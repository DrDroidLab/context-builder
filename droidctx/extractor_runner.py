"""Wraps drdroid-debug-toolkit metadata extractors for standalone use."""

import inspect
import logging
import os
import sys
import threading
import uuid
from contextlib import contextmanager
from typing import Any

# drdroid-debug-toolkit imports Django settings at module level
# (aws_boto_3_api_processor.py uses django.conf.settings for AWS_DRD_CLOUD_ROLE_ARN).
# Configure minimal Django settings before importing the toolkit.
import django.conf
if not django.conf.settings.configured:
    django.conf.settings.configure(
        AWS_DRD_CLOUD_ROLE_ARN="",
    )

from drdroid_debug_toolkit.core.integrations.source_metadata_extractor import SourceMetadataExtractor
from drdroid_debug_toolkit.core.integrations.source_metadata_extractor_facade import source_metadata_extractor_facade

from droidctx.credential_mapper import get_source_enum, yaml_creds_to_extractor_kwargs

logger = logging.getLogger(__name__)

_datadog_patched = False

# Methods to skip per connector type (slow or redundant)
SKIP_METHODS = {
    "DATADOG": {"extract_metrics"},  # Redundant with extract_services, very slow
    "CLOUDWATCH": {"extract_dashboard_by_name"},  # Requires a dashboard_name argument
}


def _patch_datadog_unstable_ops():
    """Patch datadog-api-client to ignore unknown unstable operations.

    Newer versions of datadog-api-client promoted query_timeseries_data to stable,
    but the toolkit still tries to enable it as unstable, causing a KeyError.
    """
    global _datadog_patched
    if _datadog_patched:
        return
    try:
        from datadog_api_client.configuration import _UnstableOperations

        _orig_setitem = _UnstableOperations.__setitem__

        def _safe_setitem(self, key, value):
            try:
                _orig_setitem(self, key, value)
            except KeyError:
                pass  # Silently ignore unknown unstable operations

        _UnstableOperations.__setitem__ = _safe_setitem
        _datadog_patched = True
    except ImportError:
        pass


_datadog_metrics_patched = False


def _patch_datadog_skip_metric_tags():
    """Patch DatadogApiProcessor.fetch_metrics to return empty.

    extract_services fetches ALL metrics then calls fetch_metric_tags per metric
    (thousands of sequential API calls). For context building we only need the
    service map, not per-metric tags. This makes extract_services finish in seconds.
    """
    global _datadog_metrics_patched
    if _datadog_metrics_patched:
        return
    try:
        from drdroid_debug_toolkit.core.integrations.source_api_processors.datadog_api_processor import DatadogApiProcessor
        DatadogApiProcessor.fetch_metrics = lambda self: {"data": []}
        _datadog_metrics_patched = True
    except ImportError:
        pass


# Thread-local storage for output suppression
_tls = threading.local()


@contextmanager
def _suppress_output():
    """Suppress stdout/stderr in a thread-safe way using per-thread devnull."""
    devnull = open(os.devnull, "w")
    old_stdout, old_stderr = sys.stdout, sys.stderr
    _tls.devnull = devnull
    try:
        sys.stdout = devnull
        sys.stderr = devnull
        yield
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        _tls.devnull = None
        devnull.close()


def _has_required_args(method) -> bool:
    """Check if a method requires positional arguments beyond self."""
    try:
        sig = inspect.signature(method)
        for param in sig.parameters.values():
            if param.name == "self":
                continue
            if param.default is inspect.Parameter.empty and param.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ):
                return True
        return False
    except (ValueError, TypeError):
        return False


def get_extract_methods(extractor) -> list[str]:
    """Get all extract_* methods on an extractor instance (excluding base class methods)."""
    methods = []
    for m in dir(extractor):
        if not m.startswith("extract_") or m in dir(SourceMetadataExtractor):
            continue
        method = getattr(extractor, m)
        if not callable(method):
            continue
        # Skip methods that require positional arguments (e.g. extract_deployments_for_namespace)
        if _has_required_args(method):
            continue
        methods.append(m)
    return methods


def run_extractor(
    connector_name: str,
    connector_type: str,
    yaml_config: dict,
    progress_callback: Any = None,
    verbose: bool = False,
) -> dict:
    """Run all extract_* methods for a single connector.

    Args:
        connector_name: User-defined name (e.g. "grafana_prod")
        connector_type: Connector type string (e.g. "GRAFANA")
        yaml_config: Raw YAML config dict including 'type' field
        progress_callback: Optional callable(method_name, status) for progress updates

    Returns:
        The _collected_assets dict from the extractor:
        {SourceModelType: {uid: {data_dict}, ...}, ...}

    Raises:
        Exception if extractor instantiation fails (credentials issue).
        Individual extract method failures are caught and logged.
    """
    # Route _cli_mode KUBERNETES to native kubectl extractor
    if connector_type == "KUBERNETES" and yaml_config.get("_cli_mode"):
        from droidctx.k8s_cli_extractor import extract_k8s_via_cli
        return extract_k8s_via_cli(
            connector_name=connector_name,
            progress_callback=progress_callback,
            verbose=verbose,
        )

    source = get_source_enum(connector_type)
    extractor_class = source_metadata_extractor_facade.get_connector_metadata_extractor_class(source)

    if extractor_class is None:
        raise ValueError(f"No metadata extractor registered for connector type: {connector_type}")

    # Convert YAML keys to extractor kwargs
    creds_kwargs = yaml_creds_to_extractor_kwargs(connector_type, yaml_config)

    # Patch datadog-api-client unstable_operations to silently ignore unknown keys
    _patch_datadog_unstable_ops()

    # For Datadog: skip per-metric tag fetching in extract_services (thousands of API calls)
    if connector_type == "DATADOG":
        _patch_datadog_skip_metric_tags()

    # Instantiate extractor (no api_host/api_token = standalone mode)
    # Suppress stdout during init — toolkit prints debug noise
    request_id = str(uuid.uuid4())
    if verbose:
        extractor = extractor_class(
            request_id=request_id,
            connector_name=connector_name,
            **creds_kwargs,
        )
    else:
        with _suppress_output():
            extractor = extractor_class(
                request_id=request_id,
                connector_name=connector_name,
                **creds_kwargs,
            )

    # Set attributes that some extractors expect but don't define in __init__
    if not hasattr(extractor, "account_id"):
        extractor.account_id = None

    # Discover and run all extract_* methods
    methods = get_extract_methods(extractor)
    skip = SKIP_METHODS.get(connector_type, set())
    methods = [m for m in methods if m not in skip]
    results_summary = {}

    for method_name in sorted(methods):
        if progress_callback:
            progress_callback(method_name, "running")

        try:
            if verbose:
                result = getattr(extractor, method_name)()
            else:
                with _suppress_output():
                    result = getattr(extractor, method_name)()
            count = len(result) if isinstance(result, dict) else 0
            results_summary[method_name] = count
            if progress_callback:
                progress_callback(method_name, f"done ({count} items)")
        except Exception as e:
            logger.warning(f"[{connector_name}] {method_name} failed: {e}")
            results_summary[method_name] = -1
            if progress_callback:
                progress_callback(method_name, f"failed: {e}")

    return extractor.get_collected_assets()

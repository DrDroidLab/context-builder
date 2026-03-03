"""Wraps drdroid-debug-toolkit metadata extractors for standalone use."""

import logging
import os
import sys
import uuid
from contextlib import contextmanager
from typing import Any

from drdroid_debug_toolkit.core.integrations.source_metadata_extractor import SourceMetadataExtractor
from drdroid_debug_toolkit.core.integrations.source_metadata_extractor_facade import source_metadata_extractor_facade

from droidctx.credential_mapper import get_source_enum, yaml_creds_to_extractor_kwargs

logger = logging.getLogger(__name__)

_datadog_patched = False

# Methods to skip per connector type (slow or redundant)
SKIP_METHODS = {
    "DATADOG": {"extract_metrics"},  # Redundant with extract_services, very slow
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


@contextmanager
def _suppress_output():
    """Suppress stdout and stderr from noisy toolkit code."""
    devnull = open(os.devnull, "w")
    old_stdout, old_stderr = sys.stdout, sys.stderr
    try:
        sys.stdout, sys.stderr = devnull, devnull
        yield
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
        devnull.close()


def get_extract_methods(extractor) -> list[str]:
    """Get all extract_* methods on an extractor instance (excluding base class methods)."""
    return [
        m for m in dir(extractor)
        if callable(getattr(extractor, m))
        and m.startswith("extract_")
        and m not in dir(SourceMetadataExtractor)
    ]


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

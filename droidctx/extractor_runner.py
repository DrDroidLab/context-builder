"""Wraps drdroid-debug-toolkit metadata extractors for standalone use."""

import logging
import uuid
from typing import Any

from drdroid_debug_toolkit.core.integrations.source_metadata_extractor import SourceMetadataExtractor
from drdroid_debug_toolkit.core.integrations.source_metadata_extractor_facade import source_metadata_extractor_facade

from droidctx.credential_mapper import get_source_enum, yaml_creds_to_extractor_kwargs

logger = logging.getLogger(__name__)


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

    # Instantiate extractor (no api_host/api_token = standalone mode)
    request_id = str(uuid.uuid4())
    extractor = extractor_class(
        request_id=request_id,
        connector_name=connector_name,
        **creds_kwargs,
    )

    # Discover and run all extract_* methods
    methods = get_extract_methods(extractor)
    results_summary = {}

    for method_name in sorted(methods):
        if progress_callback:
            progress_callback(method_name, "running")

        try:
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

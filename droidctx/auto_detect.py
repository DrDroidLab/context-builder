"""Auto-detect credentials from locally configured CLI tools."""

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

from droidctx.cli_tools import check_cli_tool

logger = logging.getLogger(__name__)


def _run_cmd(cmd: list[str], timeout: int = 15) -> str | None:
    """Run a shell command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _run_cmd_json(cmd: list[str], timeout: int = 15) -> dict | None:
    """Run a shell command and parse stdout as JSON."""
    out = _run_cmd(cmd, timeout)
    if out:
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return None
    return None


def detect_kubectl() -> list[dict[str, Any]]:
    """Detect Kubernetes clusters from kubectl config.

    Returns list of connector configs (one per context).
    """
    if not check_cli_tool("kubectl"):
        return []

    connectors = []

    # Get current context name
    current_ctx = _run_cmd(["kubectl", "config", "current-context"])
    if not current_ctx:
        return []

    # Get minified config for current context
    config = _run_cmd_json(["kubectl", "config", "view", "--minify", "-o", "json"])
    if not config:
        return []

    cluster_name = current_ctx
    # Try to extract a cleaner cluster name from config
    clusters = config.get("clusters", [])
    if clusters:
        cluster_name = clusters[0].get("name", current_ctx)

    # Use a safe connector name derived from context
    safe_name = current_ctx.replace("/", "-").replace(":", "-").replace(".", "-")
    connector_name = f"k8s_{safe_name}"

    connectors.append({
        "_connector_name": connector_name,
        "type": "KUBERNETES",
        "_cli_mode": True,
        "cluster_name": cluster_name,
    })

    return connectors


def detect_aws() -> list[dict[str, Any]]:
    """Detect AWS configuration from aws CLI.

    Returns CloudWatch and EKS connector configs.
    """
    if not check_cli_tool("aws"):
        return []

    connectors = []

    # Check if AWS is configured by trying to get caller identity
    identity = _run_cmd_json(["aws", "sts", "get-caller-identity"])
    if not identity:
        return []

    # Get default region from config
    region = _run_cmd(["aws", "configure", "get", "region"])
    if not region:
        # Try environment variable fallback
        import os
        region = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION")

    if region:
        connectors.append({
            "_connector_name": f"cloudwatch_{region}",
            "type": "CLOUDWATCH",
            "region": region,
        })

        # Try to detect EKS clusters
        clusters_out = _run_cmd_json(
            ["aws", "eks", "list-clusters", "--region", region, "--output", "json"]
        )
        if clusters_out:
            cluster_names = clusters_out.get("clusters", [])
            for cluster in cluster_names:
                connectors.append({
                    "_connector_name": f"eks_{cluster}",
                    "type": "EKS",
                    "region": region,
                    "eks_cluster_name": cluster,
                })

    return connectors


def detect_gcloud() -> list[dict[str, Any]]:
    """Detect GCP configuration from gcloud CLI.

    Returns GKE and GCM connector configs.
    """
    if not check_cli_tool("gcloud"):
        return []

    connectors = []

    project_id = _run_cmd(["gcloud", "config", "get-value", "project"])
    if not project_id or project_id == "(unset)":
        return []

    zone = _run_cmd(["gcloud", "config", "get-value", "compute/zone"])
    if zone == "(unset)":
        zone = None

    # Try to detect GKE clusters
    clusters_json = _run_cmd_json(
        ["gcloud", "container", "clusters", "list", "--format", "json"]
    )
    if clusters_json and isinstance(clusters_json, list):
        for cluster in clusters_json:
            cname = cluster.get("name", "")
            czone = cluster.get("zone", cluster.get("location", zone or ""))
            if cname:
                connectors.append({
                    "_connector_name": f"gke_{cname}",
                    "type": "GKE",
                    "gke_project_id": project_id,
                    "gke_cluster_name": cname,
                    "gke_zone": czone,
                })

    # GCM connector needs service account JSON — note it as needing manual completion
    connectors.append({
        "_connector_name": f"gcm_{project_id}",
        "type": "GCM",
        "gcp_project_id": project_id,
        "gcp_service_account_json": "",  # Needs manual entry
        "_needs_manual": ["gcp_service_account_json"],
    })

    return connectors


def detect_az() -> list[dict[str, Any]]:
    """Detect Azure configuration from az CLI.

    Returns Azure connector config (secrets need manual entry).
    """
    if not check_cli_tool("az"):
        return []

    connectors = []

    account = _run_cmd_json(["az", "account", "show"])
    if not account:
        return []

    tenant_id = account.get("tenantId", "")
    subscription_id = account.get("id", "")
    sub_name = account.get("name", "default")

    safe_name = sub_name.replace(" ", "-").lower()

    connectors.append({
        "_connector_name": f"azure_{safe_name}",
        "type": "AZURE",
        "azure_tenant_id": tenant_id,
        "azure_client_id": "",  # Needs manual entry
        "azure_client_secret": "",  # Needs manual entry
        "azure_subscription_id": subscription_id,
        "_needs_manual": ["azure_client_id", "azure_client_secret"],
    })

    return connectors


ALL_DETECTORS = [
    ("kubectl", detect_kubectl),
    ("aws", detect_aws),
    ("gcloud", detect_gcloud),
    ("az", detect_az),
]


def run_all_detectors() -> list[dict[str, Any]]:
    """Run all CLI tool detectors and return discovered connectors."""
    all_connectors = []

    for tool_name, detector in ALL_DETECTORS:
        try:
            results = detector()
            all_connectors.extend(results)
        except Exception as e:
            logger.warning(f"Detector for {tool_name} failed: {e}")

    return all_connectors


def merge_into_credentials(
    detected: list[dict[str, Any]],
    existing: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[str], list[str]]:
    """Merge detected connectors into existing credentials dict.

    Does not overwrite existing entries. Returns (merged, added, skipped).
    """
    merged = dict(existing)
    added = []
    skipped = []

    for connector in detected:
        name = connector.pop("_connector_name")
        connector.pop("_needs_manual", None)

        if name in merged:
            skipped.append(name)
            continue

        merged[name] = connector
        added.append(name)

    return merged, added, skipped


def save_credentials(credentials: dict[str, dict[str, Any]], keyfile: Path):
    """Save credentials dict to YAML file."""
    keyfile.parent.mkdir(parents=True, exist_ok=True)
    with open(keyfile, "w") as f:
        yaml.dump(credentials, f, default_flow_style=False, sort_keys=False)

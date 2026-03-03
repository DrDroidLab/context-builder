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

    return connectors


def detect_az() -> list[dict[str, Any]]:
    """Detect Azure configuration from az CLI.

    Azure requires client_id/client_secret which can't be auto-detected.
    Returns empty — hints are provided via get_manual_hints() instead.
    """
    return []


ALL_DETECTORS = [
    ("kubectl", detect_kubectl),
    ("aws", detect_aws),
    ("gcloud", detect_gcloud),
    ("az", detect_az),
]


def get_manual_hints() -> list[str]:
    """Return hints for CLI tools that are configured but can't be fully auto-detected."""
    hints = []

    if check_cli_tool("gcloud"):
        project_id = _run_cmd(["gcloud", "config", "get-value", "project"])
        if project_id and project_id != "(unset)":
            hints.append(f"GCM (Google Cloud Monitoring): gcloud found (project={project_id}), add manually with type: GCM")

    if check_cli_tool("az"):
        account = _run_cmd_json(["az", "account", "show"])
        if account:
            sub_name = account.get("name", "unknown")
            hints.append(f"AZURE: az CLI found (subscription={sub_name}), add manually with type: AZURE")

    return hints


def run_all_detectors() -> tuple[list[dict[str, Any]], list[str]]:
    """Run all CLI tool detectors and return (connectors, manual_hints)."""
    all_connectors = []

    for tool_name, detector in ALL_DETECTORS:
        try:
            results = detector()
            all_connectors.extend(results)
        except Exception as e:
            logger.warning(f"Detector for {tool_name} failed: {e}")

    hints = get_manual_hints()
    return all_connectors, hints


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

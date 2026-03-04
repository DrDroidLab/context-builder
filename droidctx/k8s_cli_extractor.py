"""Native Kubernetes extraction using kubectl CLI.

Replaces the debug-toolkit KUBERNETES extractor when _cli_mode is true.
Uses the current kubeconfig context — no api_server/token needed.
"""

import json
import logging
import subprocess

from drdroid_debug_toolkit.core.protos.base_pb2 import SourceModelType as SMT

logger = logging.getLogger(__name__)

# Resource types to extract and their SourceModelType mapping
K8S_RESOURCES = [
    ("namespaces", "kubectl get namespaces -o json", SMT.KUBERNETES_NAMESPACE),
    ("services", "kubectl get services -A -o json", SMT.KUBERNETES_SERVICE),
    ("deployments", "kubectl get deployments -A -o json", SMT.KUBERNETES_DEPLOYMENT),
    ("ingresses", "kubectl get ingresses -A -o json", SMT.KUBERNETES_INGRESS),
    ("statefulsets", "kubectl get statefulsets -A -o json", SMT.KUBERNETES_STATEFULSET),
    ("replicasets", "kubectl get replicasets -A -o json", SMT.KUBERNETES_REPLICASET),
    ("hpa", "kubectl get hpa -A -o json", SMT.KUBERNETES_HPA),
    ("networkpolicies", "kubectl get networkpolicies -A -o json", SMT.KUBERNETES_NETWORK_POLICY),
]


class _KubectlConnectionError(Exception):
    """Raised when kubectl can't reach the cluster."""
    pass


def _kubectl_get(cmd_str: str, timeout: int = 30) -> list[dict]:
    """Run a kubectl get command and return the items list.

    Raises _KubectlConnectionError if the cluster is unreachable.
    """
    try:
        result = subprocess.run(
            cmd_str.split(),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            # Detect connection failures so caller can fail fast
            if "Unable to connect" in stderr or "failed with exit code" in stderr:
                raise _KubectlConnectionError(stderr.split("\n")[-1])
            logger.warning(f"kubectl failed: {cmd_str.split()[2]}: {stderr.split(chr(10))[-1]}")
            return []

        data = json.loads(result.stdout)
        return data.get("items", [])
    except subprocess.TimeoutExpired:
        raise _KubectlConnectionError(f"kubectl timed out: {cmd_str}")
    except _KubectlConnectionError:
        raise
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"kubectl error: {cmd_str.split()[2]}: {e}")
        return []


def _parse_namespace(item: dict) -> tuple[str, dict]:
    """Parse a Namespace item into (uid, info)."""
    name = item.get("metadata", {}).get("name", "")
    status = item.get("status", {}).get("phase", "")
    return name, {"name": name, "status": status}


def _parse_service(item: dict) -> tuple[str, dict]:
    """Parse a Service item into (uid, info)."""
    meta = item.get("metadata", {})
    spec = item.get("spec", {})
    ns = meta.get("namespace", "default")
    name = meta.get("name", "")
    uid = f"{ns}/{name}"

    ports = []
    for p in spec.get("ports", []):
        port_str = f"{p.get('port', '')}"
        if p.get("targetPort"):
            port_str += f":{p['targetPort']}"
        if p.get("protocol"):
            port_str += f"/{p['protocol']}"
        ports.append(port_str)

    return uid, {
        "name": name,
        "namespace": ns,
        "type": spec.get("type", ""),
        "ports": ", ".join(ports),
        "cluster_ip": spec.get("clusterIP", ""),
    }


def _parse_deployment(item: dict) -> tuple[str, dict]:
    """Parse a Deployment item into (uid, info)."""
    meta = item.get("metadata", {})
    spec = item.get("spec", {})
    ns = meta.get("namespace", "default")
    name = meta.get("name", "")
    uid = f"{ns}/{name}"

    replicas = spec.get("replicas", 0)

    # Extract first container image
    image = ""
    containers = (
        spec.get("template", {}).get("spec", {}).get("containers", [])
    )
    if containers:
        image = containers[0].get("image", "")

    return uid, {
        "name": name,
        "namespace": ns,
        "replicas": replicas,
        "image": image,
    }


def _parse_ingress(item: dict) -> tuple[str, dict]:
    """Parse an Ingress item into (uid, info)."""
    meta = item.get("metadata", {})
    spec = item.get("spec", {})
    ns = meta.get("namespace", "default")
    name = meta.get("name", "")
    uid = f"{ns}/{name}"

    hosts = []
    for rule in spec.get("rules", []):
        host = rule.get("host", "")
        if host:
            hosts.append(host)

    return uid, {
        "name": name,
        "namespace": ns,
        "hosts": ", ".join(hosts),
    }


def _parse_statefulset(item: dict) -> tuple[str, dict]:
    """Parse a StatefulSet item into (uid, info)."""
    meta = item.get("metadata", {})
    spec = item.get("spec", {})
    ns = meta.get("namespace", "default")
    name = meta.get("name", "")
    uid = f"{ns}/{name}"

    return uid, {
        "name": name,
        "namespace": ns,
        "replicas": spec.get("replicas", 0),
    }


def _parse_replicaset(item: dict) -> tuple[str, dict]:
    """Parse a ReplicaSet item into (uid, info)."""
    meta = item.get("metadata", {})
    spec = item.get("spec", {})
    ns = meta.get("namespace", "default")
    name = meta.get("name", "")
    uid = f"{ns}/{name}"

    return uid, {
        "name": name,
        "namespace": ns,
        "replicas": spec.get("replicas", 0),
    }


def _parse_hpa(item: dict) -> tuple[str, dict]:
    """Parse an HPA item into (uid, info)."""
    meta = item.get("metadata", {})
    spec = item.get("spec", {})
    ns = meta.get("namespace", "default")
    name = meta.get("name", "")
    uid = f"{ns}/{name}"

    target_ref = spec.get("scaleTargetRef", {})

    return uid, {
        "name": name,
        "namespace": ns,
        "min_replicas": spec.get("minReplicas", ""),
        "max_replicas": spec.get("maxReplicas", ""),
        "target_kind": target_ref.get("kind", ""),
        "target_name": target_ref.get("name", ""),
    }


def _parse_network_policy(item: dict) -> tuple[str, dict]:
    """Parse a NetworkPolicy item into (uid, info)."""
    meta = item.get("metadata", {})
    ns = meta.get("namespace", "default")
    name = meta.get("name", "")
    uid = f"{ns}/{name}"

    return uid, {
        "name": name,
        "namespace": ns,
    }


# Map resource name to parser function
_PARSERS = {
    "namespaces": _parse_namespace,
    "services": _parse_service,
    "deployments": _parse_deployment,
    "ingresses": _parse_ingress,
    "statefulsets": _parse_statefulset,
    "replicasets": _parse_replicaset,
    "hpa": _parse_hpa,
    "networkpolicies": _parse_network_policy,
}


def extract_k8s_via_cli(
    connector_name: str,
    progress_callback=None,
    verbose: bool = False,
) -> dict:
    """Extract Kubernetes resources using kubectl CLI.

    Returns dict in the same format as debug-toolkit extractors:
    {SourceModelType: {uid: {data_dict}, ...}, ...}
    """
    assets = {}

    for resource_name, cmd, model_type in K8S_RESOURCES:
        if progress_callback:
            progress_callback(f"extract_{resource_name}", "running")

        try:
            items = _kubectl_get(cmd)
        except _KubectlConnectionError as e:
            # Cluster unreachable — no point trying remaining resources
            raise Exception(f"kubectl: cluster unreachable ({e})") from None

        parser = _PARSERS[resource_name]

        parsed = {}
        for item in items:
            try:
                uid, info = parser(item)
                if uid:
                    parsed[uid] = info
            except Exception as e:
                logger.warning(f"[{connector_name}] Failed to parse {resource_name} item: {e}")

        if parsed:
            assets[model_type] = parsed

        if progress_callback:
            progress_callback(f"extract_{resource_name}", f"done ({len(parsed)} items)")

    return assets

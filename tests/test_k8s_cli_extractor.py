"""Tests for native K8s CLI extractor."""

import json
from unittest.mock import patch, MagicMock

import pytest

from droidctx.k8s_cli_extractor import (
    _parse_namespace,
    _parse_service,
    _parse_deployment,
    _parse_ingress,
    _parse_statefulset,
    _parse_replicaset,
    _parse_hpa,
    _parse_network_policy,
    extract_k8s_via_cli,
)


class TestParsers:
    def test_parse_namespace(self):
        item = {"metadata": {"name": "default"}, "status": {"phase": "Active"}}
        uid, info = _parse_namespace(item)
        assert uid == "default"
        assert info["name"] == "default"
        assert info["status"] == "Active"

    def test_parse_service(self):
        item = {
            "metadata": {"name": "api-svc", "namespace": "prod"},
            "spec": {
                "type": "ClusterIP",
                "clusterIP": "10.0.0.1",
                "ports": [{"port": 80, "targetPort": 8080, "protocol": "TCP"}],
            },
        }
        uid, info = _parse_service(item)
        assert uid == "prod/api-svc"
        assert info["name"] == "api-svc"
        assert info["namespace"] == "prod"
        assert info["type"] == "ClusterIP"
        assert "80:8080/TCP" in info["ports"]

    def test_parse_deployment(self):
        item = {
            "metadata": {"name": "web", "namespace": "default"},
            "spec": {
                "replicas": 3,
                "template": {
                    "spec": {
                        "containers": [{"image": "nginx:1.25", "name": "nginx"}],
                    },
                },
            },
        }
        uid, info = _parse_deployment(item)
        assert uid == "default/web"
        assert info["replicas"] == 3
        assert info["image"] == "nginx:1.25"

    def test_parse_ingress(self):
        item = {
            "metadata": {"name": "web-ing", "namespace": "default"},
            "spec": {
                "rules": [{"host": "app.example.com"}, {"host": "api.example.com"}],
            },
        }
        uid, info = _parse_ingress(item)
        assert uid == "default/web-ing"
        assert "app.example.com" in info["hosts"]
        assert "api.example.com" in info["hosts"]

    def test_parse_statefulset(self):
        item = {
            "metadata": {"name": "redis", "namespace": "cache"},
            "spec": {"replicas": 3},
        }
        uid, info = _parse_statefulset(item)
        assert uid == "cache/redis"
        assert info["replicas"] == 3

    def test_parse_replicaset(self):
        item = {
            "metadata": {"name": "web-abc123", "namespace": "default"},
            "spec": {"replicas": 2},
        }
        uid, info = _parse_replicaset(item)
        assert uid == "default/web-abc123"
        assert info["replicas"] == 2

    def test_parse_hpa(self):
        item = {
            "metadata": {"name": "web-hpa", "namespace": "default"},
            "spec": {
                "minReplicas": 2,
                "maxReplicas": 10,
                "scaleTargetRef": {"kind": "Deployment", "name": "web"},
            },
        }
        uid, info = _parse_hpa(item)
        assert uid == "default/web-hpa"
        assert info["min_replicas"] == 2
        assert info["max_replicas"] == 10
        assert info["target_kind"] == "Deployment"
        assert info["target_name"] == "web"

    def test_parse_network_policy(self):
        item = {
            "metadata": {"name": "deny-all", "namespace": "secure"},
        }
        uid, info = _parse_network_policy(item)
        assert uid == "secure/deny-all"
        assert info["name"] == "deny-all"


class TestExtractK8sViaCli:
    @patch("droidctx.k8s_cli_extractor._kubectl_get")
    def test_basic_extraction(self, mock_get):
        def side_effect(cmd, **kwargs):
            if "namespaces" in cmd:
                return [
                    {"metadata": {"name": "default"}, "status": {"phase": "Active"}},
                    {"metadata": {"name": "kube-system"}, "status": {"phase": "Active"}},
                ]
            if "deployments" in cmd:
                return [
                    {
                        "metadata": {"name": "api", "namespace": "default"},
                        "spec": {
                            "replicas": 2,
                            "template": {"spec": {"containers": [{"image": "api:v1", "name": "api"}]}},
                        },
                    },
                ]
            return []

        mock_get.side_effect = side_effect

        from drdroid_debug_toolkit.core.protos.base_pb2 import SourceModelType as SMT
        assets = extract_k8s_via_cli("test-k8s")

        assert SMT.KUBERNETES_NAMESPACE in assets
        assert len(assets[SMT.KUBERNETES_NAMESPACE]) == 2
        assert SMT.KUBERNETES_DEPLOYMENT in assets
        assert len(assets[SMT.KUBERNETES_DEPLOYMENT]) == 1

    @patch("droidctx.k8s_cli_extractor._kubectl_get", return_value=[])
    def test_empty_cluster(self, mock_get):
        assets = extract_k8s_via_cli("empty-k8s")
        # No model types should be in assets since all returned empty
        assert len(assets) == 0

    @patch("droidctx.k8s_cli_extractor._kubectl_get")
    def test_progress_callback(self, mock_get):
        mock_get.return_value = []
        callbacks = []

        def cb(method, status):
            callbacks.append((method, status))

        extract_k8s_via_cli("test", progress_callback=cb)
        # Should have called back for each resource type (running + done)
        assert len(callbacks) == 16  # 8 resource types * 2 (running + done)

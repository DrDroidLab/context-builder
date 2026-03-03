"""Tests for auto_detect module."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

from droidctx.auto_detect import (
    _run_cmd,
    _run_cmd_json,
    detect_kubectl,
    detect_aws,
    detect_gcloud,
    detect_az,
    run_all_detectors,
    merge_into_credentials,
    save_credentials,
)


class TestRunCmd:
    def test_successful_command(self):
        result = _run_cmd(["echo", "hello"])
        assert result == "hello"

    def test_failed_command(self):
        result = _run_cmd(["false"])
        assert result is None

    def test_nonexistent_command(self):
        result = _run_cmd(["nonexistent_cmd_xyz_123"])
        assert result is None


class TestRunCmdJson:
    def test_valid_json(self):
        result = _run_cmd_json(["echo", '{"key": "value"}'])
        assert result == {"key": "value"}

    def test_invalid_json(self):
        result = _run_cmd_json(["echo", "not json"])
        assert result is None


class TestDetectKubectl:
    @patch("droidctx.auto_detect.check_cli_tool", return_value=False)
    def test_kubectl_not_installed(self, mock_check):
        assert detect_kubectl() == []

    @patch("droidctx.auto_detect._run_cmd_json")
    @patch("droidctx.auto_detect._run_cmd")
    @patch("droidctx.auto_detect.check_cli_tool", return_value=True)
    def test_kubectl_detected(self, mock_check, mock_cmd, mock_json):
        mock_cmd.return_value = "my-cluster-context"
        mock_json.return_value = {
            "clusters": [{"name": "my-cluster"}],
        }

        result = detect_kubectl()
        assert len(result) == 1
        assert result[0]["type"] == "KUBERNETES"
        assert result[0]["_cli_mode"] is True
        assert result[0]["cluster_name"] == "my-cluster"
        assert "_connector_name" in result[0]

    @patch("droidctx.auto_detect._run_cmd", return_value=None)
    @patch("droidctx.auto_detect.check_cli_tool", return_value=True)
    def test_kubectl_no_context(self, mock_check, mock_cmd):
        assert detect_kubectl() == []


class TestDetectAws:
    @patch("droidctx.auto_detect.check_cli_tool", return_value=False)
    def test_aws_not_installed(self, mock_check):
        assert detect_aws() == []

    @patch("droidctx.auto_detect._run_cmd_json")
    @patch("droidctx.auto_detect._run_cmd")
    @patch("droidctx.auto_detect.check_cli_tool", return_value=True)
    def test_aws_detected_with_region(self, mock_check, mock_cmd, mock_json):
        def cmd_side_effect(cmd, **kwargs):
            if "get-caller-identity" in cmd:
                return {"Account": "123456"}
            if "list-clusters" in cmd:
                return {"clusters": ["eks-prod"]}
            return None
        mock_json.side_effect = cmd_side_effect

        mock_cmd.side_effect = lambda cmd, **kwargs: "us-east-1" if "get" in cmd and "region" in cmd else None

        result = detect_aws()
        # Should have CloudWatch + EKS connectors
        assert any(c["type"] == "CLOUDWATCH" for c in result)
        assert any(c["type"] == "EKS" for c in result)

    @patch("droidctx.auto_detect._run_cmd_json", return_value=None)
    @patch("droidctx.auto_detect.check_cli_tool", return_value=True)
    def test_aws_not_configured(self, mock_check, mock_json):
        assert detect_aws() == []


class TestDetectGcloud:
    @patch("droidctx.auto_detect.check_cli_tool", return_value=False)
    def test_gcloud_not_installed(self, mock_check):
        assert detect_gcloud() == []

    @patch("droidctx.auto_detect._run_cmd_json")
    @patch("droidctx.auto_detect._run_cmd")
    @patch("droidctx.auto_detect.check_cli_tool", return_value=True)
    def test_gcloud_detected(self, mock_check, mock_cmd, mock_json):
        def cmd_side_effect(cmd, **kwargs):
            cmd_str = " ".join(cmd)
            if "get-value project" in cmd_str:
                return "my-project"
            if "compute/zone" in cmd_str:
                return "us-central1-a"
            return None
        mock_cmd.side_effect = cmd_side_effect
        mock_json.return_value = [{"name": "gke-1", "zone": "us-central1-a"}]

        result = detect_gcloud()
        assert any(c["type"] == "GKE" for c in result)
        assert any(c["type"] == "GCM" for c in result)

    @patch("droidctx.auto_detect._run_cmd", return_value="(unset)")
    @patch("droidctx.auto_detect.check_cli_tool", return_value=True)
    def test_gcloud_no_project(self, mock_check, mock_cmd):
        assert detect_gcloud() == []


class TestDetectAz:
    @patch("droidctx.auto_detect.check_cli_tool", return_value=False)
    def test_az_not_installed(self, mock_check):
        assert detect_az() == []

    @patch("droidctx.auto_detect._run_cmd_json")
    @patch("droidctx.auto_detect.check_cli_tool", return_value=True)
    def test_az_detected(self, mock_check, mock_json):
        mock_json.return_value = {
            "tenantId": "tenant-123",
            "id": "sub-456",
            "name": "My Subscription",
        }

        result = detect_az()
        assert len(result) == 1
        assert result[0]["type"] == "AZURE"
        assert result[0]["azure_tenant_id"] == "tenant-123"
        assert result[0]["azure_subscription_id"] == "sub-456"
        assert result[0]["_needs_manual"] == ["azure_client_id", "azure_client_secret"]


class TestMergeIntoCredentials:
    def test_merge_new_connectors(self):
        detected = [
            {"_connector_name": "k8s_prod", "type": "KUBERNETES", "_cli_mode": True, "cluster_name": "prod"},
        ]
        existing = {"grafana": {"type": "GRAFANA", "grafana_host": "h", "grafana_api_key": "k"}}

        merged, added, skipped = merge_into_credentials(detected, existing)
        assert "k8s_prod" in merged
        assert "grafana" in merged
        assert added == ["k8s_prod"]
        assert skipped == []

    def test_skip_existing(self):
        detected = [
            {"_connector_name": "grafana", "type": "KUBERNETES", "_cli_mode": True, "cluster_name": "x"},
        ]
        existing = {"grafana": {"type": "GRAFANA"}}

        merged, added, skipped = merge_into_credentials(detected, existing)
        assert merged["grafana"]["type"] == "GRAFANA"  # Not overwritten
        assert added == []
        assert skipped == ["grafana"]

    def test_strips_internal_fields(self):
        detected = [
            {"_connector_name": "k8s", "_needs_manual": ["field"], "type": "KUBERNETES", "_cli_mode": True, "cluster_name": "c"},
        ]
        merged, added, _ = merge_into_credentials(detected, {})
        assert "_connector_name" not in merged["k8s"]
        assert "_needs_manual" not in merged["k8s"]


class TestSaveCredentials:
    def test_save_and_reload(self, tmp_path):
        creds = {"k8s": {"type": "KUBERNETES", "_cli_mode": True, "cluster_name": "prod"}}
        keyfile = tmp_path / "creds.yaml"

        save_credentials(creds, keyfile)

        with open(keyfile) as f:
            loaded = yaml.safe_load(f)

        assert loaded == creds

    def test_creates_parent_dirs(self, tmp_path):
        keyfile = tmp_path / "subdir" / "nested" / "creds.yaml"
        save_credentials({"test": {"type": "GRAFANA"}}, keyfile)
        assert keyfile.exists()


class TestRunAllDetectors:
    @patch("droidctx.auto_detect.ALL_DETECTORS", [
        ("kubectl", lambda: [{"_connector_name": "k8s_test", "type": "KUBERNETES", "_cli_mode": True, "cluster_name": "test"}]),
        ("aws", lambda: []),
    ])
    def test_aggregates_results(self):
        results = run_all_detectors()
        assert len(results) == 1
        assert results[0]["type"] == "KUBERNETES"

    def _boom():
        raise Exception("boom")

    @patch("droidctx.auto_detect.ALL_DETECTORS", [
        ("bad_tool", lambda: (_ for _ in ()).throw(Exception("boom"))),
        ("aws", lambda: []),
    ])
    def test_handles_detector_failure(self):
        # Should not raise, just skip the failing detector
        results = run_all_detectors()
        assert isinstance(results, list)
        assert results == []

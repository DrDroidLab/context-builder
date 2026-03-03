"""Tests for _cli_mode credential validation bypass."""

from droidctx.config import validate_credentials


class TestCliModeValidation:
    def test_k8s_cli_mode_skips_server_and_token(self):
        creds = {
            "k8s_prod": {
                "type": "KUBERNETES",
                "_cli_mode": True,
                "cluster_name": "prod-cluster",
            }
        }
        errors = validate_credentials(creds)
        assert errors == []

    def test_k8s_without_cli_mode_requires_all_fields(self):
        creds = {
            "k8s_prod": {
                "type": "KUBERNETES",
                "cluster_name": "prod-cluster",
            }
        }
        errors = validate_credentials(creds)
        assert len(errors) == 2  # missing cluster_api_server and cluster_token
        messages = [e["message"] for e in errors]
        assert any("cluster_api_server" in m for m in messages)
        assert any("cluster_token" in m for m in messages)

    def test_k8s_cli_mode_still_requires_cluster_name(self):
        creds = {
            "k8s_prod": {
                "type": "KUBERNETES",
                "_cli_mode": True,
            }
        }
        errors = validate_credentials(creds)
        assert len(errors) == 1
        assert "cluster_name" in errors[0]["message"]

    def test_non_k8s_connector_unaffected_by_cli_mode(self):
        creds = {
            "grafana": {
                "type": "GRAFANA",
                "_cli_mode": True,
                "grafana_host": "https://g.com",
            }
        }
        errors = validate_credentials(creds)
        # GRAFANA has no cli_mode_optional, so _cli_mode has no effect
        assert len(errors) == 1
        assert "grafana_api_key" in errors[0]["message"]

    def test_standard_k8s_still_works(self):
        creds = {
            "k8s": {
                "type": "KUBERNETES",
                "cluster_name": "prod",
                "cluster_api_server": "https://k8s.example.com",
                "cluster_token": "token123",
            }
        }
        errors = validate_credentials(creds)
        assert errors == []

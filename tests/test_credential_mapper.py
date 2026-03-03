"""Tests for credential key mapping."""

from drdroid_debug_toolkit.core.protos.base_pb2 import Source

from droidctx.credential_mapper import (
    get_source_enum,
    yaml_creds_to_extractor_kwargs,
)


class TestGetSourceEnum:
    def test_grafana(self):
        assert get_source_enum("GRAFANA") == Source.GRAFANA

    def test_datadog(self):
        assert get_source_enum("DATADOG") == Source.DATADOG

    def test_unknown_raises(self):
        try:
            get_source_enum("NOT_A_REAL_TYPE")
            assert False, "Should have raised"
        except ValueError:
            pass


class TestYamlCredsToExtractorKwargs:
    def test_grafana_passthrough(self):
        yaml_config = {
            "type": "GRAFANA",
            "grafana_host": "https://g.com",
            "grafana_api_key": "key123",
            "ssl_verify": "false",
        }
        result = yaml_creds_to_extractor_kwargs("GRAFANA", yaml_config)
        assert result == {
            "grafana_host": "https://g.com",
            "grafana_api_key": "key123",
            "ssl_verify": "false",
        }
        assert "type" not in result

    def test_kubernetes_key_mapping(self):
        yaml_config = {
            "type": "KUBERNETES",
            "cluster_name": "prod",
            "cluster_api_server": "https://k8s.example.com",
            "cluster_token": "tok123",
        }
        result = yaml_creds_to_extractor_kwargs("KUBERNETES", yaml_config)
        assert result == {
            "api_server": "https://k8s.example.com",
            "token": "tok123",
        }
        # cluster_name should be dropped (mapped to None)
        assert "cluster_name" not in result

    def test_github_key_mapping(self):
        yaml_config = {
            "type": "GITHUB",
            "github_token": "ghp_xxx",
            "github_org": "myorg",
        }
        result = yaml_creds_to_extractor_kwargs("GITHUB", yaml_config)
        assert result == {"api_key": "ghp_xxx", "org": "myorg"}

    def test_datadog_passthrough(self):
        yaml_config = {
            "type": "DATADOG",
            "dd_api_key": "a",
            "dd_app_key": "b",
            "dd_api_domain": "datadoghq.com",
        }
        result = yaml_creds_to_extractor_kwargs("DATADOG", yaml_config)
        assert result == {"dd_api_key": "a", "dd_app_key": "b", "dd_api_domain": "datadoghq.com"}

    def test_azure_key_mapping(self):
        yaml_config = {
            "type": "AZURE",
            "azure_tenant_id": "t",
            "azure_client_id": "c",
            "azure_client_secret": "s",
            "azure_subscription_id": "sub",
        }
        result = yaml_creds_to_extractor_kwargs("AZURE", yaml_config)
        assert result == {
            "tenant_id": "t",
            "client_id": "c",
            "client_secret": "s",
            "subscription_id": "sub",
        }

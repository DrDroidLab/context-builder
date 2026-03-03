"""Tests for cross-service aggregation."""

from droidctx.markdown_generator import MarkdownGenerator


class TestServiceCrossref:
    def test_generates_services_file(self, tmp_path):
        from drdroid_debug_toolkit.core.protos.base_pb2 import SourceModelType as SMT

        gen = MarkdownGenerator(tmp_path)

        results = {
            "grafana_prod": {
                "connector_type": "GRAFANA",
                "assets": {
                    SMT.GRAFANA_TEMPO_SERVICE: {
                        "svc1": {"name": "payment-service"},
                        "svc2": {"name": "auth-service"},
                    },
                },
                "error": None,
            },
            "k8s_prod": {
                "connector_type": "KUBERNETES",
                "assets": {
                    SMT.KUBERNETES_SERVICE: {
                        "svc1": {"name": "payment-service"},
                        "svc3": {"name": "api-gateway"},
                    },
                    SMT.KUBERNETES_DEPLOYMENT: {
                        "dep1": {"name": "payment-service"},
                    },
                },
                "error": None,
            },
        }

        gen.generate_service_crossref(results)

        services_file = tmp_path / "resources" / "cross_references" / "services.md"
        assert services_file.exists()
        content = services_file.read_text()
        assert "payment-service" in content
        assert "auth-service" in content
        assert "api-gateway" in content

    def test_multi_connector_service_in_detail_section(self, tmp_path):
        from drdroid_debug_toolkit.core.protos.base_pb2 import SourceModelType as SMT

        gen = MarkdownGenerator(tmp_path)

        results = {
            "grafana_prod": {
                "connector_type": "GRAFANA",
                "assets": {SMT.GRAFANA_TEMPO_SERVICE: {"s1": {"name": "payment-service"}}},
                "error": None,
            },
            "k8s_prod": {
                "connector_type": "KUBERNETES",
                "assets": {SMT.KUBERNETES_SERVICE: {"s2": {"name": "payment-service"}}},
                "error": None,
            },
        }

        gen.generate_service_crossref(results)

        services_file = tmp_path / "resources" / "cross_references" / "services.md"
        assert services_file.exists()
        content = services_file.read_text()
        assert "grafana_prod" in content
        assert "k8s_prod" in content
        assert "Multi-Source Services" in content

    def test_single_connector_service_no_detail_section(self, tmp_path):
        from drdroid_debug_toolkit.core.protos.base_pb2 import SourceModelType as SMT

        gen = MarkdownGenerator(tmp_path)

        results = {
            "k8s_prod": {
                "connector_type": "KUBERNETES",
                "assets": {SMT.KUBERNETES_SERVICE: {"s1": {"name": "lonely-service"}}},
                "error": None,
            },
        }

        gen.generate_service_crossref(results)

        services_file = tmp_path / "resources" / "cross_references" / "services.md"
        assert services_file.exists()
        content = services_file.read_text()
        assert "lonely-service" in content
        # Should NOT have the multi-source detail section
        assert "Multi-Source Services" not in content

    def test_skips_failed_connectors(self, tmp_path):
        gen = MarkdownGenerator(tmp_path)

        results = {
            "broken": {
                "connector_type": "GRAFANA",
                "assets": {},
                "error": "Connection refused",
            },
        }

        gen.generate_service_crossref(results)

        # No file generated since no services found
        services_file = tmp_path / "resources" / "cross_references" / "services.md"
        assert not services_file.exists()

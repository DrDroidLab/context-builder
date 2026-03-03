"""Tests for cross-service aggregation."""

from droidctx.markdown_generator import MarkdownGenerator


class TestServiceCrossref:
    def test_generates_index(self, tmp_path):
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

        index = tmp_path / "resources" / "services" / "index.md"
        assert index.exists()
        content = index.read_text()
        assert "payment-service" in content
        assert "auth-service" in content
        assert "api-gateway" in content

    def test_multi_connector_service_gets_own_file(self, tmp_path):
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

        svc_file = tmp_path / "resources" / "services" / "payment-service.md"
        assert svc_file.exists()
        content = svc_file.read_text()
        assert "grafana_prod" in content
        assert "k8s_prod" in content

    def test_single_connector_service_no_own_file(self, tmp_path):
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

        # Should be in index but not get its own file (only 1 connector)
        svc_file = tmp_path / "resources" / "services" / "lonely-service.md"
        assert not svc_file.exists()

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

        # No index generated since no services found
        index = tmp_path / "resources" / "services" / "index.md"
        assert not index.exists()

"""Tests for markdown generation."""

from pathlib import Path
from unittest.mock import patch

from droidctx.markdown_generator import MarkdownGenerator, sanitize_filename


class TestSanitizeFilename:
    def test_basic(self):
        assert sanitize_filename("My Dashboard") == "my-dashboard"

    def test_special_chars(self):
        assert sanitize_filename("api/v2 (prod)") == "apiv2-prod"

    def test_long_name(self):
        result = sanitize_filename("x" * 200)
        assert len(result) <= 100


class TestMarkdownGenerator:
    def test_generate_summary(self, tmp_path):
        gen = MarkdownGenerator(tmp_path)
        # Mock SourceModelType with plain int
        assets = {301: {"uid1": {"name": "Prometheus", "type": "prometheus"}}}

        lines = gen._generate_summary("grafana_prod", "GRAFANA", assets)

        assert isinstance(lines, list)
        content = "\n".join(lines)
        assert "grafana_prod" in content
        assert "GRAFANA" in content

    def test_generate_overview(self, tmp_path):
        gen = MarkdownGenerator(tmp_path)
        results = {
            "grafana_prod": {
                "connector_type": "GRAFANA",
                "assets": {301: {"a": {}, "b": {}}},
                "error": None,
            },
            "bad_one": {
                "connector_type": "DATADOG",
                "assets": {},
                "error": "Connection refused",
            },
        }

        gen.generate_overview(results)

        overview = tmp_path / "resources" / "overview.md"
        assert overview.exists()
        content = overview.read_text()
        assert "grafana_prod" in content
        assert "OK" in content
        assert "FAILED" in content
        assert "Connection refused" in content

    def test_generate_generic(self, tmp_path):
        gen = MarkdownGenerator(tmp_path)
        assets = {2801: {"app1": {"name": "my-app", "status": "healthy"}}}

        lines = gen._generate_generic("argocd_prod", "ARGOCD", assets)

        assert isinstance(lines, list)
        content = "\n".join(lines)
        assert "my-app" in content

    def test_generate_all_single_file(self, tmp_path):
        gen = MarkdownGenerator(tmp_path)
        assets = {2801: {"app1": {"name": "my-app", "status": "healthy"}}}

        gen.generate_all("argocd_prod", "ARGOCD", assets)

        context_file = tmp_path / "resources" / "connectors" / "argocd_prod" / "context.md"
        assert context_file.exists()
        content = context_file.read_text()
        assert "argocd_prod" in content
        assert "ARGOCD" in content
        assert "my-app" in content

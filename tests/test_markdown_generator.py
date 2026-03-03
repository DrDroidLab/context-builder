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
    def test_generate_tool_file(self, tmp_path):
        gen = MarkdownGenerator(tmp_path)
        # Mock SourceModelType with plain int
        assets = {301: {"uid1": {"name": "Prometheus", "type": "prometheus"}}}

        gen._generate_tool_file("grafana_prod", "GRAFANA", assets)

        tool_file = tmp_path / "resources" / "tools" / "grafana_prod.md"
        assert tool_file.exists()
        content = tool_file.read_text()
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

        gen._generate_generic("argocd_prod", "ARGOCD", assets)

        detail_file = tmp_path / "resources" / "tools" / "argocd_prod-details.md"
        assert detail_file.exists()
        content = detail_file.read_text()
        assert "my-app" in content

"""Tests for the init command."""

from pathlib import Path

from typer.testing import CliRunner

from droidctx.main import app

runner = CliRunner()


class TestInitCommand:
    def test_creates_folder_structure(self, tmp_path):
        target = tmp_path / "ctx"
        result = runner.invoke(app, ["init", "--path", str(target)])
        assert result.exit_code == 0

        assert (target / "resources").is_dir()
        assert (target / "resources" / "connectors").is_dir()
        assert (target / "resources" / "cross_references").is_dir()

    def test_creates_credentials_template(self, tmp_path):
        target = tmp_path / "ctx"
        runner.invoke(app, ["init", "--path", str(target)])

        creds_file = target / "credentials.yaml"
        assert creds_file.exists()
        content = creds_file.read_text()
        assert "GRAFANA" in content
        assert "DATADOG" in content
        assert "KUBERNETES" in content

    def test_creates_overview_placeholder(self, tmp_path):
        target = tmp_path / "ctx"
        runner.invoke(app, ["init", "--path", str(target)])

        overview = target / "resources" / "overview.md"
        assert overview.exists()
        assert "droidctx sync" in overview.read_text()

    def test_reinit_preserves_existing_files(self, tmp_path):
        target = tmp_path / "ctx"

        # First init
        runner.invoke(app, ["init", "--path", str(target)])

        # Write custom content to credentials
        creds_file = target / "credentials.yaml"
        creds_file.write_text("my_custom: content")

        # Re-init
        result = runner.invoke(app, ["init", "--path", str(target)])
        assert result.exit_code == 0

        # Custom content preserved
        assert creds_file.read_text() == "my_custom: content"

    def test_prints_next_steps(self, tmp_path):
        target = tmp_path / "ctx"
        result = runner.invoke(app, ["init", "--path", str(target)])
        assert "Next steps" in result.output
        assert "Edit credentials" in result.output
        assert "Sync metadata" in result.output

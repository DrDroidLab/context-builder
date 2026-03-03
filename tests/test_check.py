"""Tests for the check command."""

from pathlib import Path

import yaml
from typer.testing import CliRunner

from droidctx.main import app

runner = CliRunner()


def _write_creds(path: Path, creds: dict):
    path.write_text(yaml.dump(creds))


class TestCheckCommand:
    def test_valid_credentials(self, tmp_path):
        keyfile = tmp_path / "creds.yaml"
        _write_creds(keyfile, {
            "grafana_prod": {"type": "GRAFANA", "grafana_host": "h", "grafana_api_key": "k"},
        })

        result = runner.invoke(app, ["check", "--keyfile", str(keyfile)])
        assert result.exit_code == 0
        assert "OK" in result.output
        assert "All credentials valid" in result.output

    def test_invalid_credentials_fails(self, tmp_path):
        keyfile = tmp_path / "creds.yaml"
        _write_creds(keyfile, {
            "bad": {"type": "UNKNOWN_TYPE"},
        })

        result = runner.invoke(app, ["check", "--keyfile", str(keyfile)])
        assert result.exit_code == 1
        assert "INVALID" in result.output

    def test_missing_required_field(self, tmp_path):
        keyfile = tmp_path / "creds.yaml"
        _write_creds(keyfile, {
            "grafana_prod": {"type": "GRAFANA", "grafana_host": "h"},
            # missing grafana_api_key
        })

        result = runner.invoke(app, ["check", "--keyfile", str(keyfile)])
        assert result.exit_code == 1
        assert "INVALID" in result.output
        assert "grafana_api_key" in result.output

    def test_missing_keyfile(self, tmp_path):
        result = runner.invoke(app, ["check", "--keyfile", str(tmp_path / "nope.yaml")])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_mixed_valid_invalid(self, tmp_path):
        keyfile = tmp_path / "creds.yaml"
        _write_creds(keyfile, {
            "good": {"type": "GRAFANA", "grafana_host": "h", "grafana_api_key": "k"},
            "bad": {"type": "MISSING_FIELDS"},
        })

        result = runner.invoke(app, ["check", "--keyfile", str(keyfile)])
        assert result.exit_code == 1
        assert "OK" in result.output
        assert "INVALID" in result.output

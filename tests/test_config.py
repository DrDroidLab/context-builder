"""Tests for credential loading and validation."""

import tempfile
from pathlib import Path

import pytest
import yaml

from droidctx.config import load_credentials, validate_credentials


def _write_yaml(data: dict, path: Path):
    path.write_text(yaml.dump(data))


class TestLoadCredentials:
    def test_load_valid_file(self, tmp_path):
        creds = {"grafana_prod": {"type": "GRAFANA", "grafana_host": "https://g.com", "grafana_api_key": "key"}}
        f = tmp_path / "creds.yaml"
        _write_yaml(creds, f)

        result = load_credentials(f)
        assert result == creds

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_credentials(Path("/nonexistent/creds.yaml"))

    def test_empty_file(self, tmp_path):
        f = tmp_path / "creds.yaml"
        f.write_text("")
        with pytest.raises(ValueError, match="empty"):
            load_credentials(f)


class TestValidateCredentials:
    def test_valid_grafana(self):
        creds = {"grafana_prod": {"type": "GRAFANA", "grafana_host": "https://g.com", "grafana_api_key": "key"}}
        errors = validate_credentials(creds)
        assert errors == []

    def test_missing_type(self):
        creds = {"bad": {"grafana_host": "https://g.com"}}
        errors = validate_credentials(creds)
        assert len(errors) == 1
        assert "type" in errors[0]["message"]

    def test_unknown_type(self):
        creds = {"bad": {"type": "UNKNOWN_THING"}}
        errors = validate_credentials(creds)
        assert len(errors) == 1
        assert "Unknown" in errors[0]["message"]

    def test_missing_required_field(self):
        creds = {"grafana_prod": {"type": "GRAFANA", "grafana_host": "https://g.com"}}
        errors = validate_credentials(creds)
        assert len(errors) == 1
        assert "grafana_api_key" in errors[0]["message"]

    def test_multiple_connectors(self):
        creds = {
            "grafana": {"type": "GRAFANA", "grafana_host": "h", "grafana_api_key": "k"},
            "dd": {"type": "DATADOG", "dd_api_key": "a", "dd_app_key": "b"},
        }
        errors = validate_credentials(creds)
        assert errors == []

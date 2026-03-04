"""Tests for the sync engine with mocked extractors."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import yaml
import pytest

from droidctx.sync_engine import sync
from rich.console import Console


def _write_creds(path: Path, creds: dict):
    path.write_text(yaml.dump(creds))


class TestSyncEngine:
    def test_dry_run_writes_no_files(self, tmp_path):
        keyfile = tmp_path / "creds.yaml"
        _write_creds(keyfile, {
            "grafana_prod": {"type": "GRAFANA", "grafana_host": "h", "grafana_api_key": "k"},
        })
        output = tmp_path / "output"
        output.mkdir()

        console = Console(file=open(tmp_path / "log.txt", "w"))
        result = sync(keyfile=keyfile, output_dir=output, dry_run=True, console=console)

        assert result == {}
        # No resources dir should be created
        assert not (output / "resources" / "connectors").exists()

    def test_invalid_creds_still_runs_valid_ones(self, tmp_path):
        keyfile = tmp_path / "creds.yaml"
        _write_creds(keyfile, {
            "bad": {"type": "UNKNOWN"},
            "grafana_prod": {"type": "GRAFANA", "grafana_host": "h", "grafana_api_key": "k"},
        })
        output = tmp_path / "output"
        output.mkdir()

        mock_assets = {301: {"ds1": {"name": "Prometheus", "type": "prometheus"}}}

        with patch("droidctx.sync_engine.run_extractor") as mock_run:
            mock_run.return_value = mock_assets
            console = Console(file=open(tmp_path / "log.txt", "w"))
            result = sync(keyfile=keyfile, output_dir=output, console=console)

        # Only grafana_prod should be in results (bad was filtered out)
        assert "grafana_prod" in result
        assert "bad" not in result

    def test_connector_filter(self, tmp_path):
        keyfile = tmp_path / "creds.yaml"
        _write_creds(keyfile, {
            "grafana_prod": {"type": "GRAFANA", "grafana_host": "h", "grafana_api_key": "k"},
            "dd_prod": {"type": "DATADOG", "dd_api_key": "a", "dd_app_key": "b"},
        })
        output = tmp_path / "output"
        output.mkdir()

        with patch("droidctx.sync_engine.run_extractor") as mock_run:
            mock_run.return_value = {}
            console = Console(file=open(tmp_path / "log.txt", "w"))
            result = sync(keyfile=keyfile, output_dir=output,
                         connector_filter=["grafana_prod"], console=console)

        # Only grafana_prod, dd_prod should be skipped
        assert "grafana_prod" in result
        assert "dd_prod" not in result

    def test_extractor_failure_recorded(self, tmp_path):
        keyfile = tmp_path / "creds.yaml"
        _write_creds(keyfile, {
            "grafana_prod": {"type": "GRAFANA", "grafana_host": "h", "grafana_api_key": "k"},
        })
        output = tmp_path / "output"
        output.mkdir()

        with patch("droidctx.sync_engine.run_extractor") as mock_run:
            mock_run.side_effect = ConnectionError("Connection refused")
            console = Console(file=open(tmp_path / "log.txt", "w"))
            result = sync(keyfile=keyfile, output_dir=output, console=console)

        assert "grafana_prod" in result
        assert result["grafana_prod"]["error"] is not None
        assert "Connection refused" in result["grafana_prod"]["error"]

    def test_generates_overview(self, tmp_path):
        keyfile = tmp_path / "creds.yaml"
        _write_creds(keyfile, {
            "grafana_prod": {"type": "GRAFANA", "grafana_host": "h", "grafana_api_key": "k"},
        })
        output = tmp_path / "output"
        output.mkdir()

        mock_assets = {301: {"ds1": {"name": "Prometheus"}}}
        with patch("droidctx.sync_engine.run_extractor") as mock_run:
            mock_run.return_value = mock_assets
            console = Console(file=open(tmp_path / "log.txt", "w"))
            sync(keyfile=keyfile, output_dir=output, console=console)

        overview = output / "resources" / "overview.md"
        assert overview.exists()
        content = overview.read_text()
        assert "grafana_prod" in content
        assert "OK" in content

    def test_empty_credentials_file(self, tmp_path):
        keyfile = tmp_path / "creds.yaml"
        keyfile.write_text("")

        output = tmp_path / "output"
        output.mkdir()

        console = Console(file=open(tmp_path / "log.txt", "w"))
        # Empty file returns {} — sync completes with no connectors
        result = sync(keyfile=keyfile, output_dir=output, console=console)
        assert result == {}

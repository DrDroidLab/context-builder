"""Tests for auto-sync feature: config, schedulers, and CLI commands."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from droidctx.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# auto_sync module tests
# ---------------------------------------------------------------------------

class TestAutoSyncConfig:
    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        from droidctx import auto_sync

        cfg_dir = tmp_path / "cfg"
        cfg_file = cfg_dir / "auto-sync.yaml"
        monkeypatch.setattr(auto_sync, "CONFIG_DIR", cfg_dir)
        monkeypatch.setattr(auto_sync, "CONFIG_FILE", cfg_file)

        config = {
            "enabled": True,
            "interval_minutes": 15,
            "keyfile": "/tmp/k.yaml",
            "output_dir": "/tmp/out",
            "droidctx_bin": "/usr/local/bin/droidctx",
            "platform": "darwin",
        }
        auto_sync.save_config(config)
        loaded = auto_sync.load_config()
        assert loaded == config

    def test_load_missing_returns_empty(self, tmp_path, monkeypatch):
        from droidctx import auto_sync

        monkeypatch.setattr(auto_sync, "CONFIG_FILE", tmp_path / "nope.yaml")
        assert auto_sync.load_config() == {}

    def test_resolve_paths_defaults_output_to_keyfile_parent(self, tmp_path):
        from droidctx.auto_sync import resolve_paths

        kf = tmp_path / "credentials.yaml"
        kf.touch()
        keyfile, output_dir = resolve_paths(kf, None)
        assert output_dir == kf.parent.resolve()

    def test_resolve_paths_explicit_output(self, tmp_path):
        from droidctx.auto_sync import resolve_paths

        kf = tmp_path / "credentials.yaml"
        out = tmp_path / "custom"
        keyfile, output_dir = resolve_paths(kf, out)
        assert output_dir == out.resolve()

    def test_find_droidctx_binary(self):
        from droidctx.auto_sync import find_droidctx_binary

        with patch("shutil.which", return_value="/usr/local/bin/droidctx"):
            assert find_droidctx_binary() == "/usr/local/bin/droidctx"

    def test_find_droidctx_binary_not_found(self):
        from droidctx.auto_sync import find_droidctx_binary

        with patch("shutil.which", return_value=None):
            assert find_droidctx_binary() is None

    def test_get_last_run_time_no_log(self, tmp_path, monkeypatch):
        from droidctx import auto_sync

        monkeypatch.setattr(auto_sync, "LOG_FILE", tmp_path / "nope.log")
        assert auto_sync.get_last_run_time() is None

    def test_get_last_run_time_parses_last_line(self, tmp_path, monkeypatch):
        from droidctx import auto_sync

        log = tmp_path / "auto-sync.log"
        log.write_text("first line\nsecond line\nlast line\n")
        monkeypatch.setattr(auto_sync, "LOG_FILE", log)
        assert auto_sync.get_last_run_time() == "last line"

    def test_get_last_run_time_empty_log(self, tmp_path, monkeypatch):
        from droidctx import auto_sync

        log = tmp_path / "auto-sync.log"
        log.write_text("")
        monkeypatch.setattr(auto_sync, "LOG_FILE", log)
        assert auto_sync.get_last_run_time() is None


# ---------------------------------------------------------------------------
# Scheduler tests (all subprocess calls mocked)
# ---------------------------------------------------------------------------

class TestLaunchdScheduler:
    def test_install_writes_plist_and_loads(self, tmp_path, monkeypatch):
        from droidctx import scheduler, auto_sync

        plist = tmp_path / "io.drdroid.droidctx.auto-sync.plist"
        monkeypatch.setattr(scheduler, "PLIST_PATH", plist)
        monkeypatch.setattr(auto_sync, "LOG_FILE", tmp_path / "auto-sync.log")

        config = {
            "droidctx_bin": "/usr/local/bin/droidctx",
            "keyfile": "/tmp/k.yaml",
            "output_dir": "/tmp/out",
            "interval_minutes": 10,
        }

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            s = scheduler.LaunchdScheduler()
            s.install(config)

        assert plist.exists()
        content = plist.read_text()
        assert "<integer>600</integer>" in content
        assert "/usr/local/bin/droidctx" in content
        mock_run.assert_called_once()
        assert "launchctl" in mock_run.call_args[0][0]

    def test_uninstall_removes_plist(self, tmp_path, monkeypatch):
        from droidctx import scheduler

        plist = tmp_path / "io.drdroid.droidctx.auto-sync.plist"
        plist.write_text("<plist/>")
        monkeypatch.setattr(scheduler, "PLIST_PATH", plist)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            s = scheduler.LaunchdScheduler()
            s.uninstall()

        assert not plist.exists()
        mock_run.assert_called_once()

    def test_is_active(self, tmp_path, monkeypatch):
        from droidctx import scheduler

        plist = tmp_path / "io.drdroid.droidctx.auto-sync.plist"
        monkeypatch.setattr(scheduler, "PLIST_PATH", plist)

        s = scheduler.LaunchdScheduler()
        assert not s.is_active()

        plist.write_text("<plist/>")
        assert s.is_active()


class TestCronScheduler:
    def test_install_adds_cron_entry(self, monkeypatch):
        from droidctx import scheduler, auto_sync

        monkeypatch.setattr(auto_sync, "LOG_FILE", Path("/tmp/auto-sync.log"))

        config = {
            "droidctx_bin": "/usr/local/bin/droidctx",
            "keyfile": "/tmp/k.yaml",
            "output_dir": "/tmp/out",
            "interval_minutes": 15,
        }

        with patch("subprocess.run") as mock_run:
            # First call: crontab -l returns empty
            # Second call: crontab - writes new content
            mock_run.side_effect = [
                MagicMock(returncode=1, stdout="", stderr=""),  # no existing crontab
                MagicMock(returncode=0),  # write
            ]
            s = scheduler.CronScheduler()
            s.install(config)

        write_call = mock_run.call_args_list[1]
        written = write_call.kwargs.get("input", "")
        assert "droidctx-auto-sync" in written
        assert "*/15" in written

    def test_uninstall_removes_marker(self):
        from droidctx import scheduler

        existing = "0 * * * * something\n*/30 * * * * droidctx sync >> log 2>&1 # droidctx-auto-sync\n"

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=existing),  # read
                MagicMock(returncode=0),  # write
            ]
            s = scheduler.CronScheduler()
            s.uninstall()

        write_call = mock_run.call_args_list[1]
        written = write_call.kwargs.get("input", "")
        assert "droidctx-auto-sync" not in written
        assert "something" in written

    def test_is_active(self):
        from droidctx import scheduler

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="*/30 * * * * cmd # droidctx-auto-sync\n",
            )
            s = scheduler.CronScheduler()
            assert s.is_active()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            s = scheduler.CronScheduler()
            assert not s.is_active()


class TestGetScheduler:
    def test_darwin(self):
        from droidctx import scheduler

        with patch.object(scheduler.sys, "platform", "darwin"):
            s = scheduler.get_scheduler()
            assert isinstance(s, scheduler.LaunchdScheduler)

    def test_linux(self):
        from droidctx import scheduler

        with patch.object(scheduler.sys, "platform", "linux"):
            s = scheduler.get_scheduler()
            assert isinstance(s, scheduler.CronScheduler)

    def test_windows_raises(self):
        from droidctx import scheduler

        with patch.object(scheduler.sys, "platform", "win32"):
            with pytest.raises(NotImplementedError):
                scheduler.get_scheduler()


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------

class TestAutoSyncCLI:
    def test_enable_missing_keyfile(self, tmp_path):
        result = runner.invoke(
            app,
            ["auto-sync", "enable", "--keyfile", str(tmp_path / "nope.yaml")],
        )
        assert result.exit_code == 1
        assert "not found" in result.output

    @patch("droidctx.auto_sync.find_droidctx_binary", return_value=None)
    def test_enable_binary_not_found(self, _mock_bin, tmp_path):
        kf = tmp_path / "credentials.yaml"
        kf.write_text("test: true")
        result = runner.invoke(
            app,
            ["auto-sync", "enable", "--keyfile", str(kf)],
        )
        assert result.exit_code == 1
        assert "Could not find" in result.output

    @patch("droidctx.scheduler.get_scheduler")
    @patch("droidctx.auto_sync.find_droidctx_binary", return_value="/usr/local/bin/droidctx")
    @patch("droidctx.auto_sync.save_config")
    def test_enable_success(self, mock_save, _mock_bin, mock_get_sched, tmp_path):
        kf = tmp_path / "credentials.yaml"
        kf.write_text("test: true")

        mock_scheduler = MagicMock()
        mock_scheduler.is_active.return_value = False
        mock_get_sched.return_value = mock_scheduler

        result = runner.invoke(
            app,
            ["auto-sync", "enable", "--keyfile", str(kf), "--interval", "10"],
        )
        assert result.exit_code == 0
        assert "enabled" in result.output.lower()
        mock_scheduler.install.assert_called_once()
        mock_save.assert_called_once()

    @patch("droidctx.scheduler.get_scheduler")
    @patch("droidctx.auto_sync.load_config", return_value={"enabled": False})
    @patch("droidctx.auto_sync.save_config")
    def test_disable_when_not_enabled(self, _mock_save, _mock_load, mock_get_sched):
        mock_scheduler = MagicMock()
        mock_scheduler.is_active.return_value = False
        mock_get_sched.return_value = mock_scheduler

        result = runner.invoke(app, ["auto-sync", "disable"])
        assert result.exit_code == 0
        assert "not currently enabled" in result.output.lower()

    @patch("droidctx.scheduler.get_scheduler")
    @patch("droidctx.auto_sync.load_config", return_value={"enabled": True})
    @patch("droidctx.auto_sync.save_config")
    def test_disable_success(self, mock_save, _mock_load, mock_get_sched):
        mock_scheduler = MagicMock()
        mock_scheduler.is_active.return_value = True
        mock_get_sched.return_value = mock_scheduler

        result = runner.invoke(app, ["auto-sync", "disable"])
        assert result.exit_code == 0
        assert "disabled" in result.output.lower()
        mock_scheduler.uninstall.assert_called_once()

    @patch("droidctx.scheduler.get_scheduler")
    @patch("droidctx.auto_sync.load_config", return_value={})
    def test_status_not_configured(self, _mock_load, _mock_sched):
        result = runner.invoke(app, ["auto-sync", "status"])
        assert result.exit_code == 0
        assert "not been configured" in result.output.lower()

    @patch("droidctx.auto_sync.get_last_run_time", return_value="2026-03-06 14:00:00")
    @patch("droidctx.scheduler.get_scheduler")
    @patch("droidctx.auto_sync.load_config")
    def test_status_shows_info(self, mock_load, mock_get_sched, _mock_last):
        mock_load.return_value = {
            "enabled": True,
            "interval_minutes": 30,
            "keyfile": "/tmp/k.yaml",
            "output_dir": "/tmp/out",
            "droidctx_bin": "/usr/local/bin/droidctx",
            "platform": "darwin",
        }
        mock_scheduler = MagicMock()
        mock_scheduler.is_active.return_value = True
        mock_get_sched.return_value = mock_scheduler

        result = runner.invoke(app, ["auto-sync", "status"])
        assert result.exit_code == 0
        assert "30" in result.output
        assert "/tmp/k.yaml" in result.output

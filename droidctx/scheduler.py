"""Platform-specific scheduler backends for auto-sync."""

import abc
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any


class Scheduler(abc.ABC):
    """Abstract base for OS-level periodic job schedulers."""

    @abc.abstractmethod
    def install(self, config: dict[str, Any]) -> None:
        """Register the periodic sync job."""

    @abc.abstractmethod
    def uninstall(self) -> None:
        """Remove the periodic sync job."""

    @abc.abstractmethod
    def is_active(self) -> bool:
        """Return True if the job is currently registered."""


# ---------------------------------------------------------------------------
# macOS launchd
# ---------------------------------------------------------------------------

PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / "io.drdroid.droidctx.auto-sync.plist"

_PLIST_TEMPLATE = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
      "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
    <plist version="1.0">
    <dict>
        <key>Label</key>
        <string>io.drdroid.droidctx.auto-sync</string>
        <key>ProgramArguments</key>
        <array>
            <string>{droidctx_bin}</string>
            <string>sync</string>
            <string>--keyfile</string>
            <string>{keyfile}</string>
            <string>--path</string>
            <string>{output_dir}</string>
        </array>
        <key>StartInterval</key>
        <integer>{interval_seconds}</integer>
        <key>StandardOutPath</key>
        <string>{log_file}</string>
        <key>StandardErrorPath</key>
        <string>{log_file}</string>
    </dict>
    </plist>
""")


class LaunchdScheduler(Scheduler):
    """macOS launchd backend."""

    def install(self, config: dict[str, Any]) -> None:
        from droidctx.auto_sync import LOG_FILE

        plist_content = _PLIST_TEMPLATE.format(
            droidctx_bin=config["droidctx_bin"],
            keyfile=config["keyfile"],
            output_dir=config["output_dir"],
            interval_seconds=config["interval_minutes"] * 60,
            log_file=str(LOG_FILE),
        )
        PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        PLIST_PATH.write_text(plist_content)
        subprocess.run(
            ["launchctl", "load", str(PLIST_PATH)],
            check=True,
            capture_output=True,
        )

    def uninstall(self) -> None:
        if PLIST_PATH.exists():
            subprocess.run(
                ["launchctl", "unload", str(PLIST_PATH)],
                check=True,
                capture_output=True,
            )
            PLIST_PATH.unlink()

    def is_active(self) -> bool:
        return PLIST_PATH.exists()


# ---------------------------------------------------------------------------
# Linux cron
# ---------------------------------------------------------------------------

CRON_MARKER = "# droidctx-auto-sync"


class CronScheduler(Scheduler):
    """Linux crontab backend."""

    def _read_crontab(self) -> str:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return ""
        return result.stdout

    def _write_crontab(self, content: str) -> None:
        subprocess.run(
            ["crontab", "-"],
            input=content,
            check=True,
            text=True,
            capture_output=True,
        )

    def install(self, config: dict[str, Any]) -> None:
        from droidctx.auto_sync import LOG_FILE

        # Remove old entry first
        existing = self._read_crontab()
        lines = [l for l in existing.splitlines() if CRON_MARKER not in l]

        cmd = (
            f"{config['droidctx_bin']} sync "
            f"--keyfile {config['keyfile']} "
            f"--path {config['output_dir']}"
        )
        cron_line = f"*/{config['interval_minutes']} * * * * {cmd} >> {LOG_FILE} 2>&1 {CRON_MARKER}"
        lines.append(cron_line)

        self._write_crontab("\n".join(lines) + "\n")

    def uninstall(self) -> None:
        existing = self._read_crontab()
        lines = [l for l in existing.splitlines() if CRON_MARKER not in l]
        self._write_crontab("\n".join(lines) + "\n" if lines else "")

    def is_active(self) -> bool:
        return CRON_MARKER in self._read_crontab()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_scheduler() -> Scheduler:
    """Return the appropriate scheduler for the current platform."""
    if sys.platform == "darwin":
        return LaunchdScheduler()
    elif sys.platform.startswith("linux"):
        return CronScheduler()
    else:
        raise NotImplementedError(f"Auto-sync is not supported on {sys.platform}")

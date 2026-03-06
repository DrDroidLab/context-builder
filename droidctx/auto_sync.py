"""Auto-sync configuration and orchestration."""

import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

CONFIG_DIR = Path.home() / ".config" / "droidctx"
CONFIG_FILE = CONFIG_DIR / "auto-sync.yaml"
LOG_FILE = CONFIG_DIR / "auto-sync.log"


def load_config() -> dict[str, Any]:
    """Load auto-sync config from disk. Returns empty dict if missing."""
    if not CONFIG_FILE.exists():
        return {}
    return yaml.safe_load(CONFIG_FILE.read_text()) or {}


def save_config(config: dict[str, Any]) -> None:
    """Write auto-sync config to disk, creating directory if needed."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))


def resolve_paths(keyfile: Path, output_dir: Optional[Path]) -> tuple[Path, Path]:
    """Return (keyfile, output_dir) as absolute paths.

    If output_dir is None, defaults to the keyfile's parent directory.
    """
    keyfile = keyfile.resolve()
    if output_dir is None:
        output_dir = keyfile.parent.resolve()
    else:
        output_dir = output_dir.resolve()
    return keyfile, output_dir


def find_droidctx_binary() -> Optional[str]:
    """Locate the droidctx executable on $PATH."""
    return shutil.which("droidctx")


def get_last_run_time() -> Optional[str]:
    """Parse the log file and return the timestamp of the last run, or None."""
    if not LOG_FILE.exists():
        return None
    try:
        text = LOG_FILE.read_text().strip()
        if not text:
            return None
        # Return the last non-empty line (most recent log entry)
        for line in reversed(text.splitlines()):
            line = line.strip()
            if line:
                return line
        return None
    except OSError:
        return None


def build_config(
    *,
    keyfile: Path,
    output_dir: Path,
    interval_minutes: int,
    droidctx_bin: str,
) -> dict[str, Any]:
    """Build a config dict ready to be saved."""
    return {
        "enabled": True,
        "interval_minutes": interval_minutes,
        "keyfile": str(keyfile),
        "output_dir": str(output_dir),
        "droidctx_bin": droidctx_bin,
        "platform": sys.platform,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

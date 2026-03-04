"""Credential loading and validation."""

from pathlib import Path
from typing import Any

import yaml

from droidctx.constants import CONNECTOR_CREDENTIALS


def load_credentials(keyfile: Path) -> dict[str, dict[str, Any]]:
    """Load and parse credentials YAML file.

    Returns dict of connector_name -> {type, ...credential_fields}.
    """
    if not keyfile.exists():
        raise FileNotFoundError(f"Credentials file not found: {keyfile}")

    with open(keyfile, "r") as f:
        data = yaml.safe_load(f)

    if not data or not isinstance(data, dict):
        return {}

    return data


def validate_credentials(credentials: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    """Validate credentials format and required fields.

    Returns list of validation errors (empty if all valid).
    Each error is {connector: str, message: str}.
    """
    errors = []

    for name, config in credentials.items():
        if not isinstance(config, dict):
            errors.append({"connector": name, "message": "Must be a YAML mapping"})
            continue

        conn_type = config.get("type")
        if not conn_type:
            errors.append({"connector": name, "message": "Missing 'type' field"})
            continue

        if conn_type not in CONNECTOR_CREDENTIALS:
            errors.append({
                "connector": name,
                "message": f"Unknown connector type: {conn_type}. Run 'droidctx list-connectors' to see supported types.",
            })
            continue

        spec = CONNECTOR_CREDENTIALS[conn_type]

        # _cli_mode connectors only require fields not in cli_mode_optional
        cli_mode = config.get("_cli_mode", False)
        cli_mode_optional = set(spec.get("cli_mode_optional", []))

        for field in spec["required"]:
            if cli_mode and field in cli_mode_optional:
                continue
            if field not in config or not config[field]:
                errors.append({"connector": name, "message": f"Missing required field: {field}"})

    return errors

"""CLI tool detection for connectors that need external binaries."""

import shutil

from droidctx.constants import CLI_TOOL_INSTALL_HINTS, CONNECTOR_CREDENTIALS


def check_cli_tool(tool: str) -> bool:
    """Check if a CLI tool is available on PATH."""
    return shutil.which(tool) is not None


def check_required_tools(connector_configs: dict) -> list[dict[str, str]]:
    """Check all required CLI tools for configured connectors.

    Returns list of warnings: {connector, tool, hint}.
    """
    warnings = []
    checked = set()

    for name, config in connector_configs.items():
        conn_type = config.get("type", "")
        spec = CONNECTOR_CREDENTIALS.get(conn_type)
        if not spec or not spec["cli_tool"]:
            continue

        tool = spec["cli_tool"]
        if tool in checked:
            continue
        checked.add(tool)

        if not check_cli_tool(tool):
            warnings.append({
                "connector": name,
                "tool": tool,
                "hint": CLI_TOOL_INSTALL_HINTS.get(tool, ""),
            })

    return warnings

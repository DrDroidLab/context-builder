"""Tests for CLI tool detection."""

from droidctx.cli_tools import check_cli_tool, check_required_tools


class TestCheckCliTool:
    def test_existing_tool(self):
        assert check_cli_tool("python") is True

    def test_nonexistent_tool(self):
        assert check_cli_tool("nonexistent_tool_xyz_123") is False


class TestCheckRequiredTools:
    def test_no_cli_tools_needed(self):
        configs = {"grafana": {"type": "GRAFANA"}}
        warnings = check_required_tools(configs)
        assert warnings == []

    def test_missing_tool_warning(self):
        configs = {"k8s": {"type": "KUBERNETES"}}
        # kubectl may or may not be installed, just check format
        warnings = check_required_tools(configs)
        for w in warnings:
            assert "connector" in w
            assert "tool" in w
            assert "hint" in w

    def test_deduplicates_tool_checks(self):
        configs = {
            "cw1": {"type": "CLOUDWATCH"},
            "cw2": {"type": "CLOUDWATCH"},
            "eks1": {"type": "EKS"},
        }
        # All need 'aws' - should only check once
        warnings = check_required_tools(configs)
        aws_warnings = [w for w in warnings if w["tool"] == "aws"]
        assert len(aws_warnings) <= 1

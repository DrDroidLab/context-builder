# Development Guide

## Prerequisites

- Python 3.9+
- pip

## Setup

```bash
# Clone the repo
git clone https://github.com/DrDroidLab/context-builder.git
cd context-builder

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Verify local install (should show version with +local suffix)
droidctx --version
# => droidctx 0.1.0+local
```

The `+local` suffix confirms you're running from source. A released install shows just `0.1.0`.

## Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run a specific test file
pytest tests/test_markdown_generator.py -v

# Run with coverage
pytest tests/ --cov=droidctx --cov-report=term-missing
```

### Test Files

| File | Covers |
|------|--------|
| `test_init.py` | `droidctx init` directory/file creation |
| `test_config.py` | Credential loading and validation |
| `test_check.py` | `droidctx check` credential verification |
| `test_credential_mapper.py` | YAML config to extractor kwarg mapping |
| `test_cli_tools.py` | CLI tool detection (kubectl, aws, etc.) |
| `test_cli_mode_validation.py` | K8s CLI mode validation |
| `test_auto_detect.py` | Auto-detection of connectors from local CLI tools |
| `test_k8s_cli_extractor.py` | Native kubectl-based extraction |
| `test_markdown_generator.py` | Markdown file generation and formatting |
| `test_service_crossref.py` | Cross-connector service matching |
| `test_sync_engine.py` | Full sync pipeline orchestration |

## Manual Testing

```bash
# Initialize a test workspace
droidctx init --path /tmp/test-ctx

# List available connectors
droidctx list-connectors

# Show details for a specific connector type
droidctx list-connectors --type POSTGRES

# Validate credentials
droidctx check --keyfile /tmp/test-ctx/droidctx-context/credentials.yaml

# Run a sync (requires configured credentials)
droidctx sync --keyfile /tmp/test-ctx/droidctx-context/credentials.yaml --path /tmp/test-ctx

# Dry run (no files written)
droidctx sync --keyfile <path> --dry-run

# Sync specific connectors only
droidctx sync --keyfile <path> --connectors postgres_main,grafana_prod
```

## Project Structure

```
droidctx/
  __init__.py             # Version definition + local install detection
  main.py                 # CLI entry point (Typer app)
  sync_engine.py          # Orchestrates extraction and generation
  markdown_generator.py   # Transforms assets into .md files
  extractor_runner.py     # Runs drdroid-debug-toolkit extractors
  credential_mapper.py    # Maps YAML credentials to extractor kwargs
  config.py               # Credential loading and validation
  constants.py            # Connector type definitions
  auto_detect.py          # Auto-detect connectors from CLI tools
  cli_tools.py            # CLI tool detection helpers
  k8s_cli_extractor.py    # Native kubectl-based K8s extractor
  progress.py             # Progress display utilities
tests/                    # Test suite (pytest)
```

## Generated File Format

Every generated `.md` file includes a YAML frontmatter metadata header:

```yaml
---
synced_at: 2025-01-15T10:30:00Z
droidctx_version: 0.1.0
---
```

This helps agents determine data freshness before using the context.

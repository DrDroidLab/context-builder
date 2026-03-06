"""Orchestrates the full sync flow: credentials -> extraction -> markdown."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from rich.console import Console

from droidctx.cli_tools import check_required_tools
from droidctx.config import load_credentials, validate_credentials
from droidctx.constants import CONNECTOR_CREDENTIALS
from droidctx.extractor_runner import run_extractor
from droidctx.markdown_generator import MarkdownGenerator
from droidctx.progress import SyncProgress, print_cli_tool_warnings, print_results_table

logger = logging.getLogger(__name__)


def sync(
    keyfile: Path,
    output_dir: Path,
    connector_filter: list[str] | None = None,
    dry_run: bool = False,
    verbose: bool = False,
    console: Console | None = None,
) -> dict[str, dict[str, Any]]:
    """Run the full sync pipeline.

    Returns dict of connector_name -> {connector_type, assets, error}.
    """
    console = console or Console()

    # Suppress noisy toolkit logs unless verbose
    if not verbose:
        for noisy in [
            "drdroid_debug_toolkit",
            "core",
            "urllib3",
            "datadog_api_client",
        ]:
            logging.getLogger(noisy).setLevel(logging.CRITICAL)

    # 1. Load and validate credentials
    console.print("[bold]Loading credentials...[/]")
    credentials = load_credentials(keyfile)
    errors = validate_credentials(credentials)

    if errors:
        console.print("[red]Credential validation errors:[/]")
        for err in errors:
            console.print(f"  [red]x[/] {err['connector']}: {err['message']}")
        console.print()

    # Filter to valid connectors only
    valid_connectors = {
        name: config for name, config in credentials.items()
        if not any(e["connector"] == name for e in errors)
        and config.get("type") in CONNECTOR_CREDENTIALS
    }

    # Apply connector filter if specified
    if connector_filter:
        filter_set = set(connector_filter)
        unknown = filter_set - set(valid_connectors.keys())
        if unknown:
            console.print(f"[yellow]Unknown connectors (skipped): {', '.join(unknown)}[/]")
        valid_connectors = {k: v for k, v in valid_connectors.items() if k in filter_set}

    if not valid_connectors:
        console.print("[red]No valid connectors to sync.[/]")
        return {}

    console.print(f"[bold]Found {len(valid_connectors)} connector(s) to sync[/]")

    # 2. Check CLI tools
    tool_warnings = check_required_tools(valid_connectors)
    print_cli_tool_warnings(console, tool_warnings)

    # 3. Dry run - just show what would be synced
    if dry_run:
        console.print("\n[yellow]Dry run - no files will be written[/]\n")
        for name, config in valid_connectors.items():
            console.print(f"  Would sync: [bold]{name}[/] ({config['type']})")
        console.print()
        return {}

    # 4. Run extractors with progress
    start_time = time.monotonic()
    results: dict[str, dict[str, Any]] = {}
    generator = MarkdownGenerator(output_dir)

    with SyncProgress(console) as progress:
        for name, config in valid_connectors.items():
            progress.add_connector(name, config["type"])

        # Run extractors in parallel
        with ThreadPoolExecutor(max_workers=min(4, len(valid_connectors))) as executor:
            futures = {}
            for name, config in valid_connectors.items():
                conn_type = config["type"]
                progress.update(name, "starting...", advance=10)

                def _run(n=name, ct=conn_type, cfg=config):
                    return n, ct, run_extractor(
                        connector_name=n,
                        connector_type=ct,
                        yaml_config=cfg,
                        progress_callback=None,
                        verbose=verbose,
                    )

                futures[executor.submit(_run)] = name

            for future in as_completed(futures):
                connector_name = futures[future]
                try:
                    name, conn_type, assets = future.result()
                    results[name] = {
                        "connector_type": conn_type,
                        "assets": assets,
                        "error": None,
                    }
                    progress.complete(name, f"{sum(len(v) for v in assets.values() if isinstance(v, dict))} resources")

                    # Generate markdown for this connector
                    try:
                        generator.generate_all(name, conn_type, assets)
                    except Exception as e:
                        logger.error(f"Markdown generation failed for {name}: {e}")

                except Exception as e:
                    logger.error(f"Extraction failed for {connector_name}: {e}")
                    results[connector_name] = {
                        "connector_type": valid_connectors[connector_name]["type"],
                        "assets": {},
                        "error": str(e),
                    }
                    progress.fail(connector_name, str(e))

    # 5. Cross-reference services across connectors
    try:
        generator.generate_service_crossref(results)
    except Exception as e:
        logger.error(f"Service cross-reference failed: {e}")

    # 6. Generate overview
    generator.generate_overview(results)

    elapsed = time.monotonic() - start_time

    # 7. Print results
    print_results_table(console, results)

    # 8. Print stats
    total_resources = sum(
        sum(len(v) for v in r["assets"].values() if isinstance(v, dict))
        for r in results.values() if not r.get("error")
    )
    ok_count = sum(1 for r in results.values() if not r.get("error"))
    fail_count = sum(1 for r in results.values() if r.get("error"))

    console.print(f"\n[bold green]Sync complete![/] {ok_count} connectors synced, "
                  f"{total_resources} resources discovered in {elapsed:.1f}s")
    if fail_count:
        console.print(f"[yellow]{fail_count} connector(s) failed[/]")

    # 9. Print suggested CLAUDE.md prompt
    console.print("\n[bold]Add this to your CLAUDE.md or agent prompt:[/]\n")
    console.print(f'[dim]  My production infrastructure context is in {output_dir / "resources"}/.[/]')
    console.print("[dim]  Refer to this when investigating issues, writing queries, or understanding system topology.[/]")
    console.print("\n[bold]Optional (if you want agent to refresh the context):[/]\n")
    console.print("[dim]  Before using context files, check the synced_at timestamp in the YAML frontmatter.[/]")
    console.print("[dim]  If the data is older than 6 hours, run `droidctx sync` to refresh the context.[/]\n")

    return results

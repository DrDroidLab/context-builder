"""droidctx CLI - Infrastructure context builder for coding agents."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from droidctx import __version__
from droidctx.constants import CONNECTOR_CREDENTIALS, RESOURCE_DIRS

app = typer.Typer(
    name="droidctx",
    help="Build infrastructure context for Claude Code and coding agents.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


def version_callback(value: bool):
    if value:
        console.print(f"droidctx {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", "-v", callback=version_callback, is_eager=True, help="Show version"),
):
    """Build infrastructure context for Claude Code and coding agents."""
    pass


@app.command()
def init(
    path: Path = typer.Option(
        Path("./droidctx-context"),
        "--path",
        "-p",
        help="Directory to create the context structure in",
    ),
):
    """Initialize folder structure and credentials template."""
    path = path.resolve()

    # Create base directory
    path.mkdir(parents=True, exist_ok=True)

    # Create resources subdirectories
    resources_dir = path / "resources"
    resources_dir.mkdir(exist_ok=True)

    for dirname in RESOURCE_DIRS:
        (resources_dir / dirname).mkdir(exist_ok=True)

    # Generate credentials template
    creds_file = path / "credentials.yaml"
    if not creds_file.exists():
        _write_credentials_template(creds_file)
        console.print(f"  Created credentials template: {creds_file}", style="dim")
    else:
        console.print(f"  Credentials file already exists: {creds_file}", style="dim")

    # Write placeholder overview
    overview_file = resources_dir / "overview.md"
    if not overview_file.exists():
        overview_file.write_text("# Infrastructure Overview\n\nRun `droidctx sync` to populate this file.\n")

    console.print(f"\n[bold green]Initialized droidctx context at:[/] {path}\n")
    console.print("Next steps:")
    console.print(f"  1. Auto-detect CLIs:  [bold]droidctx detect --keyfile {creds_file}[/]")
    console.print(f"  2. Edit credentials:  [bold]{creds_file}[/]")
    console.print(f"  3. Sync metadata:     [bold]droidctx sync --keyfile {creds_file}[/]")
    console.print()


@app.command()
def sync(
    keyfile: Path = typer.Option(Path("./droidctx-context/credentials.yaml"), "--keyfile", "-k", help="Path to credentials YAML file"),
    path: Optional[Path] = typer.Option(None, "--path", "-p", help="Output directory (default: same as keyfile dir)"),
    connectors: Optional[str] = typer.Option(None, "--connectors", "-c", help="Comma-separated connector names to sync"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be synced without writing files"),
    verbose: bool = typer.Option(False, "--verbose", help="Show detailed extraction logs"),
):
    """Sync infrastructure metadata and generate .md context files."""
    import logging
    from droidctx.sync_engine import sync as run_sync

    if verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s")

    keyfile = keyfile.resolve()
    if not keyfile.exists():
        console.print(f"[red]Credentials file not found: {keyfile}[/]")
        raise typer.Exit(1)

    output_dir = (path or keyfile.parent).resolve()
    connector_filter = [c.strip() for c in connectors.split(",")] if connectors else None

    run_sync(
        keyfile=keyfile,
        output_dir=output_dir,
        connector_filter=connector_filter,
        dry_run=dry_run,
        verbose=verbose,
        console=console,
    )


@app.command()
def check(
    keyfile: Path = typer.Option(Path("./droidctx-context/credentials.yaml"), "--keyfile", "-k", help="Path to credentials YAML file"),
):
    """Validate credentials and test connectivity."""
    from droidctx.config import load_credentials, validate_credentials
    from droidctx.cli_tools import check_required_tools

    keyfile = keyfile.resolve()
    if not keyfile.exists():
        console.print(f"[red]Credentials file not found: {keyfile}[/]")
        raise typer.Exit(1)

    try:
        credentials = load_credentials(keyfile)
    except Exception as e:
        console.print(f"[red]Failed to load credentials: {e}[/]")
        raise typer.Exit(1)

    # Validate format
    errors = validate_credentials(credentials)

    # Check CLI tools
    tool_warnings = check_required_tools(credentials)

    # Display results
    table = Table(title="Credential Check")
    table.add_column("Connector", style="bold")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Notes")

    for name, config in credentials.items():
        conn_type = config.get("type", "MISSING")
        connector_errors = [e for e in errors if e["connector"] == name]
        connector_tool_warnings = [w for w in tool_warnings if w["connector"] == name]

        if connector_errors:
            notes = "; ".join(e["message"] for e in connector_errors)
            table.add_row(name, conn_type, "[red]INVALID[/]", notes)
        elif connector_tool_warnings:
            notes = "; ".join(f"Missing CLI: {w['tool']}" for w in connector_tool_warnings)
            table.add_row(name, conn_type, "[yellow]WARNING[/]", notes)
        else:
            table.add_row(name, conn_type, "[green]OK[/]", "Credentials valid")

    console.print()
    console.print(table)
    console.print()

    if errors:
        console.print(f"[red]{len(errors)} error(s) found[/]")
        raise typer.Exit(1)
    else:
        console.print("[green]All credentials valid[/]")


@app.command()
def detect(
    keyfile: Path = typer.Option(Path("./droidctx-context/credentials.yaml"), "--keyfile", "-k", help="Path to credentials YAML file"),
):
    """Auto-detect credentials from locally configured CLI tools (kubectl, aws, gcloud, az)."""
    from droidctx.auto_detect import run_all_detectors, merge_into_credentials, save_credentials
    from droidctx.config import load_credentials

    keyfile = keyfile.resolve()

    # Load existing credentials if file exists
    existing = {}
    if keyfile.exists():
        try:
            existing = load_credentials(keyfile)
        except (ValueError, Exception):
            existing = {}

    # Run detectors
    console.print("[bold]Scanning for CLI tools...[/]\n")

    detected = run_all_detectors()

    if not detected:
        console.print("[yellow]No configured CLI tools detected.[/]")
        console.print("[dim]Checked: kubectl, aws, gcloud, az[/]\n")
        console.print("You can manually configure connectors in:")
        console.print(f"  [bold]{keyfile}[/]\n")
        return

    # Show what was detected
    table = Table(title="Detected Connectors")
    table.add_column("Connector", style="bold")
    table.add_column("Type")
    table.add_column("Details")
    table.add_column("Status")

    needs_manual = []
    for conn in detected:
        name = conn["_connector_name"]
        ctype = conn["type"]
        manual_fields = conn.get("_needs_manual", [])

        # Build details string
        details_parts = []
        for k, v in conn.items():
            if k.startswith("_") or k == "type" or not v:
                continue
            details_parts.append(f"{k}={v}")
        details = ", ".join(details_parts[:3])

        if name in existing:
            table.add_row(name, ctype, details, "[dim]already exists[/]")
        elif manual_fields:
            table.add_row(name, ctype, details, f"[yellow]needs: {', '.join(manual_fields)}[/]")
            needs_manual.append((name, manual_fields))
        else:
            table.add_row(name, ctype, details, "[green]ready[/]")

    console.print(table)
    console.print()

    # Merge and save
    merged, added, skipped = merge_into_credentials(detected, existing)

    if not added:
        if needs_manual:
            console.print("[dim]No complete connectors to add.[/]")
        else:
            console.print("[dim]No new connectors to add (all already exist in credentials file).[/]")
    else:
        save_credentials(merged, keyfile)

        console.print(f"[bold green]Added {len(added)} connector(s) to {keyfile}[/]")
        for name in added:
            console.print(f"  + {name}")

    if needs_manual:
        console.print(f"\n[yellow]Not added (needs manual config in {keyfile}):[/]")
        for name, fields in needs_manual:
            console.print(f"  {name}: add {', '.join(fields)}")

    console.print(f"\nNext: [bold]droidctx sync -k {keyfile}[/]")
    console.print()


@app.command(name="list-connectors")
def list_connectors(
    connector_type: Optional[str] = typer.Option(None, "--type", "-t", help="Show details for a specific connector type"),
):
    """List all supported connector types."""
    if connector_type:
        connector_type = connector_type.upper()
        if connector_type not in CONNECTOR_CREDENTIALS:
            console.print(f"[red]Unknown connector type: {connector_type}[/]")
            raise typer.Exit(1)

        spec = CONNECTOR_CREDENTIALS[connector_type]
        console.print(f"\n[bold]{connector_type}[/] - {spec['description']}\n")

        table = Table(title="Credential Fields")
        table.add_column("Field", style="bold")
        table.add_column("Required")
        for field in spec["required"]:
            table.add_row(field, "[green]yes[/]")
        for field in spec["optional"]:
            table.add_row(field, "[dim]no[/]")
        if spec["cli_tool"]:
            table.add_row(f"CLI: {spec['cli_tool']}", "[yellow]needed[/]")

        console.print(table)
        console.print()
        return

    table = Table(title="Supported Connector Types")
    table.add_column("Type", style="bold")
    table.add_column("Description")
    table.add_column("CLI Tool", style="dim")

    for ctype, spec in sorted(CONNECTOR_CREDENTIALS.items()):
        table.add_row(ctype, spec["description"], spec["cli_tool"] or "-")

    console.print()
    console.print(table)
    console.print(f"\n[dim]{len(CONNECTOR_CREDENTIALS)} connectors supported. Use --type <TYPE> for details.[/]\n")


def _write_credentials_template(filepath: Path):
    """Write a credentials template YAML with all supported connector types."""
    template = """# droidctx credentials file
# Uncomment and fill in the connectors you want to sync.
# Run 'droidctx list-connectors' to see all supported types and fields.

# --- Monitoring & Observability ---

# grafana_prod:
#   type: "GRAFANA"
#   grafana_host: https://your-grafana.com
#   grafana_api_key: glsa_xxxxxxxxxxxx
#   ssl_verify: false

# datadog_prod:
#   type: "DATADOG"
#   dd_api_key: your_api_key
#   dd_app_key: your_app_key
#   dd_api_domain: datadoghq.com

# newrelic_prod:
#   type: "NEW_RELIC"
#   nr_api_key: NRAK-xxxxxxxxxxxx
#   nr_account_id: "1234567"

# cloudwatch_us:
#   type: "CLOUDWATCH"
#   region: us-east-1
#   aws_access_key: AKIAIOSFODNN7EXAMPLE
#   aws_secret_key: wJalrXUtnFEMI/K7MDENG...

# signoz_prod:
#   type: "SIGNOZ"
#   signoz_host: https://your-signoz.com
#   signoz_api_key: your_api_key

# sentry_prod:
#   type: "SENTRY"
#   sentry_api_key: your_api_key
#   sentry_org: your-org

# --- Kubernetes & Cloud ---

# k8s_production:
#   type: "KUBERNETES"
#   cluster_name: prod-cluster
#   cluster_api_server: https://k8s-api.example.com
#   cluster_token: eyJhbGciOiJSUzI1NiIs...

# eks_prod:
#   type: "EKS"
#   region: us-east-1
#   eks_cluster_name: prod-eks

# gke_prod:
#   type: "GKE"
#   gke_project_id: my-project
#   gke_cluster_name: prod-gke
#   gke_zone: us-central1-a

# argocd_prod:
#   type: "ARGOCD"
#   argocd_server: https://argocd.example.com
#   argocd_token: your_token

# azure_prod:
#   type: "AZURE"
#   azure_tenant_id: your_tenant_id
#   azure_client_id: your_client_id
#   azure_client_secret: your_client_secret
#   azure_subscription_id: your_subscription_id

# --- Databases ---

# postgres_main:
#   type: "POSTGRES"
#   host: db.example.com
#   port: 5432
#   database: production
#   user: readonly_user
#   password: secret

# mongodb_main:
#   type: "MONGODB"
#   connection_string: mongodb://user:pass@host:27017/db

# clickhouse_prod:
#   type: "CLICKHOUSE"
#   ch_host: clickhouse.example.com
#   ch_port: 8123
#   ch_user: default
#   ch_password: secret

# elasticsearch_prod:
#   type: "ELASTIC_SEARCH"
#   es_host: https://elasticsearch.example.com:9200
#   es_api_key: your_api_key

# opensearch_prod:
#   type: "OPEN_SEARCH"
#   os_host: https://opensearch.example.com:9200
#   os_username: admin
#   os_password: secret

# --- CI/CD & Project Management ---

# github_org:
#   type: "GITHUB"
#   github_token: ghp_xxxxxxxxxxxx
#   github_org: your-org

# jira_prod:
#   type: "JIRA_CLOUD"
#   jira_url: https://your-org.atlassian.net
#   jira_email: you@company.com
#   jira_api_token: your_api_token

# jenkins_prod:
#   type: "JENKINS"
#   jenkins_url: https://jenkins.example.com
#   jenkins_user: admin
#   jenkins_api_token: your_api_token

# --- Logs ---

# grafana_loki:
#   type: "GRAFANA_LOKI"
#   grafana_host: https://your-grafana.com
#   grafana_api_key: glsa_xxxxxxxxxxxx

# victoria_logs:
#   type: "VICTORIA_LOGS"
#   vl_host: https://victorialogs.example.com

# coralogix_prod:
#   type: "CORALOGIX"
#   coralogix_api_key: your_api_key
#   coralogix_domain: coralogix.com

# posthog_prod:
#   type: "POSTHOG"
#   posthog_host: https://app.posthog.com
#   posthog_api_key: phx_xxxxxxxxxxxx

# --- Google Cloud ---

# gcm_prod:
#   type: "GCM"
#   gcp_project_id: my-project
#   gcp_service_account_json: /path/to/service-account.json

# --- Generic SQL ---

# sql_analytics:
#   type: "SQL_DATABASE_CONNECTION"
#   connection_string: mysql+pymysql://user:pass@host:3306/db
"""
    filepath.write_text(template)


if __name__ == "__main__":
    app()

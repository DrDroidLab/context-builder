"""Rich progress display for sync operations."""

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskID


class SyncProgress:
    """Manages Rich progress display for multi-connector sync."""

    def __init__(self, console: Console | None = None):
        self.console = console or Console()
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description}"),
            BarColumn(),
            TextColumn("[dim]{task.fields[status]}"),
            console=self.console,
        )
        self._tasks: dict[str, TaskID] = {}

    def __enter__(self):
        self._progress.__enter__()
        return self

    def __exit__(self, *args):
        self._progress.__exit__(*args)

    def add_connector(self, name: str, connector_type: str) -> str:
        """Add a connector to track. Returns the connector name as ID."""
        task_id = self._progress.add_task(
            f"{name} ({connector_type})",
            total=100,
            status="waiting...",
        )
        self._tasks[name] = task_id
        return name

    def update(self, name: str, status: str, advance: float = 0):
        """Update connector progress."""
        if name in self._tasks:
            self._progress.update(self._tasks[name], advance=advance, status=status)

    def complete(self, name: str, status: str = "done"):
        """Mark connector as complete."""
        if name in self._tasks:
            self._progress.update(self._tasks[name], completed=100, status=f"[green]{status}[/]")

    def fail(self, name: str, error: str):
        """Mark connector as failed."""
        if name in self._tasks:
            self._progress.update(self._tasks[name], completed=100, status=f"[red]FAILED: {error[:50]}[/]")


def print_results_table(console: Console, results: dict):
    """Print final summary table of sync results."""
    table = Table(title="Sync Results")
    table.add_column("Connector", style="bold")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Resources")

    for name, result in sorted(results.items()):
        ctype = result.get("connector_type", "")
        error = result.get("error")

        if error:
            table.add_row(name, ctype, "[red]FAILED[/]", str(error)[:60])
        else:
            assets = result.get("assets", {})
            total = sum(len(v) for v in assets.values() if isinstance(v, dict))
            table.add_row(name, ctype, "[green]OK[/]", f"{total} resources")

    console.print()
    console.print(table)


def print_cli_tool_warnings(console: Console, warnings: list[dict]):
    """Print warnings about missing CLI tools."""
    if not warnings:
        return

    console.print("\n[yellow]Missing CLI tools:[/]")
    for w in warnings:
        console.print(f"  [yellow]![/] {w['tool']} (needed by {w['connector']}): {w['hint']}")
    console.print()

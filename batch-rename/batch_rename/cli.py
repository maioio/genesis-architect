from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table

from .renamer import plan_renames, execute_renames
from .config import load_config
from .log import read_log
from .exceptions import BatchRenameError

app = typer.Typer(help="Batch rename files safely. Defaults to dry-run.")
console = Console()


def _resolve_files(directory: Path, glob: str) -> list[Path]:
    files = sorted(directory.glob(glob))
    if not files:
        console.print(f"[yellow]No files matched '{glob}' in {directory}[/yellow]")
        raise typer.Exit(1)
    return files


@app.command()
def rename(
    directory: Path = typer.Argument(..., help="Directory containing files to rename"),
    search: str = typer.Option("", "--search", "-s", help="Text to search for"),
    replacement: str = typer.Option("", "--replace", "-r", help="Replacement text"),
    glob: str = typer.Option("*", "--glob", "-g", help="File glob pattern"),
    prefix: str = typer.Option("", "--prefix", help="Prefix to add"),
    suffix: str = typer.Option("", "--suffix", help="Suffix to add to stem"),
    counter: Optional[int] = typer.Option(None, "--counter", help="Add counter starting at N"),
    regex: bool = typer.Option(False, "--regex", help="Treat search as regex"),
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="Preview only (default: on)"),
    copy: bool = typer.Option(False, "--copy", help="Copy files instead of moving"),
    config: Optional[Path] = typer.Option(None, "--config", help="Path to config file"),
):
    """Preview or execute batch renames."""
    try:
        load_config(config)
        files = _resolve_files(directory, glob)
        plan = plan_renames(files, search, replacement, regex, prefix, suffix, counter)
    except BatchRenameError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    table = Table(title="Rename Plan", show_lines=True)
    table.add_column("Original", style="cyan")
    table.add_column("New Name", style="green")
    for src, dst in plan:
        changed = src.name != dst.name
        style = "" if changed else "dim"
        table.add_row(src.name, dst.name, style=style)
    console.print(table)

    if dry_run:
        console.print("[yellow]Dry-run mode - no files changed. Use --execute to apply.[/yellow]")
        return

    execute_renames(plan, copy=copy)
    console.print(f"[green]Renamed {len(plan)} file(s).[/green]")


@app.command()
def undo(
    directory: Path = typer.Argument(..., help="Directory with a .rename_log.json"),
):
    """Reverse the last rename operation in a directory."""
    try:
        entries = read_log(directory)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    for entry in reversed(entries):
        src, dst = Path(entry["to"]), Path(entry["from"])
        if src.exists():
            src.rename(dst)
            console.print(f"[green]Restored:[/green] {src.name} -> {dst.name}")
        else:
            console.print(f"[yellow]Skip (missing):[/yellow] {src.name}")


def main():
    app()

import click
from core import organize_files

@click.command()
@click.argument("directory")
@click.option("--dry-run", is_flag=True, help="Preview without moving")
def organize(directory: str, dry_run: bool):
    """Organize files in DIRECTORY by extension."""
    result = organize_files(directory, dry_run=dry_run)
    for src, dst in result.items():
        prefix = "[DRY]" if dry_run else "Moved"
        click.echo(f"{prefix}: {src} -> {dst}")
    click.echo(f"Done: {len(result)} files.")

if __name__ == "__main__":
    organize()

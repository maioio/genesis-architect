"""CLI entrypoint."""

import logging
import os
import sys
from pathlib import Path

import click

from podcast_dl import __version__
from podcast_dl.adapters.config_adapter import load_config
from podcast_dl.services.feed_service import sync_feed

if sys.platform == "win32":
    os.environ.setdefault("PYTHONUTF8", "1")


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(format="%(levelname)s: %(message)s", level=level)


@click.group()
@click.version_option(__version__, prog_name="podcast-dl")
def cli() -> None:
    """podcast-dl: download podcast episodes from RSS feeds."""


@cli.command()
@click.argument("feed_url")
@click.option("--output", "-o", default=None, help="Output directory (default: downloads/)")
@click.option("--workers", "-w", default=None, type=int, help="Max concurrent downloads")
@click.option("--limit", "-n", default=None, type=int, help="Max episodes to download")
@click.option("--state", default="downloaded.json", show_default=True,
              help="Episode state file path")
@click.option("--verbose", "-v", is_flag=True)
def download(
    feed_url: str,
    output: str | None,
    workers: int | None,
    limit: int | None,
    state: str,
    verbose: bool,
) -> None:
    """Download new episodes from FEED_URL."""
    _setup_logging(verbose)
    cfg = load_config()

    output_dir = Path(output or cfg["output_dir"])
    max_workers = workers or cfg["max_workers"]
    state_path = Path(state)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        downloaded = sync_feed(
            feed_url=feed_url,
            output_dir=output_dir,
            state_path=state_path,
            max_workers=max_workers,
            limit=limit,
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    if downloaded:
        click.echo(f"Downloaded {len(downloaded)} episode(s) to {output_dir}/")
    else:
        click.echo("No new episodes.")


def main() -> None:
    cli()

"""CLI adapter - thin wrapper over core. No business logic here."""
import click
from .core import process_file


@click.command()
@click.argument("input_file")
@click.option("--output", "-o", default=None, help="Output file path")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed output")
def cli(input_file: str, output: str | None, verbose: bool) -> None:
    """Process INPUT_FILE and print summary."""
    try:
        result = process_file(input_file, output)
        if verbose:
            click.echo(f"Lines:  {result['lines']}")
            click.echo(f"Words:  {result['words']}")
            click.echo(f"Chars:  {result['chars']}")
        else:
            click.echo(f"{result['lines']} lines, {result['words']} words")
    except FileNotFoundError as e:
        raise click.BadParameter(str(e), param_hint="INPUT_FILE") from e


def main() -> None:
    cli()

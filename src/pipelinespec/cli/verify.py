from pipelinespec.models import Answer
from pipelinespec.core import verifier
from pydantic import TypeAdapter
from pipelinespec import console
from rich.table import Table
from pathlib import Path
import click

@click.command()
@click.argument('truth', required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument('output', required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
def main(truth: Path, output: Path) -> None:

    answers = TypeAdapter(dict[str, Answer])
    report = verifier.verify(answers.validate_json(truth.read_text()), answers.validate_json(output.read_text()))
    table = Table('Check', 'Result', 'Detail', show_lines=False)

    for check in report.checks:
        table.add_row(check.name, '[green]pass[/green]' if check.passed else '[red]FAIL[/red]', check.detail)

    console.print(table)

    failed = sum(not check.passed for check in report.checks)

    if failed:
        console.print(f'[bold red]FAIL[/bold red] {failed} of {len(report.checks)} checks failed')
    else:
        console.print(f'[bold green]PASS[/bold green] all {len(report.checks)} checks passed')

    raise SystemExit(1 if failed else 0)

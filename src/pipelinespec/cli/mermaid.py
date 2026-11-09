from pipelinespec.models import AccessMap
from pipelinespec.core import mermaid
from pathlib import Path
import click

@click.command()
@click.argument('map_file', required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option('--output', '-o', type=click.Path(dir_okay=False, path_type=Path), help='Write the diagram to this file instead of printing it.')
def main(map_file: Path, output: Path | None) -> None:

    diagram = mermaid.render(AccessMap.model_validate_json(map_file.read_text()))

    if output:
        output.write_text(diagram)
    else:
        click.echo(diagram, nl=False)

if __name__ == '__main__':
    main()

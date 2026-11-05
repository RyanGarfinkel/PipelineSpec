from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from pipelinespec.core import pipeline, runner, access_map
from pipelinespec import console, log, settings
from pipelinespec.config import TraceSettings
from pipelinespec.models import Workflow
from pipelinespec.tools import git
from pathlib import Path
import logging
import click
import os

def __validate(repo: str, certificate: str | None, container: str | None, arch: str | None, output: str | None, model: str | None, n: int) -> None:

    # Constraint runs
    if n != 1 and not settings.constraints_only:
        raise click.UsageError('-n requires --constraints-only')

    # Repository
    repository = Path(repo).expanduser()
    if not os.path.exists(repository):
        raise FileNotFoundError(f'Repository not found: {repository}')

    if not os.path.exists(repository / '.github' / 'workflows'):
        raise FileNotFoundError(f'No workflows found in repository: {repository}')

    settings.repo = repository

    # Certificate

    if certificate is not None:
        settings.trace.mitm_certificate = Path(certificate).expanduser()

    if not settings.constraints_only and settings.trace.mitm_certificate is None:
        raise ValueError('MITMProxy certificate directory not provided. Use --certificate or set CERTIFICATE.')

    if not settings.constraints_only and not os.path.exists(settings.trace.mitm_certificate):
        raise FileNotFoundError(f'MITMProxy certificate directory not found: {settings.trace.mitm_certificate}')

    # Output directory

    if output is not None:
        settings.file.output = Path(output)

    os.makedirs(settings.file.output, exist_ok=True)

    # Update settings

    if container is not None:
        settings.trace.container = TraceSettings.validate_container_label(container)

    if arch is not None:
        settings.trace.arch = arch

    if model is not None:
        settings.agent.model = model

def __sample_constraints(workflows: list[Workflow], n: int) -> None:

    if n == 1:
        pipeline.get_constraints(workflows)
        return

    progress = Progress(SpinnerColumn(), TextColumn('[cyan]{task.description}'), BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(), console=console)
    bar = progress.add_task('', total=n)

    with progress:
        for sample in range(1, n + 1):
            progress.update(bar, description=f'Constraint run {sample} of {n}')
            pipeline.get_constraints(workflows, sample)
            progress.advance(bar)

def __run(trace_only: bool, n: int) -> None:

    # Workflow parsing
    workflows = Workflow.find_all(settings.repo / '.github' / 'workflows')
    phases = sum(len(workflow.jobs) for workflow in workflows)
    log(f'Found {len(workflows)} pipelines and {phases} phases.')

    # Constraints
    if settings.constraints_only:
        __sample_constraints(workflows, n)
        log('Skipping Z3 and tracing.', style='yellow')
        return

    constraints = pipeline.load_constraints(workflows) if trace_only else pipeline.get_constraints(workflows)

    # Variants
    variants = pipeline.get_variants(workflows, constraints)

    # Tracing
    log(f'Beggining trace...')

    for trace in runner.get_traces(workflows, variants):
        access_map.add(trace)
        access_map.save()

    log(f'Trace complete. Access map saved to {access_map.save()}.', style='green')

@click.command()
@click.option('--repo', '-r', required=True, help='Path to the GitHub repository.')
@click.option('--certificate', '-C', help='Path to the MITMProxy certificate directory.')
@click.option('--container', '-c', help='Container image to use for running the workflow.')
@click.option('--arch', '-a', type=click.Choice(['linux/amd64', 'linux/arm64']), help='Container architecture.')
@click.option('--output', '-o', help='Path to the output directory.')
@click.option('--model', '-m', help='Model for the agents.')
@click.option('--constraints-only', is_flag=True, help='Stop after the constraint agent. Writes constraints.json.')
@click.option('-n', 'n', type=click.IntRange(min=1), default=1, help='Requires --constraints-only if used. Controls how many times to run the constraint agent.')
@click.option('--trace-only', is_flag=True, help='Skips the constraint agent. Runs Z3, tracing and access map generation.')
@click.option('--constraints', type=click.Path(exists=True, dir_okay=False, resolve_path=True, path_type=Path), help='Path to a constraints.json from an earlier run. Required by --trace-only.')
@click.option('--verbose', '-v', is_flag=True, help='Verbose logging.')
def main(repo: str, certificate: str | None, container: str | None, arch: str | None, output: str | None, model: str | None, constraints_only: bool, n: int, trace_only: bool, constraints: Path | None, verbose: bool) -> None:

    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if trace_only and constraints is None:
        raise click.UsageError('Trace only requires --constraints.')

    if constraints is not None and not trace_only:
        raise click.UsageError('Constraints were provided but --trace-only is missing.')

    if trace_only and constraints_only:
        raise click.UsageError('Constraints only and trace only cannot be used together.')

    settings.constraints_only = constraints_only
    settings.constraints = constraints
    settings.verbose = verbose

    __validate(repo, certificate, container, arch, output, model, n)

    log(f'Analyzing [bold cyan]{git.repository() or settings.repo.name}[/bold cyan]', markup=True)

    if verbose:
        log(f'Using model {settings.agent.model} from {settings.agent.provider}')

    __run(trace_only, n)

if __name__ == '__main__':
    main()

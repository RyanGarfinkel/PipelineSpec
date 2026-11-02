from pipelinespec.config import TraceSettings
from pipelinespec.core import pipeline
from pipelinespec.models import Workflow
from pipelinespec import log, settings
from pipelinespec.tools import git
from pathlib import Path
import logging
import click
import os

def __validate(repo: str, certificate: str | None, container: str | None, arch: str | None, output: str | None, model: str | None) -> None:

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

    if not settings.variants_only and settings.trace.mitm_certificate is None:
        raise ValueError('MITMProxy certificate directory not provided. Use --certificate or set CERTIFICATE.')

    if not settings.variants_only and not os.path.exists(settings.trace.mitm_certificate):
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

def __run(trace_only: bool) -> None:

    # Workflow parsing
    workflows = Workflow.find_all(settings.repo / '.github' / 'workflows')
    phases = sum(len(workflow.jobs) for workflow in workflows)
    log(f'Found {len(workflows)} pipelines and {phases} phases.')

    # Variants
    if not trace_only:
        variants = pipeline.get_variants(workflows)
    else:
        variants = pipeline.load_variants()
    
    if settings.variants_only:
        log('Skipping tracing.', style='yellow')
        return

    # Tracing
    path = pipeline.trace(variants)

    # access map

@click.command()
@click.option('--repo', '-r', required=True, help='Path to the GitHub repository.')
@click.option('--certificate', '-C', help='Path to the MITMProxy certificate directory.')
@click.option('--container', '-c', help='Container image to use for running the workflow.')
@click.option('--arch', '-a', type=click.Choice(['linux/amd64', 'linux/arm64']), help='Container architecture.')
@click.option('--output', '-o', help='Path to the output directory.')
@click.option('--model', '-m', help='Model for the agents.')
@click.option('--variants-only', is_flag=True, help='Stop after running Z3. Writes constraints.json and variants.json.')
@click.option('--trace-only', is_flag=True, help='Skips constraint agent and Z3. Runs tracing and access map generation. Requires --variants flag.')
@click.option('--variants', type=click.Path(exists=True, dir_okay=False, resolve_path=True, path_type=Path), help='Path to JSON that specifies how to run tracing variants. Required by --trace-only.')
@click.option('--verbose', '-v', is_flag=True, help='Verbose logging.')
def main(repo: str, certificate: str | None, container: str | None, arch: str | None, output: str | None, model: str | None, variants_only: bool, trace_only: bool, variants: Path | None, verbose: bool) -> None:

    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if trace_only and variants is None:
        raise click.UsageError('Trace only requires --variants.')

    if variants is not None and not trace_only:
        raise click.UsageError('Variants were provided but was missing --trace-only.')

    if trace_only and variants_only:
        raise click.UsageError('Variants only and trace only cannot be used together.')

    settings.variants_only = variants_only
    settings.variants = variants
    settings.verbose = verbose

    __validate(repo, certificate, container, arch, output, model)

    log(f'Analyzing [bold cyan]{git.repository() or settings.repo.name}[/bold cyan]', markup=True)

    if verbose:
        log(f'Using model {settings.agent.model} from {settings.agent.provider}')

    pipeline.run()

if __name__ == '__main__':
    main()

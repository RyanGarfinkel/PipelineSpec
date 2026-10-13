from pipelinespec.models import MockedCall, TraceConfig
from pipelinespec.core import tracer
from pipelinespec import settings
from pathlib import Path
import logging as log
import click
import os

def __validate(repo: str, certificate: str | None, container: str | None, arch: str | None, output: str | None) -> None:

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

    if settings.trace.mitm_certificate is None:
        raise ValueError('MITMProxy certificate directory not provided. Use --certificate or set CERTIFICATE.')

    if not os.path.exists(settings.trace.mitm_certificate):
        raise FileNotFoundError(f'MITMProxy certificate directory not found: {settings.trace.mitm_certificate}')

    # Output directory

    if output is not None:
        settings.file.output = Path(output)

    os.makedirs(settings.file.output, exist_ok=True)
    settings.file.secrets.touch()
    settings.file.env.touch()

    # Update settings
    
    if container is not None:
        settings.trace.container = container

    if arch is not None:
        settings.trace.arch = arch

@click.command()
@click.option('--repo', '-r', required=True, help='Path to the GitHub repository.')
@click.option('--certificate', '-C', help='Path to the MITMProxy certificate directory.')
@click.option('--container', '-c', help='Container image to use for running the workflow.')
@click.option('--arch', '-a', type=click.Choice(['linux/amd64', 'linux/arm64']), help='Container architecture.')
@click.option('--output', '-o', help='Path to the output directory.')
@click.option('--verbose', '-v', is_flag=True, help='Verbose logging.')
def main(repo: str, certificate: str | None, container: str | None, arch: str | None, output: str | None, verbose: bool) -> None:

    if verbose:
        log.getLogger().setLevel(log.DEBUG)

    __validate(repo, certificate, container, arch, output)

    npm_publish = MockedCall(
        method='PUT',
        url='https://registry.npmjs.org/dafink-ui',
        status=200,
        headers={'content-type': 'application/json'},
        body={'ok': True},
    )

    tracer.run(TraceConfig(workflow='Publish CLI', job='publish', mocked_calls=[npm_publish]))

if __name__ == '__main__':
    main()
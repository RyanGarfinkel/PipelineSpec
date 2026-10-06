from pipelinespec.models import Workflow
from pipelinespec import settings
from pathlib import Path
import logging as log
import click
import os

@click.command()
@click.option('--repo', '-r', required=True, help='Path to the GitHub repository.')
@click.option('--certificate', '-C', help='Path to the MITMProxy certificate directory.')
@click.option('--container', '-c', help='Container image to use for running the workflow.')
@click.option('--arch', '-a', type=click.Choice(['linux/amd64', 'linux/arm64']), help='Container architecture.')
@click.option('--output', '-o', help='Path to the output directory.')
@click.option('--verbose', '-v', is_flag=True, help='Verbose logging.')
def main(repo: str, certificate: str | None, container: str | None, arch: str | None, output: str | None, verbose: bool) -> None:

    # Input validation

    if verbose:
        log.getLogger().setLevel(log.DEBUG)

    repository = Path(repo).expanduser()

    if not os.path.exists(repository):
        raise FileNotFoundError(f'Repository not found: {repository}')

    if not os.path.exists(repository / '.github' / 'workflows'):
        raise FileNotFoundError(f'No workflows found in repository: {repository}')

    if certificate is not None:
        settings.certificate = Path(certificate).expanduser()

    if settings.certificate is None:
        raise ValueError('MITMProxy certificate directory not provided. Use --certificate or set CERTIFICATE.')

    if not os.path.exists(settings.certificate):
        raise FileNotFoundError(f'MITMProxy certificate directory not found: {settings.certificate}')

    # Update settings

    settings.repo = repository

    if container is not None:
        settings.container = container

    if arch is not None:
        settings.arch = arch

    if output is not None:
        settings.output_dir = Path(output)

    # Extract workflows

    workflows = (repository / '.github' / 'workflows').glob('*.yml')
    workflows = [Workflow.parse(w) for w in workflows]

    log.info(f'Found {len(list(workflows))} workflows in repository: {repository}')

    for workflow in workflows:
        log.info(f'{workflow.name} - {workflow.path}: {[j.name for j in workflow.jobs]}')

    ##################

    ci_workflow = next((w for w in workflows if w.name == 'CI'), None)
    if ci_workflow is None:
        raise ValueError(f'No ci workflow found in repository: {repository}')

    lint_and_test_job = next((j for j in ci_workflow.jobs if j.name == 'lint-and-test'), None)
    if lint_and_test_job is None:
        raise ValueError(f'No lint-and-test job found in ci workflow: {ci_workflow.path}')

    from pipelinespec.core.runner import job_runner
    from pipelinespec.models import TraceConfig

    log.info(f'Running job: {lint_and_test_job.name} from workflow: {ci_workflow.name}')
    job_runner.execute(lint_and_test_job, TraceConfig(env={}, secrets={}, networks=[]))
    log.info(f'Job completed: {lint_and_test_job.name} from workflow: {ci_workflow.name}')


if __name__ == '__main__':
    main()
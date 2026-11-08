from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from concurrent.futures import ThreadPoolExecutor, as_completed
from click.core import ParameterSource
from pipelinespec.models import Sample
from pipelinespec import console, log
from pipelinespec.utils import slug
from pipelinespec.tools import git
from datetime import datetime
from threading import Lock
from pathlib import Path
import subprocess
import random
import shutil
import click
import json
import sys
import os

JOURNAL_LOCK = Lock()

def report(journal: Path, message: str, style: str | None = None) -> None:

    log(message, style=style)

    with JOURNAL_LOCK, open(journal, 'a') as f:
        f.write(f'[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}\n')

def read_manifest(output: Path) -> list[Sample]:

    path = output / 'manifest.json'

    if not path.exists():
        raise click.UsageError(f'There is no manifest at {path}. Run sample first.')

    return [Sample.model_validate(entry) for entry in json.loads(path.read_text())]

def load_samples(n: int, output: Path) -> list[Sample]:

    return read_manifest(output)[:n]

def random_samples(n: int, model: str, output: Path) -> list[Sample]:

    results = output / 'results' / slug(model)
    traceable = [sample for sample in read_manifest(output) if traced_constraints(results / slug(sample.name), 1, False) is not None]

    return random.sample(traceable, min(n, len(traceable)))

def run_pipelinespec(arguments: list[str], terminal) -> int:

    command = [sys.executable, '-m', 'pipelinespec.cli.main', *arguments]

    return subprocess.run(command, stdout=terminal, stderr=subprocess.STDOUT, env={**os.environ, 'PYTHONUNBUFFERED': '1'}).returncode

def traced_constraints(results: Path, k: int, constraints: bool) -> Path | None:

    if constraints:
        return results / ('constraints.json' if k == 1 else 'constraints_1.json')

    return next((path for path in (results / 'constraints.json', results / 'constraints_1.json') if path.exists()), None)

def run_pipeline(sample: Sample, model: str, k: int, output: Path, constraints: bool, tracing: bool, journal: Path, header: str) -> bool:

    results = output / 'results' / slug(model) / slug(sample.name)
    results.mkdir(parents=True, exist_ok=True)
    traced = traced_constraints(results, k, constraints)

    if tracing and traced is None:
        report(journal, f'{sample.name}: there is no constraints.json or constraints_1.json in {results} to trace.', 'yellow')
        return False

    clones = output / 'repositories'
    clones.mkdir(parents=True, exist_ok=True)
    destination = clones / slug(sample.name)

    try:
        destination.mkdir()
    except FileExistsError:
        report(journal, f'{destination} already exists, so {sample.name} is skipped rather than overwriting it.', 'yellow')
        return False

    try:
        git.checkout(sample.clone_url, sample.commit, destination)

        common = ['-r', str(destination), '-o', str(results), '-m', model]
        stages = [
            *([('constraints', [*common, '--constraints-only', '-n', str(k)])] if constraints else []),
            *([('tracing', [*common, '--trace-only', '--constraints', str(traced)])] if tracing else []),
        ]

        with open(results / 'terminal.log', 'w' if constraints else 'a') as terminal:
            terminal.write(f'{header}repository: {sample.name} at {sample.commit}\n\n')
            terminal.flush()

            for stage, arguments in stages:
                code = run_pipelinespec(arguments, terminal)

                if code != 0:
                    report(journal, f'{sample.name}: {stage} exited with {code}; see {results / "terminal.log"}.', 'yellow')
                    return False

        report(journal, f'{sample.name}: done, results in {results}.', 'green')

        return True
    except Exception as problem:
        report(journal, f'{sample.name} could not be run: {problem}', 'yellow')
        return False
    finally:
        shutil.rmtree(destination, ignore_errors=True)

@click.command()
@click.option('-n', type=click.IntRange(min=1), default=50, help='Number of repositories to run: the first n of the manifest, or with --trace-only a random n of those with saved constraints.')
@click.option('--threads', '-t', type=click.IntRange(min=1), default=1, help='Number of repositories to process at once.')
@click.option('--model', '-m', required=True, help='Model for the agents.')
@click.option('-k', type=click.IntRange(min=1), default=5, help='Number of constraint agent runs per repository; only the first is traced.')
@click.option('--constraints-only', is_flag=True, help='Only run the constraint agent; skip tracing.')
@click.option('--trace-only', is_flag=True, help='Only trace, from the constraints an earlier run saved in the results directory.')
@click.option('--output', '-o', default='data/', help='Directory with manifest.json; results go to its results/ directory.')
def main(n: int, threads: int, model: str, k: int, constraints_only: bool, trace_only: bool, output: str) -> None:

    if constraints_only and trace_only:
        raise click.UsageError('--constraints-only and --trace-only cannot be used together.')

    if trace_only and click.get_current_context().get_parameter_source('k') == ParameterSource.COMMANDLINE:
        raise click.UsageError('-k has no effect with --trace-only, which traces the constraints already saved.')

    if not constraints_only and not os.environ.get('CERTIFICATE'):
        raise click.UsageError('CERTIFICATE is not set. Add the mitmproxy certificate directory to .env and run with uv run --env-file .env.')

    directory = Path(output)
    journal = directory / 'terminal.log'
    samples = random_samples(n, model, directory) if trace_only else load_samples(n, directory)

    with JOURNAL_LOCK, open(journal, 'a') as f:
        f.write(f'\n===== experiment started {datetime.now():%Y-%m-%d %H:%M:%S} =====\n')

    report(journal, f'Read {len(samples)} repositories from {directory / "manifest.json"}' + (f', picked at random from those with saved constraints:{", ".join(sample.name for sample in samples)}.' if trace_only else '.'))

    if trace_only and len(samples) < n:
        report(journal, f'Only {len(samples)} repositories have saved constraints for {model}, fewer than the {n} asked for.', 'yellow')
    stages = 'constraints only' if constraints_only else 'tracing only' if trace_only else 'constraints, then tracing'
    parameters = {
        'model': model,
        'repositories': f'{len(samples)} (-n {n})',
        'stages': stages,
        'constraint runs (-k)': 'none, the saved constraints are traced' if trace_only else f'{k}' + ('' if constraints_only else ', the first is traced'),
        'threads (-t)': threads,
        'manifest': directory / 'manifest.json',
        'results': directory / 'results' / slug(model),
    }

    if not constraints_only:
        parameters['certificate'] = os.environ['CERTIFICATE']

    report(journal, 'Experiment parameters:')

    for name, value in parameters.items():
        report(journal, f'  {name}: {value}')

    header = 'Experiment parameters:\n' + ''.join(f'  {name}: {value}\n' for name, value in parameters.items())

    report(journal, f'Running pipelinespec on {len(samples)} repositories...')

    progress = Progress(SpinnerColumn(), TextColumn('[cyan]{task.description}'), BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(), console=console)
    bar = progress.add_task('Running pipelinespec', total=len(samples))
    succeeded = 0

    with progress, ThreadPoolExecutor(max_workers=threads) as pool:
        futures = [pool.submit(run_pipeline, sample, model, k, directory, not trace_only, not constraints_only, journal, header) for sample in samples]

        for future in as_completed(futures):
            succeeded += future.result()
            progress.advance(bar)

    report(journal, f'{succeeded} of {len(samples)} repositories finished; results in {directory / "results" / slug(model)}.', 'green' if succeeded == len(samples) else 'yellow')

if __name__ == '__main__':
    main()

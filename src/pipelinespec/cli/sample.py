from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from concurrent.futures import ThreadPoolExecutor
from pipelinespec.models import Sample, Workflow
from pipelinespec.tools import git, github
from pipelinespec import console, log
from pipelinespec.utils import slug
from rich.console import Group
from threading import Lock
from rich.live import Live
from rich.text import Text
from pathlib import Path
import shutil
import click
import json

PER_PAGE = 100
MAX_PAGES = 10
BINARY_PROBE = 8192
EXCLUDED_TOPICS = frozenset({
    'awesome', 'awesome-list', 'list', 'tutorial', 'template', 'certification', 'roadmap', 'skills', 'ai-skills', 'deepseek',
    'style-guide', 'styleguide', 'book', 'books', 'education', 'leetcode',
    'interview', 'interview-preparation', 'interview-questions', 'coding-interviews', 'algorithm-interview', 'interview-practice',
})

def count_lines(path: Path) -> int:

    if path.is_symlink() or not path.is_file():
        return 0

    data = path.read_bytes()

    if b'\0' in data[:BINARY_PROBE]:
        return 0

    return data.count(b'\n') + (bool(data) and not data.endswith(b'\n'))

def measure(candidate: dict, clones: Path, max_jobs: int | None) -> Sample | None:

    name = candidate['name']
    destination = clones / slug(name)

    try:
        destination.mkdir()
    except FileExistsError:
        log(f'{destination} already exists, so {name} is skipped rather than overwriting it.', style='yellow')
        return None

    try:
        git.clone(candidate['clone_url'], destination)

        directory = destination / '.github' / 'workflows'
        workflows = Workflow.find_all(directory) if directory.is_dir() else []

        if not workflows:
            log(f'{name} has no workflows; skipped.', style='dim')
            return None

        jobs = sum(len(workflow.jobs) for workflow in workflows)

        if max_jobs is not None and jobs > max_jobs:
            log(f'{name} has {jobs} jobs, more than {max_jobs}; skipped.', style='dim')
            return None

        commit = git.head(destination)

        if commit is None:
            raise RuntimeError('the clone has no HEAD commit')

        tracked = git.tracked(destination)
        sample = Sample(
            name=name,
            clone_url=candidate['html_url'],
            commit=commit,
            commit_date=git.commit_date(destination),
            stars=candidate['stargazers_count'],
            forks=candidate['forks_count'],
            topics=candidate.get('topics', []),
            primary_language=candidate.get('language'),
            languages=github.languages(candidate['full_name']),
            workflows=len(workflows),
            jobs=jobs,
            files=len(tracked),
            lines=sum(count_lines(destination / path) for path in tracked),
        )

        log(f'{name}: {sample.workflows} workflows, {sample.jobs} jobs.')

        return sample
    except Exception as problem:
        log(f'{name} could not be sampled and is skipped: {problem}', style='yellow')
        return None
    finally:
        shutil.rmtree(destination, ignore_errors=True)

def save_manifest(samples: list[Sample], output: Path) -> Path:

    path = output / 'manifest.json'
    path.write_text(json.dumps([sample.model_dump(mode='json') for sample in samples], indent=4))

    return path

def sample_repositories(n: int, threads: int, output: Path, verbose: bool, max_jobs: int | None) -> list[Sample]:

    clones = output / 'repositories'
    clones.mkdir(parents=True, exist_ok=True)
    samples: list[Sample] = []

    path = save_manifest(samples, output)
    log(f'Writing the manifest to {path} as repositories are sampled.')

    progress = Progress(SpinnerColumn(), TextColumn('[cyan]{task.description}'), BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(), console=console)
    bar = progress.add_task('Sampling repositories', total=n)
    processing = Text(style='dim')
    running: set[str] = set()
    lock = Lock()

    def show() -> None:

        processing.plain = f'  Processing: {", ".join(sorted(running))}' if running else ''

    def process(candidate: dict) -> Sample | None:

        with lock:
            running.add(candidate['name'])
            show()

        try:
            return measure(candidate, clones, max_jobs)
        finally:
            with lock:
                running.discard(candidate['name'])
                show()

    with Live(Group(progress, processing), console=console), ThreadPoolExecutor(max_workers=threads) as pool:
        for page in range(1, MAX_PAGES + 1):
            found_page = github.search(page, PER_PAGE)

            if verbose:
                raw = output / 'raw' / f'repositories_{page}.json'
                raw.parent.mkdir(parents=True, exist_ok=True)
                raw.write_text(json.dumps(found_page, indent=4))
                log(f'Search page {page}: {len(found_page)} candidates, saved to {raw}.', style='dim')

            candidates = []

            for candidate in found_page:
                excluded = EXCLUDED_TOPICS.intersection(candidate.get('topics', []))

                if excluded:
                    log(f'{candidate["name"]} has the excluded topic {", ".join(sorted(excluded))}; skipped.', style='dim')
                else:
                    candidates.append(candidate)

            index = 0

            while index < len(candidates) and len(samples) < n:
                batch = candidates[index:index + min(threads, n - len(samples))]
                index += len(batch)

                for found in pool.map(process, batch):
                    if found is not None:
                        samples.append(found)
                        save_manifest(samples, output)
                        progress.advance(bar)

            if len(samples) >= n or len(found_page) < PER_PAGE:
                break

    log(f'Saved {len(samples)} repositories to {path}.', style='green')

    return samples

@click.command()
@click.option('-n', type=click.IntRange(min=1), default=10, help='Number of repositories to fetch.')
@click.option('--threads', '-t', type=click.IntRange(min=1), default=1, help='Number of repositories to process at once.')
@click.option('--output', '-o', default='data/', help='Output directory for samples GitHub repositories.')
@click.option('--max-jobs', type=click.IntRange(min=1), default=None, help='Skip repositories with more jobs than this across their workflows.')
@click.option('--verbose', '-v', is_flag=True, help='Verbose logging.')
def main(n: int, threads: int, output: str, max_jobs: int | None, verbose: bool) -> None:

    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=True)

    log(f'Sampling {n} repositories, {threads} at a time{"" if max_jobs is None else f", with at most {max_jobs} jobs each"}...')

    samples = sample_repositories(n, threads, directory, verbose, max_jobs)

    if len(samples) < n:
        log(f'Only {len(samples)} of {n} repositories could be sampled.', style='yellow')

if __name__ == '__main__':
    main()

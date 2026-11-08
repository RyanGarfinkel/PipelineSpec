from pipelinespec.models import Constraints, Gate, JobConstraints
from collections.abc import Callable, Iterable
from itertools import combinations
from pipelinespec.tools import smt
from pipelinespec import console
from pydantic import TypeAdapter
from rich.table import Table
from statistics import mean
from pathlib import Path
import click

METRICS = ('events', 'gate locations', 'equivalent gates', 'unsolved', 'variables', 'constants')

def jaccard(left: Iterable, right: Iterable) -> float:

    left, right = set(left), set(right)

    return len(left & right) / len(left | right) if left | right else 1.0

def by_location(gates: list[Gate]) -> dict[str, list[Gate]]:

    groups: dict[str, list[Gate]] = {}

    for gate in gates:
        groups.setdefault(gate.location.strip().removeprefix('./'), []).append(gate)

    return groups

def equivalent_gates(left: JobConstraints, right: JobConstraints, events: list[str]) -> tuple[float | None, set[str]]:

    left_groups, right_groups = by_location(left.gates), by_location(right.gates)
    decided: list[bool] = []
    undecided: set[str] = set()

    for location in left_groups.keys() & right_groups.keys():
        try:
            same = smt.equivalent(left, left_groups[location], right, right_groups[location], events)
        except ValueError:
            same = False

        if same is None:
            undecided.add(location)
        else:
            decided.append(same)

    return (sum(decided) / len(decided) if decided else None), undecided

def compare_job(left: JobConstraints, right: JobConstraints, events: list[str]) -> tuple[dict[str, float | None], set[str]]:

    locations: Callable[[JobConstraints], set[str]] = lambda constraints: set(by_location(constraints.gates))
    equivalent, undecided = equivalent_gates(left, right, events)

    return {
        'gate locations': jaccard(locations(left), locations(right)),
        'equivalent gates': equivalent,
        'unsolved': jaccard((item.location for item in left.unsolved), (item.location for item in right.unsolved)),
        'variables': jaccard((variable.target for variable in left.variables.values()), (variable.target for variable in right.variables.values())),
        'constants': jaccard(left.constants, right.constants),
    }, undecided

def recorded_nothing(constraints: JobConstraints) -> bool:

    return not (constraints.gates or constraints.variables or constraints.constants or constraints.unsolved)

def compare(outputs: list[dict[str, Constraints]]) -> tuple[dict[str, dict[str, list[float]]], set[str], set[str], set[str]]:

    scores: dict[str, dict[str, list[float]]] = {}
    partial: set[str] = set()
    recorded: set[str] = set()
    undecided: set[str] = set()

    for left, right in combinations(outputs, 2):
        for workflow in left.keys() | right.keys():
            if workflow not in left or workflow not in right:
                partial.add(workflow)
                continue

            left_events, right_events = ({trigger.event for trigger in side[workflow].triggers} for side in (left, right))
            events = sorted(left_events | right_events)

            for job in left[workflow].jobs.keys() | right[workflow].jobs.keys():
                name = f'{workflow} / {job}'

                if job not in left[workflow].jobs or job not in right[workflow].jobs:
                    partial.add(name)
                    continue

                row = scores.setdefault(name, {metric: [] for metric in METRICS})
                row['events'].append(jaccard(left_events, right_events))

                if not (recorded_nothing(left[workflow].jobs[job]) and recorded_nothing(right[workflow].jobs[job])):
                    recorded.add(name)

                job_scores, job_undecided = compare_job(left[workflow].jobs[job], right[workflow].jobs[job], events)
                undecided |= {f'{name} @ {location}' for location in job_undecided}

                for metric, score in job_scores.items():
                    if score is not None:
                        row[metric].append(score)

    return scores, partial, scores.keys() - recorded, undecided

def cell(values: list[float]) -> str:

    if not values:
        return '[dim]-[/dim]'

    score = mean(values)

    return f'{score:.2f}' if score == 1 else f'[yellow]{score:.2f}[/yellow]'

@click.command()
@click.argument('files', nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option('--all', '-a', 'show_all', is_flag=True, help='List every job, not only the ones that differ.')
def main(files: tuple[Path, ...], show_all: bool) -> None:
    """Measures how consistent two or more constraints.json files are, such as the -k samples of one repository or two models' outputs."""

    if len(files) < 2:
        raise click.UsageError('Give at least two constraints files to compare.')

    adapter = TypeAdapter(dict[str, Constraints])
    scores, partial, empty, undecided = compare([adapter.validate_json(path.read_text()) for path in files])
    jobs = Table('Job', *METRICS, title='Jobs (mean Jaccard over every pair of files; equivalent gates is the share of shared locations Z3 finds equivalent, of those it could decide)')

    for name, row in sorted(scores.items()):
        if show_all or any(values and mean(values) < 1 for values in row.values()):
            jobs.add_row(name, *(cell(row[metric]) for metric in METRICS))

    summary = Table('Metric', 'Mean', 'Jobs that agree', 'Jobs measured')

    for metric in METRICS:
        measured = [mean(row[metric]) for row in scores.values() if row[metric]]
        summary.add_row(metric, f'{mean(measured):.3f}' if measured else '-', str(sum(score == 1 for score in measured)), str(len(measured)))

    if jobs.row_count:
        console.print(jobs)

    console.print(summary)
    console.print(f'{len(files)} files, {len(scores)} jobs compared, {len(empty)} of them with nothing recorded in any file (they agree trivially)')

    if partial:
        console.print(f'[yellow]Missing from some files, not compared:[/yellow] {", ".join(sorted(partial))}')

    if undecided:
        console.print(f'[yellow]Z3 could not decide within the time limit, left out of equivalent gates:[/yellow] {", ".join(sorted(undecided))}')

if __name__ == '__main__':
    main()

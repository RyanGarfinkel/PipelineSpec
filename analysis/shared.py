from pipelinespec.models import Constraints
from pipelinespec.core import verifier
from collections.abc import Iterator
from pydantic import TypeAdapter
from pathlib import Path
import json
import re

DATA = Path('../data')
RESULTS = DATA / 'results'
TRUTH = DATA / 'ground_truth'
STALE = {'vscode'}
CATEGORY = re.compile(r': (trigger events|trigger|gate|no extra gates|unsolved)\b')

adapter = TypeAdapter(dict[str, Constraints])

def load_outputs() -> dict[tuple[str, str], list[dict[str, Constraints]]]:

    return {
        (model.name, repo.name): [adapter.validate_json(path.read_text()) for path in sorted(repo.glob('constraints*.json'))]
        for model in sorted(RESULTS.iterdir()) if model.is_dir()
        for repo in sorted(model.iterdir()) if repo.is_dir() and repo.name not in STALE
    }

def load_truths() -> dict[str, tuple[dict[str, Constraints], dict]]:

    return {path.stem: (adapter.validate_json(path.read_text()), json.loads(path.read_text())) for path in sorted(TRUTH.glob('*.json'))}

def spans(location: str) -> Iterator[tuple[str, int, int]]:

    for part in location.split('|'):
        path, _, lines = part.strip().removeprefix('./').rpartition(':')

        for piece in lines.split(','):
            first, _, last = piece.strip().partition('-')

            if first.strip().isdigit():
                yield path, int(first), int(last) if last.strip().isdigit() else int(first)

def overlaps(found: str, wanted: str) -> bool:

    return any(
        (path.endswith(other) or other.endswith(path)) and first <= other_last and other_first <= last
        for path, first, last in spans(found)
        for other, other_first, other_last in spans(wanted)
    )

def without_excluded(output: dict[str, Constraints], raw_truth: dict) -> tuple[dict[str, Constraints], int]:

    stripped: dict[str, Constraints] = {}
    removed = 0

    for workflow, constraints in output.items():
        jobs = {}

        for job, found in constraints.jobs.items():
            excluded = [item['location'] for item in raw_truth.get(workflow, {}).get('jobs', {}).get(job, {}).get('excluded', [])]
            gates = [gate for gate in found.gates if not any(overlaps(gate.location, location) for location in excluded)]
            removed += len(found.gates) - len(gates)
            jobs[job] = found.model_copy(update={'gates': gates})

        stripped[workflow] = constraints.model_copy(update={'jobs': jobs})

    return stripped, removed

def score(truth: dict[str, Constraints], raw_truth: dict, output: dict[str, Constraints]) -> tuple[list[dict], int]:

    stripped, removed = without_excluded(output, raw_truth)
    report = verifier.verify(truth, stripped)
    category = lambda name: match.group(1) if (match := CATEGORY.search(name)) else 'not in truth'

    return [{'category': category(check.name), 'passed': check.passed} for check in report.checks], removed

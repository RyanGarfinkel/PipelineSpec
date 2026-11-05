from pipelinespec.models import JobRun, StepResult
from singleton_decorator import singleton
from pipelinespec.utils import slug
from pathlib import Path
import json
import re

EXIT_CODE = re.compile(r"exitcode '(-?\d+)'")
SKIP_CONDITION = re.compile(r"due to '(.*)'$")

@singleton
class Runlog:

    def parse(self, log: Path) -> dict[tuple[str, str], JobRun]:

        jobs: dict[tuple[str, str], dict] = {}

        for entry in self.__entries(log):
            if 'jobID' not in entry:
                continue

            parts = entry.get('job', '').split('/')
            key = (slug(parts[-2] if len(parts) > 1 else ''), entry['jobID'])
            job = jobs.setdefault(key, {'outcome': 'unknown', 'steps': {}})

            if 'jobResult' in entry:
                job['outcome'] = entry['jobResult']

            ids = entry.get('stepID')
            if ids:
                self.__step(job, ids, entry)

        return {key: self.__run(key, job) for key, job in jobs.items()}

    def __step(self, job: dict, ids: list[str], entry: dict) -> None:

        step = job['steps'].setdefault(ids[0], {'name': '', 'order': None, 'results': {}, 'exit_code': None, 'skipped_because': None})
        message = entry.get('msg', '')

        if entry.get('stage') == 'Main' and step['order'] is None:
            step['order'] = sum(other['order'] is not None for other in job['steps'].values())

        exit_code = EXIT_CODE.search(message)
        if exit_code and step['exit_code'] is None:
            step['exit_code'] = int(exit_code[1])

        if len(ids) > 1:
            return

        step['name'] = entry.get('step', step['name'])

        if 'stepResult' in entry:
            step['results'][entry.get('stage')] = entry['stepResult']

        condition = SKIP_CONDITION.search(message)
        if entry.get('stepResult') == 'skipped' and condition:
            step['skipped_because'] = 'earlier_failure' if condition[1] == '' else 'condition'

    def __run(self, key: tuple[str, str], job: dict) -> JobRun:

        steps = job['steps']
        ordered = sorted(steps.items(), key=lambda item: len(steps) if item[1]['order'] is None else item[1]['order'])

        return JobRun(
            workflow=key[0],
            job=key[1],
            outcome=job['outcome'],
            steps=tuple(self.__result(id, step) for id, step in ordered),
        )

    def __result(self, id: str, step: dict) -> StepResult:

        results = set(step['results'].values())

        if 'failure' in results:
            outcome = 'failure'
        elif 'success' in results and step['results'].get('Main') != 'skipped':
            outcome = 'success'
        else:
            outcome = 'skipped'

        return StepResult(
            id=id,
            name=step['name'],
            outcome=outcome,
            exit_code=step['exit_code'],
            skipped_because=step['skipped_because'] if outcome == 'skipped' else None,
        )

    def __entries(self, log: Path) -> list[dict]:

        entries = []

        for line in log.read_text(errors='replace').splitlines():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        return entries

runlog = Runlog()

from pipelinespec.models import Answer, Check, Constraints, Gate, Report
from singleton_decorator import singleton
from pipelinespec.tools import smt
from typing import Any
import re

Location = tuple[str, int, int]

@singleton
class Verifier:

    def verify(self, truth: dict[str, Answer], output: dict[str, Answer]) -> Report:

        checks: list[Check] = []

        for workflow, answer in output.items():
            if workflow not in truth:
                checks.append(Check(name=workflow, passed=False, detail='The workflow is not in the ground truth.'))
                continue

            checks += self.__triggers(workflow, truth[workflow], answer)

            for job, constraints in answer.jobs.items():
                if job not in truth[workflow].jobs:
                    checks.append(Check(name=f'{workflow}/{job}', passed=False, detail='The job is not in the ground truth.'))
                    continue

                checks += self.__job(f'{workflow}/{job}', truth[workflow].jobs[job], constraints)

        if not checks:
            checks.append(Check(name='output', passed=False, detail='The output has no workflow to verify.'))

        return Report(checks=tuple(checks))

    def __triggers(self, workflow: str, expected: Answer, actual: Answer) -> list[Check]:

        wanted, found = {trigger.event for trigger in expected.triggers}, {trigger.event for trigger in actual.triggers}
        missing, extra = sorted(wanted - found), sorted(found - wanted)
        detail = '; '.join(part for part in (f'missing events {missing}' if missing else '', f'unexpected events {extra}' if extra else '') if part)
        checks = [Check(name=f'{workflow}: trigger events', passed=not detail, detail=detail)]

        for trigger in expected.triggers:
            match = next((candidate for candidate in actual.triggers if candidate.event == trigger.event), None)

            if match is None:
                continue

            problems = self.__subset(trigger.payload, match.payload, 'payload')
            checks.append(Check(name=f'{workflow}: trigger {trigger.event}', passed=not problems, detail='; '.join(problems)))

        return checks

    def __subset(self, expected: Any, actual: Any, path: str) -> list[str]:

        if isinstance(expected, dict) and set(expected) == {'$in'}:
            return [] if actual in expected['$in'] else [f'{path} is {actual!r}, expected one of {expected["$in"]}']

        if not isinstance(expected, dict):
            return [] if actual == expected else [f'{path} is {actual!r}, expected {expected!r}']

        if not isinstance(actual, dict):
            return [f'{path} is {actual!r}, expected an object']

        return [problem for key, value in expected.items() for problem in (self.__subset(value, actual[key], f'{path}.{key}') if key in actual else [f'{path}.{key} is missing'])]

    def __job(self, name: str, expected: Constraints, actual: Constraints) -> list[Check]:

        checks: list[Check] = []
        groups: dict[str, list[Gate]] = {}

        for gate in expected.gates:
            groups.setdefault(gate.location, []).append(gate)

        matched: dict[str, list[Gate]] = {location: [] for location in groups}
        extra: list[str] = []

        for gate in actual.gates:
            location = next((location for location in groups if self.__within(gate.location, location)), None)

            if location is None:
                extra.append(gate.location)
            else:
                matched[location].append(gate)

        for location, gates in groups.items():
            checks.append(self.__gates(f'{name}: gate {location}', expected, gates, actual, matched[location]))

        checks.append(Check(name=f'{name}: no extra gates', passed=not extra, detail=f'gates at {extra} are not in the ground truth' if extra else ''))

        for item in expected.unsolved:
            found = any(self.__within(candidate.location, item.location) for candidate in actual.unsolved)
            checks.append(Check(name=f'{name}: unsolved {item.location}', passed=found, detail='' if found else 'no unsolved entry at this location'))

        return checks

    def __gates(self, name: str, expected: Constraints, wanted: list[Gate], actual: Constraints, found: list[Gate]) -> Check:

        if not found:
            return Check(name=name, passed=False, detail='no gate at this location')

        try:
            same = smt.equivalent(expected, wanted, actual, found)
        except ValueError as error:
            return Check(name=name, passed=False, detail=str(error))

        if same:
            return Check(name=name, passed=True)

        return Check(name=name, passed=False, detail=f'expected {" && ".join(gate.condition for gate in wanted)}, got {" && ".join(gate.condition for gate in found)}')

    def __within(self, actual: str, expected: str) -> bool:

        path, start, _ = self.__location(actual)

        return any(
            (path.endswith(wanted) or wanted.endswith(path)) and first <= start <= last
            for wanted, first, last in map(self.__location, expected.split('|'))
        )

    def __location(self, location: str) -> Location:

        match = re.fullmatch(r'(.+?):(\d+)(?:-(\d+))?', location.strip())

        if match is None:
            return location.strip(), -1, -1

        return match.group(1).removeprefix('./'), int(match.group(2)), int(match.group(3) or match.group(2))

verifier = Verifier()

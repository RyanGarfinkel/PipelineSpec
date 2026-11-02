from pipelinespec.models import AccessMap as AccessMapModel, AccessVariant, JobNode, Tested, TraceResult, Trial
from singleton_decorator import singleton
from pipelinespec import settings
from pathlib import Path
from .loop import Traced

@singleton
class AccessMap:

    def __init__(self):

        self.jobs = {}

    def add(self, trial: Trial, result: TraceResult) -> None:

        self.jobs.setdefault((trial.candidate.workflow, trial.candidate.job), []).append((trial, result))

    def save(self) -> Path:

        nodes = tuple(self.__node(traced) for traced in self.jobs.values())
        path = settings.file.output / 'map.json'
        path.write_text(AccessMapModel(repository=str(settings.repo), jobs=nodes).model_dump_json(indent=4))

        return path

    def __node(self, traced: list[Traced]) -> JobNode:

        first = traced[0][0].candidate
        constraints = first.constraints
        ran = [(trial, result) for trial, result in traced if not trial.candidate.call]
        found: dict[tuple, list[dict]] = {}

        for trial, result in ran:
            found.setdefault((result.outcome, result.access), []).append(trial.candidate.assignment)

        variants = tuple(AccessVariant(outcome=outcome, access=access, contexts=tuple(contexts)) for (outcome, access), contexts in found.items())

        tested = tuple(
            Tested(context=trial.candidate.assignment, reason=trial.candidate.reason, outcome=trial.outcome, runs=trial.runs, diagnosis=trial.diagnosis.reason if trial.diagnosis else None)
            for trial, _ in ran
        )

        events = tuple(dict.fromkeys(trial.candidate.context.event for trial, _ in traced))

        return JobNode(workflow=first.workflow, name=first.job, events=events, needs=first.needs, uses=first.uses, gates=constraints.gates, variables=constraints.variables, unsolved=constraints.unsolved, tested=tested, variants=variants)

access_map = AccessMap()

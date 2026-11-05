from pipelinespec.models import AccessMap as AccessMapModel, AccessVariant, JobNode, Tested, Trace
from singleton_decorator import singleton
from pipelinespec import settings
from pathlib import Path

@singleton
class AccessMap:

    def __init__(self):

        self.jobs = {}

    def add(self, trace: Trace) -> None:

        self.jobs.setdefault((trace.trial.candidate.workflow, trace.trial.candidate.job), []).append(trace)

    def save(self) -> Path:

        nodes = tuple(self.__node(traces) for traces in self.jobs.values())
        path = settings.file.output / 'map.json'
        path.write_text(AccessMapModel(repository=str(settings.repo), jobs=nodes).model_dump_json(indent=4))

        return path

    def __node(self, traces: list[Trace]) -> JobNode:

        first = traces[0].trial.candidate
        constraints = first.constraints
        ran = [trace for trace in traces if not trace.trial.candidate.call]
        found: dict[tuple, list[dict]] = {}

        for trace in ran:
            found.setdefault((trace.result.outcome, trace.result.access), []).append(trace.trial.candidate.assignment)

        variants = tuple(AccessVariant(outcome=outcome, access=access, contexts=tuple(contexts)) for (outcome, access), contexts in found.items())

        tested = tuple(
            Tested(context=trial.candidate.assignment, reason=trial.candidate.reason, outcome=trial.outcome, runs=trial.runs, diagnosis=trial.diagnosis.reason if trial.diagnosis else None)
            for trial in (trace.trial for trace in ran)
        )

        events = tuple(dict.fromkeys(trace.trial.candidate.context.event for trace in traces))

        return JobNode(workflow=first.workflow, name=first.job, events=events, needs=first.needs, uses=first.uses, gates=constraints.gates, variables=constraints.variables, unsolved=constraints.unsolved, tested=tested, variants=variants)

access_map = AccessMap()

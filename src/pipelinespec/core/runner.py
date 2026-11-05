from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TaskID, TextColumn, TimeElapsedColumn
from pipelinespec.models import Mocks, Trace, TraceResult, Trial, Variant, Version, Workflow
from pipelinespec.tools import Versions, trace_filter
from pipelinespec.diagnose import diagnoser
from pipelinespec import console, settings
from singleton_decorator import singleton
from dataclasses import dataclass, field
from rich.table import Column, Table
from pipelinespec.utils import slug
from rich.console import Group
from rich.live import Live
from rich.text import Text
from .tracer import tracer
from pathlib import Path
from uuid import uuid4
import logging as log
import json

Key = tuple[str, str]
TOKEN = 'GITHUB_TOKEN'
OUTCOME_STYLES = {'success': 'green', 'failure': 'red', 'job_skipped': 'dim'}

@dataclass
class RunState:

    workflows: dict[Key, Workflow]
    progress: Progress
    bar: TaskID
    table: Table
    live: Live
    mocks: Mocks = field(default_factory=Mocks)
    versions: Versions = field(default_factory=dict)
    fetched: set[Key] = field(default_factory=set)
    trials: dict[str, dict[str, list[Trial]]] = field(default_factory=dict)

    @classmethod
    def start(cls, workflows: list[Workflow], total: int) -> 'RunState':

        lookup: dict[Key, Workflow] = {}

        for workflow in workflows:
            for job in workflow.jobs:
                lookup.setdefault((workflow.name, job.name), workflow)

        progress = Progress(SpinnerColumn(), TextColumn('[cyan]{task.description}'), BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(), console=console)
        table = Table('Pipeline', 'Phase', 'Variant', 'Outcome', *(Column(name, justify='right') for name in ('Runs', 'Files', 'Hosts')), 'Secrets')
        live = Live(Group(table, progress), console=console, vertical_overflow='visible')

        return cls(lookup, progress, progress.add_task('', total=total), table, live)

@singleton
class Runner:

    def get_traces(self, workflows: list[Workflow], variants: list[Variant]) -> list[Trace]:

        state = RunState.start(workflows, len(variants))

        for variant in variants:
            if variant.context is None:
                raise ValueError(f'The variant "{variant.reason}" is not bound to a job and a context.')

            if (variant.workflow, variant.job) not in state.workflows:
                raise ValueError(f'The variant "{variant.reason}" names job "{variant.job}" of workflow "{variant.workflow}", which is not in the repository.')

        with state.live:
            traces = [self.__variant(variant, state) for variant in variants]

        if settings.verbose:
            self.__save_versions(state.versions)

        return traces

    def __variant(self, variant: Variant, state: RunState) -> Trace:

        log.debug(f'{variant.workflow} / {variant.job} ({variant.reason}): {variant.assignment}')
        state.progress.update(state.bar, description=f'{variant.workflow} / {variant.job}: {variant.reason}')

        trace = self.__call_site(variant) if variant.call else self.__trace(variant, state)
        trial, result = trace.trial, trace.result

        state.trials.setdefault(variant.workflow, {}).setdefault(variant.job, []).append(trial)
        self.__save_trials(state.trials)

        outcome = Text('call', style='dim') if variant.call else Text(trial.outcome, style=OUTCOME_STYLES.get(trial.outcome, 'none'))
        hosts = {network.host for network in result.networks}
        state.table.add_row(variant.workflow, variant.job, variant.reason, outcome, str(len(trial.runs)), str(len(result.files)), str(len(hosts)), ', '.join(sorted(result.secrets)))
        state.progress.advance(state.bar)

        return trace

    def __call_site(self, variant: Variant) -> Trace:

        return Trace(trial=Trial(candidate=variant, outcome='unknown'), result=TraceResult(id=uuid4(), path=Path(variant.uses), job=variant.job, outcome='unknown'))

    def __trace(self, variant: Variant, state: RunState) -> Trace:

        key = (variant.workflow, variant.job)
        workflow = state.workflows[key]
        mocks, diagnosis, runs, best = state.mocks.model_copy(deep=True), None, [], None

        if key not in state.fetched and TOKEN in mocks.credentials:
            mocks.credentials.remove(TOKEN)

        for attempt in range(settings.agent.retries + 1):
            result = tracer.run(workflow, variant, mocks)
            runs.append(result.id)

            if best is None or self.__score(result) > self.__score(best[0]):
                best = result, mocks.model_copy(deep=True)

            if result.outcome != 'failure' or attempt == settings.agent.retries:
                break

            before = mocks.model_copy(deep=True)
            diagnosis = diagnoser.run(settings.file.output / 'runs' / str(result.id), mocks)

            if not diagnosis.fixable or mocks == before:
                break

            log.debug(f'Tracing again with {len(mocks.credentials)} added credentials and {len(mocks.calls)} mocked calls.')

        result, mocks = best
        state.mocks.merge(mocks)
        state.fetched.add(key)

        target = (slug(variant.workflow), variant.job)
        version = Version(run=result.id, outcome=result.outcome, steps=[(step.id, step.outcome) for step in result.steps])
        result = trace_filter.clean(result, target, state.versions)

        if result.outcome != 'skipped':
            repeat = trace_filter.clean(tracer.run(workflow, variant, mocks), target, state.versions)
            runs.append(repeat.id)

            if repeat.outcome == result.outcome:
                result = result.model_copy(update={'access': result.access.without_volatile(repeat.access)})
                self.__save_result(result)
                self.__save_result(repeat.model_copy(update={'access': result.access}))
            else:
                log.warning(f'The repeat of variant "{variant.reason}" ended with {repeat.outcome}, not {result.outcome}; its volatile paths could not be found.')

        state.versions.setdefault(target, []).append(version)

        outcome = 'job_skipped' if result.outcome == 'skipped' else result.outcome
        trial = Trial(candidate=variant, runs=tuple(runs), outcome=outcome, mocks=mocks, diagnosis=diagnosis)

        return Trace(trial=trial, result=result)

    def __score(self, result: TraceResult) -> tuple[bool, int]:

        return result.outcome == 'success', sum(step.outcome == 'success' for step in result.steps)

    def __save_result(self, result: TraceResult) -> None:

        run_dir = settings.file.output / 'runs' / str(result.id)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / 'result.json').write_text(result.model_dump_json(indent=4))

    def __save_trials(self, trials: dict[str, dict[str, list[Trial]]]) -> None:

        content = {workflow: {job: [trial.model_dump(mode='json') for trial in recorded] for job, recorded in jobs.items()} for workflow, jobs in trials.items()}
        (settings.file.output / 'trials.json').write_text(json.dumps(content, indent=4))

    def __save_versions(self, versions: Versions) -> None:

        content = {f'{workflow}/{job}': [version.model_dump(mode='json') for version in found] for (workflow, job), found in versions.items()}
        (settings.file.output / 'versions.json').write_text(json.dumps(content, indent=4))

runner = Runner()

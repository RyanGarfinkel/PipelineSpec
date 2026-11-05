from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from pipelinespec.models import Constraints, Variant, Workflow
from pipelinespec.constraint import constraint_agent
from pipelinespec import console, log, settings
from singleton_decorator import singleton
from rich.table import Column, Table
from pipelinespec.tools import smt
from rich.console import Group
from rich.live import Live
import json

@singleton
class Pipeline:

    def get_constraints(self, workflows: list[Workflow], sample: int | None = None) -> dict[str, Constraints]:

        log('Finding the conditions of each job...')
        name = 'constraints.json' if sample is None else f'constraints_{sample}.json'

        found: dict[str, Constraints] = {}

        progress = Progress(SpinnerColumn(), TextColumn('[cyan]{task.description}'), BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(), console=console)
        bar = progress.add_task('', total=len(workflows) + sum(len(workflow.jobs) for workflow in workflows))
        table = Table('Pipeline', 'Phase', 'Triggers', *(Column(name, justify='right') for name in ('Gates', 'Variables', 'Constants', 'Unsolved')))

        with Live(Group(table, progress), console=console, vertical_overflow='visible'):

            for workflow in workflows:

                progress.update(bar, description=f'{workflow.name}: finding triggers')
                constraints = found.setdefault(workflow.name, Constraints(triggers=constraint_agent.find_workflow_triggers(workflow, sample)))
                progress.advance(bar)

                for job in workflow.jobs:

                    progress.update(bar, description=f'{workflow.name} / {job.name}: finding conditions')

                    job_constraints = constraint_agent.find_job_constraints(workflow, job, sample)
                    constraints.jobs[job.name] = job_constraints

                    table.add_row(workflow.name, job.name, ', '.join(trigger.event for trigger in constraints.triggers), *(str(len(items)) for items in (job_constraints.gates, job_constraints.variables, job_constraints.constants, job_constraints.unsolved)))
                    progress.advance(bar)

        log(f'Constraints saved to {settings.file.output / name}.')

        return found

    def load_constraints(self, workflows: list[Workflow]) -> dict[str, Constraints]:

        if settings.constraints is None or not settings.constraints.exists():
            raise ValueError(f'There is no constraints file to load: {settings.constraints}.')

        log(f'Loading constraints from {settings.constraints}...')

        found = {name: Constraints.model_validate(entry) for name, entry in json.loads(settings.constraints.read_text()).items()}
        missing = [f'{workflow.name} / {job.name}' for workflow in workflows for job in workflow.jobs if job.name not in found.get(workflow.name, Constraints()).jobs]

        if missing:
            raise ValueError(f'The constraints file has no entry for: {", ".join(missing)}.')

        return found

    def get_variants(self, workflows: list[Workflow], constraints: dict[str, Constraints]) -> list[Variant]:

        variants = []

        for workflow in workflows:
            triggers = constraints[workflow.name].triggers

            for job in workflow.jobs:
                job_constraints = constraints[workflow.name].jobs[job.name]
                variants += [variant.bound(workflow, job, triggers, job_constraints) for variant in smt.solve(job_constraints, triggers)]

        path = settings.file.output / 'variants.json'
        path.write_text(json.dumps([variant.model_dump(mode='json') for variant in variants], indent=4))

        log(f'Z3 produced {len(variants)} variants, saved to {path}.')

        return variants

pipeline = Pipeline()

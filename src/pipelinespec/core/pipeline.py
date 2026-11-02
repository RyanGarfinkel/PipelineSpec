from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from pipelinespec.constraint import constraint_agent
from pipelinespec.models import Variant, Workflow
from pipelinespec import console, log, settings
from singleton_decorator import singleton
from rich.table import Column, Table
from pipelinespec.tools import smt
from rich.console import Group
from rich.live import Live
import json

@singleton
class Pipeline:

    def get_variants(self, workflows: list[Workflow]) -> list[Variant]:

        log('Finding the conditions of each job and generating variants...')

        variants = []

        progress = Progress(SpinnerColumn(), TextColumn('[cyan]{task.description}'), BarColumn(), MofNCompleteColumn(), TimeElapsedColumn(), console=console)
        bar = progress.add_task('', total=len(workflows) + sum(len(workflow.jobs) for workflow in workflows))
        table = Table('Pipeline', 'Phase', 'Triggers', *(Column(name, justify='right') for name in ('Gates', 'Variables', 'Constants', 'Unsolved', 'Variants')))

        with Live(Group(table, progress), console=console, vertical_overflow='visible'):

            for workflow in workflows:

                progress.update(bar, description=f'{workflow.name}: finding triggers')
                workflow_triggers = constraint_agent.find_workflow_triggers(workflow)
                progress.advance(bar)

                for job in workflow.jobs:

                    progress.update(bar, description=f'{workflow.name} / {job.name}: finding conditions')

                    job_constraints = constraint_agent.find_job_constraints(workflow, job)
                    solved = smt.solve(job_constraints, workflow_triggers)
                    variants += [variant.bound(workflow, job, workflow_triggers, job_constraints) for variant in solved]

                    table.add_row(workflow.name, job.name, ', '.join(trigger.event for trigger in workflow_triggers), *(str(len(found)) for found in (job_constraints.gates, job_constraints.variables, job_constraints.constants, job_constraints.unsolved, solved)))
                    progress.advance(bar)

        self.__save_variants(variants)

        log(f'Z3 produced {len(variants)} variants, saved to {settings.file.output / "variants.json"}.')

        return variants

    def load_variants(self) -> list[Variant]:

        if settings.variants is None or not settings.variants.exists():
            raise ValueError(f'There is no variants file to load: {settings.variants}.')

        log(f'Loading variants from {settings.variants}...')

        variants = [Variant.model_validate(variant) for variant in json.loads(settings.variants.read_text())]

        log(f'Loaded {len(variants)} variants.')

        return variants

    def __save_variants(self, variants: list[Variant]) -> None:

        path = settings.file.output / 'variants.json'
        path.write_text(json.dumps([variant.model_dump(mode='json') for variant in variants], indent=4))

pipeline = Pipeline()

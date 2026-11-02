from pydantic import BaseModel, ConfigDict, Field, field_validator
from pathlib import Path
from typing import Any
import yaml
import re

SECRET_REFERENCE = re.compile(r"secrets(?:\.|\[\s*['\"])(\w+)")

class Step(BaseModel):

    model_config = ConfigDict(frozen=True)

    index: int
    id: str
    name: str | None = None
    condition: str | None = None
    uses: str | None = None
    run: str | None = None
    shell: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    inputs: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def parse(cls, index: int, data: dict) -> 'Step':

        env, inputs = data.get('env'), data.get('with')

        return cls(
            index=index,
            id=str(data.get('id') or index),
            name=data.get('name'),
            condition=None if data.get('if') is None else str(data['if']),
            uses=data.get('uses'),
            run=data.get('run'),
            shell=data.get('shell'),
            env={key: str(value) for key, value in env.items()} if isinstance(env, dict) else {},
            inputs=inputs if isinstance(inputs, dict) else {},
        )

class Job(BaseModel):

    name: str = Field(..., frozen=True)
    path: Path = Field(..., frozen=True)
    needs: list[str] = Field(..., frozen=True)
    steps: list[Step] = Field(..., frozen=True)
    uses: str | None = Field(default=None, frozen=True)
    secret_names: list[str] = Field(default_factory=list, frozen=True)

class Workflow(BaseModel):

    name: str = Field(..., frozen=True)
    path: Path = Field(..., frozen=True)
    jobs: list[Job] = Field(..., frozen=True)

    @field_validator('jobs')
    @classmethod
    def sort_jobs(cls, jobs: list[Job]) -> list[Job]:

        ordered = []
        names = {job.name: job for job in jobs}
        visited = set()

        # Sorts jobs based on what is needed first

        def visit(job: Job) -> None:
            if job.name in visited:
                return

            visited.add(job.name)

            for need in job.needs:
                if need not in names:
                    raise ValueError(f'Job "{job.name}" needs "{need}", but it does not exist.')
                visit(names[need])

            ordered.append(job)

        for job in jobs:
            visit(job)

        return ordered

    @classmethod
    def find_all(cls, directory: Path) -> list['Workflow']:

        workflows = {path.resolve(): cls.__parse(path) for path in sorted([*directory.glob('*.yml'), *directory.glob('*.yaml')])}
        repo = directory.parent.parent
        ordered = []
        visited = set()

        # Sorts workflows based on what is needed first

        def visit(path: Path) -> None:
            if path in visited:
                return

            visited.add(path)

            for job in workflows[path].jobs:
                called = (repo / job.uses).resolve() if job.uses and job.uses.startswith('./') else None

                if called in workflows:
                    visit(called)

            ordered.append(workflows[path])

        for path in workflows:
            visit(path)

        return ordered


    # NOTE: Possibly unneeded, still needs review
    @classmethod
    def find(cls, directory: Path, name: str, job: str | None = None) -> 'Workflow':

        for workflow in cls.find_all(directory):
            if workflow.name == name and (job is None or any(candidate.name == job for candidate in workflow.jobs)):
                return workflow

        raise ValueError(f'Workflow "{name}" not found.' if job is None else f'Job "{job}" not found in workflow "{name}".')

    def get_job_yaml(self, job: str) -> str:

        text = self.path.read_text()
        lines = text.splitlines()
        jobs_key, jobs = next((key, value) for key, value in yaml.compose(text).value if key.value == 'jobs')
        key, value = next((key, value) for key, value in jobs.value if key.value == job)
        numbers = [jobs_key.start_mark.line, *range(key.start_mark.line, value.end_mark.line + (1 if value.end_mark.column else 0))]

        return '\n'.join(f'{number + 1}\t{lines[number]}' for number in numbers)

    @classmethod
    def __parse(cls, path: Path) -> 'Workflow':

        if not path.exists():
            raise FileNotFoundError(f'Workflow file not found: {path}')

        with open(path, 'r') as f:
            workflow_contents = yaml.safe_load(f)

        jobs = []
        for name, data in workflow_contents.get('jobs', {}).items():
            needs = data.get('needs', [])
            steps = [Step.parse(index, step) for index, step in enumerate(data.get('steps', []))]

            jobs.append(Job(
                name=name,
                path=path,
                needs=[needs] if isinstance(needs, str) else needs,
                steps=steps,
                uses=data.get('uses'),
                secret_names=sorted(set(SECRET_REFERENCE.findall(yaml.safe_dump(data))))
            ))

        return cls(
            name=workflow_contents.get('name', ''),
            path=path,
            jobs=jobs
        )

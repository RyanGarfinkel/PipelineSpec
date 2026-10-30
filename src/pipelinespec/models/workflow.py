from pydantic import BaseModel, ConfigDict, Field, field_validator
from pathlib import Path
from typing import Any
import yaml
import re

SECRET_REFERENCE = re.compile(r"secrets(?:\.|\[\s*['\"])(\w+)")
INHERITED = ['permissions', 'env', 'defaults']

def references(*blocks) -> dict[str, list[str]]:

    env: dict[str, set[str]] = {}

    for block in blocks:
        if not isinstance(block, dict):
            continue

        for key, value in block.items():
            env.setdefault(key, set()).update(SECRET_REFERENCE.findall(str(value)))

    return {key: sorted(secrets) for key, secrets in env.items()}

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
    env: list[str] = Field(default_factory=list, frozen=True)
    secrets: dict[str, list[str]] = Field(default_factory=dict, frozen=True)
    scopes: dict[str, dict[str, list[str]]] = Field(default_factory=dict, frozen=True)
    secret_names: list[str] = Field(default_factory=list, frozen=True)

class Workflow(BaseModel):

    name: str = Field(..., frozen=True)
    path: Path = Field(..., frozen=True)
    jobs: list[Job] = Field(..., frozen=True)

    # Orders jobs based on needs first

    @field_validator('jobs')
    @classmethod
    def sort_jobs(cls, jobs: list[Job]) -> list[Job]:

        ordered = []
        names = {job.name: job for job in jobs}
        visited = set()

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
    def find(cls, directory: Path, name: str, job: str | None = None) -> 'Workflow':

        for path in [*directory.glob('*.yml'), *directory.glob('*.yaml')]:
            workflow = cls.parse(path)

            if workflow.name == name and (job is None or any(candidate.name == job for candidate in workflow.jobs)):
                return workflow

        raise ValueError(f'Workflow "{name}" not found.' if job is None else f'Job "{job}" not found in workflow "{name}".')

    def excerpt(self, job: str) -> str:

        lines = self.path.read_text().splitlines()
        blocks, heading, key, value = self.__find(job)
        numbers = [number for name in INHERITED if name in blocks for number in self.__span(*blocks[name])]
        numbers += [heading.start_mark.line, *self.__span(key, value)]

        return '\n'.join(f'{number + 1}\t{lines[number]}' for number in numbers)

    def __find(self, job: str):

        blocks = {key.value: (key, value) for key, value in yaml.compose(self.path.read_text()).value}
        heading, jobs = blocks['jobs']
        key, value = next((key, value) for key, value in jobs.value if key.value == job)

        return blocks, heading, key, value

    def __span(self, key: yaml.Node, value: yaml.Node) -> range:

        return range(key.start_mark.line, value.end_mark.line + (1 if value.end_mark.column else 0))

    @classmethod
    def parse(cls, path: Path) -> 'Workflow':

        if not path.exists():
            raise FileNotFoundError(f'Workflow file not found: {path}')

        with open(path, 'r') as f:
            workflow_contents = yaml.safe_load(f)

        jobs = []
        for name, data in workflow_contents.get('jobs', {}).items():
            needs = data.get('needs', [])
            steps = [Step.parse(index, step) for index, step in enumerate(data.get('steps', []))]

            outer = [workflow_contents.get('env'), data.get('env')]
            env = references(*outer, *[step.env for step in steps])

            jobs.append(Job(
                name=name,
                path=path,
                needs=[needs] if isinstance(needs, str) else needs,
                steps=steps,
                uses=data.get('uses'),
                env=sorted(env),
                secrets={key: secrets for key, secrets in env.items() if secrets},
                scopes={step.id: references(*outer, step.env) for step in steps},
                secret_names=sorted(set(SECRET_REFERENCE.findall(yaml.safe_dump(data))))
            ))

        return cls(
            name=workflow_contents.get('name', ''),
            path=path,
            jobs=jobs
        )

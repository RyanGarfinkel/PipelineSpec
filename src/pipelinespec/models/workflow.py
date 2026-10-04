from pydantic import BaseModel, Field, field_validator
from pathlib import Path
import yaml

class Job(BaseModel):

    name: str = Field(..., frozen=True)
    path: Path = Field(..., frozen=True)
    needs: list[str] = Field(..., frozen=True)
    steps: list[dict] = Field(..., frozen=True)

class Workflow(BaseModel):

    name: str = Field(..., frozen=True)
    path: Path = Field(..., frozen=True)
    triggers: list[dict] = Field(..., frozen=True)
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

    # Extract workflow info from yml

    @classmethod
    def parse(cls, path: Path) -> 'Workflow':

        if not path.exists():
            raise FileNotFoundError(f'Workflow file not found: {path}')
        
        with open(path, 'r') as f:
            workflow_contents = yaml.safe_load(f)        

        jobs = []
        for name, data in workflow_contents.get('jobs', {}).items():
            needs = data.get('needs', [])
            jobs.append(Job(
                name=name,
                path=path,
                needs=[needs] if isinstance(needs, str) else needs,
                steps=data.get('steps', [])
            ))

        return cls(
            name=workflow_contents.get('name', ''),
            path=path,
            triggers=workflow_contents.get('on', []),
            jobs=jobs
        )

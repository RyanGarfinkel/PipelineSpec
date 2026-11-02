from pydantic import BaseModel, ConfigDict, Field
from .constraints import JobConstraints, WorkflowTrigger
from .workflow import Job, Workflow
from .variable import Scalar
from copy import deepcopy
from typing import Any

INPUT_EVENTS = ('workflow_dispatch', 'workflow_call')

class Context(BaseModel):

    model_config = ConfigDict(frozen=True)

    event: str = Field(default='push', description='Event name passed to act, e.g. push, pull_request, release.')
    payload: dict[str, Any] = Field(default_factory=dict, description='Event payload, written to the run directory and passed to act with -e.')
    actor: str | None = Field(default=None, description='Value of github.actor. The act default is used when None.')

    @property
    def event_file(self) -> dict[str, Any]:

        payload = {key: value for key, value in self.payload.items() if key != 'inputs'}

        if self.event in INPUT_EVENTS and 'inputs' in self.payload:
            payload['inputs'] = {name: str(value).lower() if isinstance(value, bool) else str(value) for name, value in self.payload['inputs'].items()}

        return payload

class Variant(BaseModel):

    model_config = ConfigDict(frozen=True)

    workflow: str = Field(default='', description='The workflow the run belongs to. Empty until bound.')
    job: str = Field(default='', description='The job to run. Empty until bound.')
    reason: str
    assignment: dict[str, Scalar]
    context: Context | None = Field(default=None, description='What act is given. None until bound.')
    constraints: JobConstraints | None = Field(default=None, description='The conditions of the job, which go into the map. None until bound.')
    call: bool = Field(default=False, description='The job only calls a reusable workflow: it is recorded in the map but not traced.')
    needs: tuple[str, ...] = Field(default=(), description='The jobs of the workflow that must succeed before this one.')
    uses: str | None = Field(default=None, description='The reusable workflow the job calls.')

    def bound(self, workflow: Workflow, job: Job, triggers: list[WorkflowTrigger], constraints: JobConstraints) -> 'Variant':

        event = self.assignment['event']
        trigger = next(trigger for trigger in triggers if trigger.event == event)
        actor, payload = None, deepcopy(trigger.payload)

        for target, value in {**constraints.constants, **self.assignment}.items():
            if target == 'actor':
                actor = value
            elif target != 'event':
                parent = payload
                *path, key = target.removeprefix('payload.').split('.')

                for part in path:
                    parent = parent.setdefault(part, {})

                parent[key] = value

        return self.model_copy(update={
            'workflow': workflow.name,
            'job': job.name,
            'context': Context(event=event, payload=payload, actor=actor),
            'constraints': constraints,
            'call': job.uses is not None,
            'needs': tuple(job.needs),
            'uses': job.uses,
        })

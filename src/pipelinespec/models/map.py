from pydantic import BaseModel, ConfigDict
from .constraints import Unsolved
from .variable import Variable
from .access import Access
from typing import Literal
from .gate import Gate
from uuid import UUID

class AccessVariant(BaseModel):

    model_config = ConfigDict(frozen=True)

    outcome: Literal['success', 'failure', 'skipped', 'unknown']
    access: Access
    contexts: tuple[dict[str, str | bool], ...]

class Tested(BaseModel):

    model_config = ConfigDict(frozen=True)

    context: dict[str, str | bool]
    reason: str
    outcome: Literal['success', 'failure', 'job_skipped', 'unknown']
    runs: tuple[UUID, ...]
    diagnosis: str | None = None

class JobNode(BaseModel):

    model_config = ConfigDict(frozen=True)

    workflow: str
    name: str
    events: tuple[str, ...]
    needs: tuple[str, ...]
    uses: str | None
    gates: tuple[Gate, ...]
    variables: dict[str, Variable]
    unsolved: tuple[Unsolved, ...]
    tested: tuple[Tested, ...]
    variants: tuple[AccessVariant, ...]

class AccessMap(BaseModel):

    model_config = ConfigDict(frozen=True)

    repository: str
    jobs: tuple[JobNode, ...]

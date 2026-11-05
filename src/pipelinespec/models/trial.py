from pydantic import BaseModel, ConfigDict, Field
from .run import TraceResult
from .variant import Variant
from typing import Literal
from .mock import Mocks
from uuid import UUID

class Diagnosis(BaseModel):

    fixable: bool = Field(..., description='True when the failure is one that adding credentials or mocks can fix (and you did), false when it is a real failure of the job.')
    reason: str = Field(..., description='One or two sentences: what failed and why, and what was added if anything.')

class Trial(BaseModel):

    model_config = ConfigDict(frozen=True)

    candidate: Variant
    runs: tuple[UUID, ...] = ()
    outcome: Literal['success', 'failure', 'job_skipped', 'unknown']
    mocks: Mocks = Field(default_factory=Mocks)
    diagnosis: Diagnosis | None = None

class Trace(BaseModel):

    model_config = ConfigDict(frozen=True)

    trial: Trial
    result: TraceResult

from pydantic import BaseModel, ConfigDict, computed_field
from .access import Access, FileAccess, NetworkAccess
from typing import Literal
from pathlib import Path
from uuid import UUID

class StepResult(BaseModel):

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    outcome: Literal['success', 'failure', 'skipped']
    exit_code: int | None = None
    skipped_because: Literal['condition', 'earlier_failure'] | None = None

class JobRun(BaseModel):

    model_config = ConfigDict(frozen=True)

    workflow: str
    job: str
    outcome: Literal['success', 'failure', 'skipped', 'unknown']
    steps: tuple[StepResult, ...]

class TraceResult(BaseModel):

    model_config = ConfigDict(frozen=True)

    id: UUID
    path: Path
    job: str
    outcome: Literal['success', 'failure', 'skipped', 'unknown']
    steps: tuple[StepResult, ...] = ()
    access: Access = Access()
    commands: tuple[tuple[str, ...], ...] = ()
    unattributed: Access = Access()

    @property
    def total(self) -> Access:

        return self.access.merge(self.unattributed)

    @computed_field
    @property
    def files(self) -> frozenset[FileAccess]:

        return self.access.files

    @computed_field
    @property
    def networks(self) -> frozenset[NetworkAccess]:

        return self.total.networks

    @computed_field
    @property
    def connections(self) -> frozenset[str]:

        return self.total.connections

    @computed_field
    @property
    def secrets(self) -> frozenset[str]:

        return self.total.secrets

    @computed_field
    @property
    def referenced(self) -> frozenset[str]:

        return self.total.referenced

class Version(BaseModel):

    run: UUID
    outcome: str
    steps: list[tuple[str, str]]

from pydantic import BaseModel, ConfigDict
from typing import Literal
from pathlib import Path
from uuid import UUID

class FileAccess(BaseModel):

    model_config = ConfigDict(frozen=True)

    path: str
    access: frozenset[Literal['read', 'write', 'execute']]

class NetworkAccess(BaseModel):

    model_config = ConfigDict(frozen=True)

    scheme: str
    host: str
    port: int
    method: str
    path: str
    headers: frozenset[tuple[str, str]]
    secrets: frozenset[str] = frozenset()
    status: int | None
    result: Literal['mocked', 'passed', 'failed']

class TraceResult(BaseModel):

    model_config = ConfigDict(frozen=True)

    id: UUID
    path: Path
    job: str
    
    files: frozenset[FileAccess]
    networks: frozenset[NetworkAccess]
    env: frozenset[str]
    secrets: frozenset[str]

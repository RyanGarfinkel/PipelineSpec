from pydantic import BaseModel, ConfigDict
from collections.abc import Iterable
from typing import Literal

class FileAccess(BaseModel):

    model_config = ConfigDict(frozen=True)

    path: str
    access: frozenset[Literal['read', 'write', 'execute']]

    @classmethod
    def combine(cls, accesses: Iterable['FileAccess']) -> frozenset['FileAccess']:

        kinds: dict[str, set[str]] = {}

        for item in accesses:
            kinds.setdefault(item.path, set()).update(item.access)

        return frozenset(cls(path=path, access=frozenset(found)) for path, found in kinds.items())

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

class Access(BaseModel):

    model_config = ConfigDict(frozen=True)

    files: frozenset[FileAccess] = frozenset()
    networks: frozenset[NetworkAccess] = frozenset()
    connections: frozenset[str] = frozenset()
    secrets: frozenset[str] = frozenset()
    referenced: frozenset[str] = frozenset()

    def merge(self, other: 'Access') -> 'Access':

        secrets = self.secrets | other.secrets

        return Access(
            files=FileAccess.combine(self.files | other.files),
            networks=self.networks | other.networks,
            connections=self.connections | other.connections,
            secrets=secrets,
            referenced=(self.referenced | other.referenced) - secrets,
        )

    def without_volatile(self, other: 'Access') -> 'Access':

        merged = self.merge(other)
        shared = {item.path for item in self.files} & {item.path for item in other.files}

        return merged.model_copy(update={'files': frozenset(item for item in merged.files if item.path in shared)})

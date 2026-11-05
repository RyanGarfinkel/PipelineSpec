from pydantic import BaseModel, ConfigDict
from typing import Literal

class Event(BaseModel):

    model_config = ConfigDict(frozen=True)

    workflow: str
    job: str
    pid: int

class FileEvent(Event):

    time: float
    path: str
    kind: Literal['read', 'write', 'execute']
    argv: tuple[str, ...] = ()

class ConnectionEvent(Event):

    time: float
    address: str
    port: int

class SocketEvent(Event):

    time: float
    source_port: int
    address: str
    port: int

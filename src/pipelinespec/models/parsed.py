from .event import ConnectionEvent, FileEvent, SocketEvent
from pydantic import BaseModel, ConfigDict

class Parsed(BaseModel):

    model_config = ConfigDict(frozen=True)

    files: list[FileEvent]
    connections: list[ConnectionEvent]
    sockets: list[SocketEvent]
    markers: dict[tuple[str, str], frozenset[str]]

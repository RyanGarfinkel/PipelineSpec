from typing import Any, Literal, Set, List
from pydantic import BaseModel, Field

# Input to trace

class MockNetworkResult(BaseModel):

    url: str = Field(..., frozen=True, description='URL of the network request.')
    status: int = Field(..., frozen=True, description='Status code to be returned from the network request.')
    response: Any = Field(..., frozen=True, description='Response to be returned from the network request.')

class TraceConfig(BaseModel):

    networks: List[MockNetworkResult] = Field(..., frozen=True, description='List of network requests to be mocked.')
    secrets: dict[str, str] = Field(..., frozen=True, description='Dictionary of GitHub secrets to be mocked.')
    env: dict[str, str] = Field(..., frozen=True, description='Dictionary of environment variables to be mocked.')

# Returned from trace

class FileAccess(BaseModel):

    path: str = Field(..., frozen=True)
    access_type: Literal['read', 'write', 'execute'] = Field(..., frozen=True)

class NetworkAccess(BaseModel):

    url: str = Field(..., frozen=True)

class TraceResult(BaseModel):

    files: Set[FileAccess] = Field(..., frozen=True)
    networks: List[NetworkAccess] = Field(..., frozen=True)
    secrets: Set[str] = Field(..., frozen=True)
    env: Set[str] = Field(..., frozen=True)

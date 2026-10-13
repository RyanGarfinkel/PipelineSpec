from pydantic import BaseModel, ConfigDict, Field
from typing import Any

class MockedCall(BaseModel):

    model_config = ConfigDict(frozen=True)

    method: str = Field(..., description='HTTP method of the request to mock.')
    url: str = Field(..., description='Glob matched against scheme, host and path (no query string), e.g. https://api.github.com/repos/*/deployments.')
    status: int = Field(default=200, description='Status code to return.')
    headers: dict[str, str] = Field(default_factory=dict, description='Headers to return.')
    body: Any = Field(default=None, description='JSON body to return.')

class TraceConfig(BaseModel):

    model_config = ConfigDict(frozen=True)

    workflow: str
    job: str
    mocked_calls: list[MockedCall] = Field(default_factory=list)

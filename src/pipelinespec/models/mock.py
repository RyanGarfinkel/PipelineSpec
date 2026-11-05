from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Literal

class MockedCall(BaseModel):

    model_config = ConfigDict(frozen=True)

    method: str = Field(..., description='HTTP method of the request to mock.')
    url: str = Field(..., description='Glob matched against scheme, host and path (no query string), e.g. https://api.github.com/repos/*/deployments.')
    status: int = Field(default=200, description='Status code to return.')
    headers: dict[str, str] = Field(default_factory=dict, description='Headers to return.')
    body: Any = Field(default=None, description='JSON body to return. None returns an empty body.')
    text: str | None = Field(default=None, description='Raw body returned as is, not JSON encoded. Takes precedence over body; an empty string is an empty body.')
    failure: Literal['reset', 'timeout', 'unreachable'] | None = Field(default=None, description='Fail the request instead of returning a response. reset drops the connection, timeout stalls for delay seconds and then drops it, unreachable returns 502 (how a client behind an HTTP proxy sees a refused connection or a DNS failure).')
    delay: float = Field(default=30.0, description='Seconds a timeout failure stalls before dropping the connection.')

class Mocks(BaseModel):

    credentials: list[str] = Field(default_factory=list, description='Secret names added by the diagnoser, beyond the ones the job references (the tracer mocks those itself).')
    calls: list[MockedCall] = Field(default_factory=list)

    def merge(self, other: 'Mocks') -> None:

        self.credentials += [name for name in other.credentials if name not in self.credentials]
        replaced = {(call.method, call.url) for call in other.calls}
        self.calls = [*[call for call in self.calls if (call.method, call.url) not in replaced], *other.calls]

from pydantic import BaseModel, ConfigDict, Field
from .constraints import Constraints
from typing import Any

class Trigger(BaseModel):

    model_config = ConfigDict(frozen=True)

    event: str = Field(..., description='The event name, one of the events the workflow lists.')
    payload: dict[str, Any] = Field(default_factory=dict, description='The event payload: only the fields the workflow\'s conditions on this event read, nested as in the event\'s real payload, with values that satisfy them. Empty when the event has no conditions.')

class Answer(BaseModel):

    triggers: list[Trigger] = Field(default_factory=list, description='One concrete example per event the workflow lists.')
    jobs: dict[str, Constraints] = Field(default_factory=dict, description='The constraints of each analyzed job, by job id.')

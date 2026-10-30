from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator
from typing import Annotated, Literal
import re

Scalar = str | bool | int
Kind = Literal['str', 'bool', 'int']

def kind(value: Scalar) -> Kind:

    return {bool: 'bool', int: 'int'}.get(type(value), 'str')

def target(value: str) -> str:

    if value == 'event':
        raise ValueError('event is built in: use the name event in a term without declaring a variable for it.')

    if not re.fullmatch(r'actor|payload\..+', value):
        raise ValueError(f'{value!r} is not something the run context sets. A target is actor or payload.<path>; a condition on anything else goes in add_unsolved.')

    return value

Target = Annotated[str, AfterValidator(target)]

class Variable(BaseModel):

    model_config = ConfigDict(frozen=True)

    target: Target = Field(..., description='Where the value lives in the run context: actor, or payload.<dotted path> (e.g. payload.ref, payload.pull_request.base.ref, payload.inputs.<name>).')
    values: tuple[Scalar, ...] = Field(..., min_length=1, description='The values worth testing, all of one type: strings, true/false, or numbers. The first is the most ordinary one; include one that makes the condition true and one that makes it false.')

    @property
    def kind(self) -> Kind:

        return kind(self.values[0])

    @model_validator(mode='after')
    def validate_values(self) -> 'Variable':

        if len({kind(value) for value in self.values}) > 1:
            raise ValueError(f'The values {list(self.values)} mix types; use strings, true/false or numbers, one type.')

        return self

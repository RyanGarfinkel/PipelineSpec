from pydantic import BaseModel, ConfigDict, Field
from typing import Annotated, Literal
from .variable import Scalar
import json

Operator = Literal['==', '!=', '<', '<=', '>', '>=', 'starts_with', 'ends_with', 'contains']

class Term(BaseModel):

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description='The variable compared, by the name it has from add_variable, or the built-in name event.')
    op: Operator = Field(..., description='== or != for any value; <, <=, > or >= for numbers; starts_with, ends_with or contains for strings. Negation goes here: use != or compare a boolean with false.')
    value: Scalar = Field(..., description='The value compared with: a string, a number, or true/false, of the same type as the variable.')

Clause = Annotated[list[Term], Field(min_length=1)]

class Gate(BaseModel):

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description='Short unique name, e.g. step.deploy.if or deploy.sh.upload.')
    type: Literal['scope', 'branch'] = Field(..., description='scope: the condition of the job or a step; when it is false the job or step is skipped. branch: a condition inside code a step runs; the step still runs but takes another path.')
    location: str = Field(..., description='Where the condition is written, as file:line, e.g. .github/workflows/ci.yml:20.')
    any_of: list[Clause] = Field(..., min_length=1, description='The condition as alternatives: it holds when any one of the lists holds, and a list holds when all of its terms do.')

    @property
    def condition(self) -> str:

        clauses = [' && '.join(f'{term.name} {term.op} {json.dumps(term.value)}' for term in clause) for clause in self.any_of]

        return clauses[0] if len(clauses) == 1 else ' || '.join(f'({clause})' for clause in clauses)

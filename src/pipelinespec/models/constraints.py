from pydantic import BaseModel, ConfigDict, Field
from .variable import Scalar, Variable
from .gate import Gate

class Unsolved(BaseModel):

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description='Name for the condition that could not be expressed.')
    reason: str = Field(..., description='Why it cannot be set from the run context, e.g. it reads needs.build.outputs.version or a step output.')
    location: str = Field(..., description='Where it is written, as file:line.')

class Constraints(BaseModel):

    events: list[str] = Field(default_factory=list, description='The events that trigger the workflow, in the order of its on: block.')
    gates: list[Gate] = Field(default_factory=list, description='The conditions that decide whether the job and its steps run and which path they take. A variant to test is generated for each gate holding and for each failing.')
    variables: dict[str, Variable] = Field(default_factory=dict, description='The inputs the gates are written over, each declared once with its target and the values to test.')
    constants: dict[str, Scalar] = Field(default_factory=dict, description='Fixed values the job needs to run normally, keyed by target (for example payload.pull_request.number or payload.pull_request.base.sha). A target that a gate compares is not a constant.')
    unsolved: list[Unsolved] = Field(default_factory=list, description='Conditions that cannot be set from the run context. They are recorded, not tested.')

    @property
    def aliases(self) -> dict[str, str]:

        found: dict[str, set[str]] = {}

        for name, variable in self.variables.items():
            parts = variable.target.split('.')

            for spelling in {'.'.join(parts[index:]) for index in range(len(parts))}:
                found.setdefault(spelling, set()).add(name)

        return {**{spelling: next(iter(names)) for spelling, names in found.items() if len(names) == 1}, **{name: name for name in self.variables}}

    @property
    def domains(self) -> dict[str, list[Scalar]]:

        found = {'event': list(self.events)}

        for variable in self.variables.values():
            values = found.setdefault(variable.target, [])
            values.extend(value for value in variable.values if value not in values)

        return found

class Candidate(BaseModel):

    model_config = ConfigDict(frozen=True)

    reason: str
    assignment: dict[str, Scalar]

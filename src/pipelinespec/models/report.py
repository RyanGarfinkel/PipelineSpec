from pydantic import BaseModel, ConfigDict

class Check(BaseModel):

    model_config = ConfigDict(frozen=True)

    name: str
    passed: bool
    detail: str = ''

class Report(BaseModel):

    model_config = ConfigDict(frozen=True)

    checks: tuple[Check, ...]

    @property
    def passed(self) -> bool:

        return all(check.passed for check in self.checks)

from pydantic import BaseModel, ConfigDict
from datetime import datetime

class Sample(BaseModel):

    model_config = ConfigDict(frozen=True)

    name: str
    clone_url: str
    commit: str
    commit_date: datetime
    stars: int
    forks: int
    topics: list[str]
    primary_language: str | None
    languages: list[str]
    workflows: int
    jobs: int
    files: int
    lines: int

from pydantic import BaseModel, Field

class Sample(BaseModel):

    name: str = Field(..., frozen=True)
    clone_url: str = Field(..., frozen=True)
    api_url: str = Field(..., frozen=True)
    workflows: list[str] = Field(..., frozen=True)

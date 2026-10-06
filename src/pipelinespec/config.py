from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Literal
from pathlib import Path

class Settings(BaseSettings):

    output_dir: Path = Field(default=Path('data'))
    repo: Path | None = Field(default=None)
    arch: Literal['linux/amd64', 'linux/arm64'] = Field(default='linux/arm64')

settings = Settings()

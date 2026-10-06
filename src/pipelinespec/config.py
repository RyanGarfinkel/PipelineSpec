from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from typing import Literal
from pathlib import Path

class Settings(BaseSettings):

    output_dir: Path = Field(default=Path('data'))
    repo: Path | None = Field(default=None)
    certificate: Path | None = Field(default=None)
    container: str = Field(default='ubuntu-latest=catthehacker/ubuntu:act-latest')
    arch: Literal['linux/amd64', 'linux/arm64'] = Field(default='linux/arm64')
    docker_compose: Path = Field(default=Path(__file__).resolve().parent / 'docker' / 'docker-compose.yml')

    @field_validator('certificate')
    @classmethod
    def expand_certificate(cls, value: Path | None) -> Path | None:

        return value.expanduser() if value is not None else None

settings = Settings()

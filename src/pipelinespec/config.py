from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings
from typing import Literal
from pathlib import Path

class FileSettings(BaseModel):

    output: Path = Field(default=Path('results'))

    @property
    def secrets(self) -> Path:
        return (self.output / 'used.secrets').resolve()

    @property
    def env(self) -> Path:
        return (self.output / 'used.env').resolve()

class TraceSettings(BaseSettings):

    container: str = Field(default='ubuntu-latest=pipeline-runner:latest')
    arch: Literal['linux/amd64', 'linux/arm64'] = Field(default='linux/arm64')
    mitm_certificate: Path | None = Field(default=None, validation_alias='CERTIFICATE')
    addon: Path = Field(default=Path(__file__).resolve().parent / 'docker' / 'addon.py', frozen=True)

    @field_validator('container')
    @classmethod
    def validate_container_label(cls, value: str) -> str:
        if '=' not in value:
            return f'ubuntu-latest={value}'
        return value

    @field_validator('mitm_certificate')
    @classmethod
    def expand_certificate(cls, value: Path | None) -> Path | None:
        return value.expanduser() if value is not None else None

class Settings(BaseSettings):

    repo: Path | None = Field(default=None)
    file: FileSettings = Field(default_factory=FileSettings)
    trace: TraceSettings = Field(default_factory=TraceSettings)
    # agent: AgentSettings = Field(default_factory=AgentSettings)

settings = Settings()

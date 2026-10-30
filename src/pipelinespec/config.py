from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, Field, field_validator
from typing import Literal
from pathlib import Path
import re

class FileSettings(BaseModel):

    output: Path = Field(default=Path('results'))

class TraceSettings(BaseSettings):

    container: str = Field(default='ubuntu-latest=catthehacker/ubuntu:act-latest')
    arch: Literal['linux/amd64', 'linux/arm64'] = Field(default='linux/arm64')
    ebpf_image: str = Field(default='pipeline-ebpf:latest')
    mitm_certificate: Path | None = Field(default=None, validation_alias='CERTIFICATE')
    addon: Path = Field(default=Path(__file__).resolve().parent / 'docker' / 'addon.py', frozen=True)
    body_limit: int = Field(default=2048, ge=0)

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

class AgentSettings(BaseSettings):

    model_config = SettingsConfigDict(env_prefix='PIPELINESPEC_AGENT_', protected_namespaces=())

    retries: int = Field(default=5, ge=1)
    model: str = Field(default='claude-sonnet-5-5')
    url: str | None = Field(default=None)
    max_items: int = Field(default=100, ge=1)
    max_steps: int = Field(default=40, ge=1)
    max_tokens: int = Field(default=4096, ge=1)

    @property
    def provider(self) -> Literal['anthropic', 'openai', 'local']:
        name = self.model.lower()

        if name.startswith('claude'):
            return 'anthropic'

        return 'openai' if re.match(r'(gpt|chatgpt|o\d)', name) else 'local'

class Settings(BaseSettings):

    model_config = SettingsConfigDict(validate_assignment=True)

    repo: Path | None = Field(default=None)
    variants_only: bool = Field(default=False)
    file: FileSettings = Field(default_factory=FileSettings)
    trace: TraceSettings = Field(default_factory=TraceSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)

    @field_validator('repo')
    @classmethod
    def resolve_repo(cls, value: Path | None) -> Path | None:
        return value.expanduser().resolve() if value is not None else None

settings = Settings()

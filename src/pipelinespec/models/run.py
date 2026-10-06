from pydantic import BaseModel, Field
from pipelinespec import settings
from uuid import UUID, uuid4
from pathlib import Path
import os

class JobRun(BaseModel):

    id: UUID = Field(default_factory=uuid4, frozen=True)

    @property
    def output_dir(self) -> Path:
        if not os.path.exists(settings.output_dir / 'runs' / str(self.id)):
            os.makedirs(settings.output_dir / 'runs' / str(self.id), exist_ok=True)
        
        return Path(settings.output_dir) / 'runs' / str(self.id)

    @property
    def secrets_file(self) -> Path:
        return self.output_dir / 'job.secrets'

    @property
    def env_file(self) -> Path:
        return self.output_dir / 'job.env'

    @property
    def logs_file(self) -> Path:
        return self.output_dir / 'run.log'

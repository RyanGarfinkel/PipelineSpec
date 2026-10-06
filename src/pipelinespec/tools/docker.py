from singleton_decorator import singleton
from pipelinespec.models import JobRun
from pipelinespec import settings
import subprocess
import os

@singleton
class DockerCompose:
    
    def network(self, job_run: JobRun) -> str:
        
        return f'{job_run.id}_sandbox'

    def up(self, job_run: JobRun) -> None:

        self.__compose(job_run, 'up', '-d', '--wait')
    
    def down(self, job_run: JobRun) -> None:
        
        self.__compose(job_run, 'down')

    def save_logs(self, job_run: JobRun) -> None:
        
        result = self.__compose(job_run, 'logs', 'proxy', check=False)

        with open(job_run.output_dir / 'proxy.log', 'w') as f:
            f.write(result.stdout + result.stderr)

    def __compose(self, job_run: JobRun, *args: str, check: bool = True) -> subprocess.CompletedProcess:

        if settings.certificate is None:
            raise ValueError('Certificate directory is not set.')

        env = {
            **os.environ,
            'RUN_DIR': str(job_run.output_dir.resolve()),
            'CERTS_DIR': str(settings.certificate.resolve()),
        }

        cmd = [
            'docker',
            'compose',
            '-p', str(job_run.id),
            '-f', str(settings.docker_compose),
            *args,
        ]

        return subprocess.run(cmd,env=env, capture_output=True, text=True, check=check)

docker_compose = DockerCompose()

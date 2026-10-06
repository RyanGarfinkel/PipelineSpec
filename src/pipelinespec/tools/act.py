from pipelinespec.models import Job, JobRun
from singleton_decorator import singleton
from pipelinespec import settings
import subprocess

@singleton
class Act:

    def run(self, job: Job, job_run: JobRun) -> int:
        
        cmd = [
            'act',
            '-P', 'ubuntu-latest=catthehacker/ubuntu:act-latest',
            '--container-daemon-socket', '-',
            '--container-architecture', settings.arch,
            '-W', job.path.resolve(),
            '-j', job.name,
            '--secret-file', job_run.secrets_file,
            '--env-file', job_run.env_file,
        ]

        with open(job_run.logs_file, 'w') as f:
            result = subprocess.run(cmd, cwd=settings.repo, stdout=f, stderr=subprocess.STDOUT, text=True)

        return result.returncode

act = Act()

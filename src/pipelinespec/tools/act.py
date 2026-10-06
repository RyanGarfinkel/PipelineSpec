from pipelinespec.models import Job, JobRun
from singleton_decorator import singleton
from pipelinespec import settings
import subprocess

PROXY_URL = 'http://proxy:8080'
CERT_PATH = '/pspec/ca.pem'

@singleton
class Act:

    def run(self, job: Job, job_run: JobRun, network: str) -> int:

        cert_file = settings.certificate.resolve() / 'mitmproxy-ca-cert.pem'

        env = {
            'HTTP_PROXY': PROXY_URL,
            'HTTPS_PROXY': PROXY_URL,
            'SSL_CERT_FILE': CERT_PATH,
            'NODE_EXTRA_CA_CERTS': CERT_PATH,
            'REQUESTS_CA_BUNDLE': CERT_PATH,
        }

        cmd = [
            'act',
            '-P', settings.container,
            '--container-daemon-socket', '-',
            '--container-architecture', settings.arch,
            '--network', network,
            '--no-cache-server',
            '--container-options', f'-v {cert_file}:{CERT_PATH}:ro',
            '-W', job.path.resolve(),
            '-j', job.name,
            '--secret-file', job_run.secrets_file.resolve(),
            '--env-file', job_run.env_file.resolve(),
        ]

        for name, value in env.items():
            cmd += ['--env', f'{name}={value}']

        with open(job_run.logs_file, 'w') as f:
            result = subprocess.run(cmd, cwd=settings.repo, stdout=f, stderr=subprocess.STDOUT, text=True)

        return result.returncode

act = Act()

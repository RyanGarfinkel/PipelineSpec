from singleton_decorator import singleton
from pipelinespec.models import Job
from pipelinespec import settings
from pathlib import Path
import subprocess

CERT_PATH = '/pspec/ca.pem'
HOOK_PATH = '/pspec/envhook.so'
TRACE_PATH = '/trace'

@singleton
class Act:

    def run(self, job: Job, run_dir: Path, proxy_port: int, trace_dir: Path) -> int:

        proxy_url = f'http://host.docker.internal:{proxy_port}'
        cert_file = settings.trace.mitm_certificate.resolve() / 'mitmproxy-ca-cert.pem'
        
        env = {
            'HTTP_PROXY': proxy_url,
            'HTTPS_PROXY': proxy_url,
            'SSL_CERT_FILE': CERT_PATH,
            'NODE_EXTRA_CA_CERTS': CERT_PATH,
            'REQUESTS_CA_BUNDLE': CERT_PATH,
            'LD_PRELOAD': HOOK_PATH,
        }

        options = [
            f'-v {cert_file}:{CERT_PATH}:ro',
            f'-v {trace_dir.resolve()}:{TRACE_PATH}',
            '--cap-add SYS_PTRACE',
            '--add-host host.docker.internal:host-gateway',
        ]

        cmd = [
            'act',
            '-P', settings.trace.container,
            '--container-daemon-socket', '-',
            '--container-architecture', settings.trace.arch,
            '--pull=false',
            '--no-cache-server',
            '--json',
            '--container-options', ' '.join(options),
            '-W', str(job.path.resolve()),
            '-j', job.name,
            '--secret-file', str(settings.file.secrets),
            '--env-file', str(settings.file.env),
        ]

        for name, value in env.items():
            cmd += ['--env', f'{name}={value}']

        with open(run_dir / 'run.jsonl', 'w') as f:
            process = subprocess.run(cmd, cwd=settings.repo, stdout=f, stderr=subprocess.STDOUT, text=True)

        return process.returncode

act = Act()

from pipelinespec.models import Context, Job
from singleton_decorator import singleton
from tempfile import NamedTemporaryFile
from pipelinespec import settings
from pathlib import Path
import subprocess
import json
import os

TOOLCACHE_VOLUME = 'act-toolcache'
TOOLCACHE_PATH = '/opt/hostedtoolcache'
CERT_PATH = f'{TOOLCACHE_PATH}/pspec/ca.pem'
LOCAL_HOSTS = 'localhost,127.0.0.1,::1'

@singleton
class Act:

    def run(self, job: Job, run_dir: Path, proxy_port: int, context: Context, credentials: dict[str, str], run: str) -> int:

        self.__install_certificate()

        proxy_url = f'http://host.docker.internal:{proxy_port}'

        env = {
            'HTTP_PROXY': proxy_url,
            'HTTPS_PROXY': proxy_url,
            'http_proxy': proxy_url,
            'https_proxy': proxy_url,
            'NO_PROXY': LOCAL_HOSTS,
            'no_proxy': LOCAL_HOSTS,
            'NODE_USE_ENV_PROXY': '1',
            'SSL_CERT_FILE': CERT_PATH,
            'NODE_EXTRA_CA_CERTS': CERT_PATH,
            'REQUESTS_CA_BUNDLE': CERT_PATH,
            'CURL_CA_BUNDLE': CERT_PATH,
            'GIT_SSL_CAINFO': CERT_PATH,
            'PSPEC_RUN': run,
        }

        cmd = [
            'act',
            context.event,
            '-P', settings.trace.container,
            '--container-daemon-socket', '-',
            '--container-architecture', settings.trace.arch,
            '--pull=false',
            '--no-cache-server',
            '--json',
            '--verbose',
            '--container-options', '--add-host host.docker.internal:host-gateway',
            '-W', str(job.path.resolve()),
            '-j', job.name,
            '--secret-file', os.devnull,
            '--env-file', os.devnull,
        ]

        cmd += ['--action-offline-mode'] if 'GITHUB_TOKEN' in credentials else ['--secret', 'GITHUB_TOKEN=']

        if context.actor is not None:
            cmd += ['--actor', context.actor]

        for name, value in credentials.items():
            cmd += ['--secret', f'{name}={value}']

        for name, value in env.items():
            cmd += ['--env', f'{name}={value}']

        with open(run_dir / 'run.jsonl', 'w') as f, NamedTemporaryFile('w', suffix='.json') as event:
            json.dump(context.event_file, event)
            event.flush()
            process = subprocess.run([*cmd, '-e', event.name], cwd=settings.repo, stdout=f, stderr=subprocess.STDOUT, text=True)

        return process.returncode

    def __install_certificate(self) -> None:

        source = settings.trace.mitm_certificate.resolve() / 'mitmproxy-ca-cert.pem'
        cmd = [
            'docker', 'run', '--rm',
            '-v', f'{TOOLCACHE_VOLUME}:{TOOLCACHE_PATH}',
            '-v', f'{source}:/ca.pem:ro',
            '--entrypoint', 'install',
            settings.trace.sidecar_image,
            '-D', '-m', '644', '/ca.pem', CERT_PATH,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f'Could not install the mitmproxy CA in the {TOOLCACHE_VOLUME} volume: {result.stderr.strip()}')

act = Act()

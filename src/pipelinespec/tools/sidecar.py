from singleton_decorator import singleton
from contextlib import contextmanager
from collections.abc import Generator
from pipelinespec import settings
from pathlib import Path
import subprocess
import time
import uuid
import re

STARTUP_TIMEOUT = 90
FLUSH_SECONDS = 1
STOP_TIMEOUT = 20
PROXY_PORT = 8080
LOST_EVENTS = re.compile(r'Lost (\d+) events')
PUBLISHED_PORT = re.compile(r':(\d+)$', re.MULTILINE)
TRACE = 'ebpf.txt'
TRAFFIC = 'traffic.jsonl'
CONTAINER_RUN_DIR = '/pspec/run'
PLATFORMS = {'aarch64': 'linux/arm64', 'arm64': 'linux/arm64', 'x86_64': 'linux/amd64', 'amd64': 'linux/amd64'}

@singleton
class Sidecar:

    @contextmanager
    def session(self, run_dir: Path) -> Generator[int]:

        architecture, system = self.__docker('info', '--format', '{{.Architecture}}|{{.OperatingSystem}}').strip().split('|', 1)
        native = PLATFORMS.get(architecture)

        if settings.trace.arch != native:
            raise RuntimeError(f'The jobs would run as {settings.trace.arch} on a {architecture} Docker host. Emulated jobs are not supported by the eBPF tracer; use -a {native}.')

        if subprocess.run(['docker', 'image', 'inspect', settings.trace.sidecar_image], capture_output=True).returncode != 0:
            raise RuntimeError(f'The sidecar image {settings.trace.sidecar_image} is missing. Build it with: docker build -t {settings.trace.sidecar_image} src/pipelinespec/docker')

        run_dir = run_dir.resolve()
        (run_dir / TRACE).unlink(missing_ok=True)

        name = f'pspec-trace-{uuid.uuid4().hex[:8]}'

        try:
            self.__docker('create', '--name', name, '--privileged', '--pid=host', '-p', f'{self.__address(system)}::{PROXY_PORT}', '-e', f'RUN_DIR={CONTAINER_RUN_DIR}', '-e', f'BODY_LIMIT={settings.trace.body_limit}', settings.trace.sidecar_image)
            self.__docker('cp', str(settings.trace.mitm_certificate.resolve() / 'mitmproxy-ca.pem'), f'{name}:/pspec/mitm/mitmproxy-ca.pem')

            for file in ('mocked_calls.json', 'secrets.json'):
                self.__docker('cp', str(run_dir / file), f'{name}:{CONTAINER_RUN_DIR}/{file}')

            self.__docker('start', name)
            self.__wait(name)

            yield self.__port(name)

            time.sleep(FLUSH_SECONDS)
        finally:
            output = self.__stop(name, run_dir)

        self.__check(run_dir, output)

    def __address(self, system: str) -> str:

        if 'Docker Desktop' in system:
            return '127.0.0.1'

        return self.__docker('network', 'inspect', 'bridge', '--format', '{{(index .IPAM.Config 0).Gateway}}').strip()

    def __port(self, name: str) -> int:

        return int(PUBLISHED_PORT.search(self.__docker('port', name, str(PROXY_PORT)))[1])

    def __docker(self, *args: str) -> str:

        result = subprocess.run(['docker', *args], capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f'docker {args[0]} failed: {result.stderr.strip()}')

        return result.stdout

    def __wait(self, name: str) -> None:

        deadline = time.time() + STARTUP_TIMEOUT

        while time.time() < deadline:
            running = subprocess.run(['docker', 'inspect', '-f', '{{.State.Running}}', name], capture_output=True, text=True).stdout.strip()
            logs = self.__logs(name)

            if running != 'true':
                raise RuntimeError(f'{name} exited during startup: {logs}')

            if 'ERROR' in logs:
                raise RuntimeError(f'The sidecar failed to start: {logs}')

            if 'Attached' in logs and 'Proxy ready' in logs:
                return

            time.sleep(0.5)

        raise TimeoutError(f'The sidecar did not start in time: {self.__logs(name)}')

    def __stop(self, name: str, run_dir: Path) -> str:

        subprocess.run(['docker', 'stop', '-t', str(STOP_TIMEOUT), name], capture_output=True)
        subprocess.run(['docker', 'cp', f'{name}:/tmp/{TRACE}', str(run_dir / TRACE)], capture_output=True)
        subprocess.run(['docker', 'cp', f'{name}:{CONTAINER_RUN_DIR}/{TRAFFIC}', str(run_dir / TRAFFIC)], capture_output=True)

        logs = self.__logs(name)
        subprocess.run(['docker', 'rm', '-f', name], capture_output=True)

        return logs

    def __check(self, run_dir: Path, output: str) -> None:

        lost = sum(int(count) for count in LOST_EVENTS.findall(output))

        if lost:
            raise RuntimeError(f'The eBPF tracer lost {lost} events; the trace is incomplete.')

        if 'ERROR' in output:
            raise RuntimeError(f'The sidecar reported errors: {output}')

        if not (run_dir / TRACE).exists():
            raise RuntimeError(f'The sidecar did not produce {TRACE}; the trace is incomplete.')

    def __logs(self, name: str) -> str:

        result = subprocess.run(['docker', 'logs', name], capture_output=True, text=True, errors='replace')

        return result.stdout + result.stderr

sidecar = Sidecar()

from singleton_decorator import singleton
from contextlib import contextmanager
from collections.abc import Generator
from pipelinespec import settings
from pathlib import Path
import subprocess
import socket
import time
import sys
import os

STARTUP_TIMEOUT = 15

@singleton
class Mitm:

    @contextmanager
    def proxy(self, run_dir: Path) -> Generator[int]:

        with socket.socket() as s:
            s.bind(('', 0))
            port = s.getsockname()[1]

        cmd = [
            str(Path(sys.executable).parent / 'mitmdump'),
            '--listen-port', str(port),
            '--set', f'confdir={settings.trace.mitm_certificate}',
            '--set', 'connection_strategy=lazy',
            '-q',
            '-s', str(settings.trace.addon),
        ]

        process = subprocess.Popen(cmd, env={**os.environ, 'RUN_DIR': str(run_dir.resolve())})

        try:
            self.__wait(port, process)
            yield port
        finally:
            process.terminate()
            process.wait()

    def __wait(self, port: int, process: subprocess.Popen) -> None:

        deadline = time.time() + STARTUP_TIMEOUT

        while time.time() < deadline:
            if process.poll() is not None:
                raise RuntimeError('mitmdump exited during startup.')

            try:
                socket.create_connection(('127.0.0.1', port), timeout=0.5).close()
                return
            except OSError:
                time.sleep(0.2)

        raise TimeoutError('mitmdump did not start in time.')

mitm = Mitm()

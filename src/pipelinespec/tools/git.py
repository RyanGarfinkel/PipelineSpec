from singleton_decorator import singleton
from pipelinespec import settings
import subprocess
import re

@singleton
class Git:

    def head(self) -> str | None:

        process = subprocess.run(['git', '-C', str(settings.repo), 'rev-parse', 'HEAD'], capture_output=True, text=True)

        return process.stdout.strip() if process.returncode == 0 else None

    def repository(self) -> str | None:

        process = subprocess.run(['git', '-C', str(settings.repo), 'remote', 'get-url', 'origin'], capture_output=True, text=True)
        match = re.search(r'[:/]([^/:]+/[^/]+?)(?:\.git)?/?$', process.stdout.strip()) if process.returncode == 0 else None

        return match.group(1) if match else None

git = Git()

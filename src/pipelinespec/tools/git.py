from singleton_decorator import singleton
from pipelinespec import settings
from pathlib import Path
import subprocess
import os
import re

@singleton
class Git:

    def clone(self, url: str, destination: Path) -> None:

        self.__run(['clone', '--depth', '1', '--quiet', url, str(destination)])

    def checkout(self, url: str, commit: str, destination: Path) -> None:

        destination.mkdir(parents=True, exist_ok=True)
        repo = ['-C', str(destination)]

        self.__run([*repo, 'init', '--quiet'])
        self.__run([*repo, 'remote', 'add', 'origin', url])
        self.__run([*repo, 'fetch', '--depth', '1', '--quiet', 'origin', commit])
        self.__run([*repo, 'checkout', '--quiet', 'FETCH_HEAD'])

    def head(self, repo: Path | None = None) -> str | None:

        return self.__commit('HEAD', repo)

    def parent(self) -> str | None:

        return self.__commit('HEAD~1')

    def commit_date(self, repo: Path) -> str:

        process = subprocess.run(['git', '-C', str(repo), 'log', '-1', '--format=%cI'], capture_output=True, text=True)

        if process.returncode != 0 or not process.stdout.strip():
            raise RuntimeError(f'git log in {repo} failed: {process.stderr.strip()}')

        return process.stdout.strip()

    def tracked(self, repo: Path) -> list[str]:

        process = subprocess.run(['git', '-C', str(repo), 'ls-files', '-z'], capture_output=True, text=True)

        if process.returncode != 0:
            raise RuntimeError(f'git ls-files in {repo} failed: {process.stderr.strip()}')

        return [path for path in process.stdout.split('\0') if path]

    def __run(self, arguments: list[str]) -> None:

        environment = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GIT_LFS_SKIP_SMUDGE': '1'}
        process = subprocess.run(['git', *arguments], capture_output=True, text=True, env=environment)

        if process.returncode != 0:
            raise RuntimeError(f'git {" ".join(arguments)} failed: {process.stderr.strip()}')

    def __commit(self, revision: str, repo: Path | None = None) -> str | None:

        process = subprocess.run(['git', '-C', str(repo or settings.repo), 'rev-parse', '--verify', '--quiet', f'{revision}^{{commit}}'], capture_output=True, text=True)

        return process.stdout.strip() if process.returncode == 0 else None

    def repository(self) -> str | None:

        process = subprocess.run(['git', '-C', str(settings.repo), 'remote', 'get-url', 'origin'], capture_output=True, text=True)
        match = re.search(r'[:/]([^/:]+/[^/]+?)(?:\.git)?/?$', process.stdout.strip()) if process.returncode == 0 else None

        return match.group(1) if match else None

git = Git()

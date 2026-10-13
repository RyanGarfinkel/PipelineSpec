from pipelinespec.models import FileAccess
from singleton_decorator import singleton
from pathlib import Path
import re

LINE = re.compile(r'^(?P<call>\w+)\((?P<args>.*)\)\s+=\s+(?P<ret>-?\d+)')
PATHS = re.compile(r'"((?:[^"\\]|\\.)*)"')
WRITE_FLAGS = ('O_WRONLY', 'O_RDWR', 'O_CREAT', 'O_TRUNC', 'O_APPEND')
OPENS = {'open', 'openat', 'openat2'}
EXECS = {'execve', 'execveat'}
IGNORED = ('/trace', '/pspec')

@singleton
class Strace:

    def parse(self, trace_dir: Path) -> list[FileAccess]:

        accesses: dict[str, set[str]] = {}

        for raw in trace_dir.glob('strace.*'):
            with open(raw, 'r', errors='replace') as f:
                for line in f:
                    parsed = self.__access(line)
                    if parsed is None:
                        continue

                    path, kind = parsed
                    if not path.startswith(IGNORED):
                        accesses.setdefault(path, set()).add(kind)

        return [FileAccess(path=path, access=frozenset(kinds)) for path, kinds in sorted(accesses.items())]

    def find(self, trace_dir: Path, values: dict[str, str]) -> frozenset[str]:

        found: set[str] = set()

        for raw in trace_dir.glob('strace.*'):
            text = raw.read_text(errors='replace')
            found.update(name for name, value in values.items() if value in text)

        return frozenset(found)

    def __access(self, line: str) -> tuple[str, str] | None:

        match = LINE.match(line)
        if match is None or int(match['ret']) < 0:
            return None

        call, args = match['call'], match['args']
        paths = PATHS.findall(args)
        if not paths:
            return None

        if call in EXECS:
            return paths[0], 'execute'

        if call in OPENS:
            return paths[0], 'write' if any(flag in args for flag in WRITE_FLAGS) else 'read'
        
        return paths[-1] if call.startswith('rename') else paths[0], 'write'

strace = Strace()

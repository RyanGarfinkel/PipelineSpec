from singleton_decorator import singleton
from pathlib import Path

@singleton
class Envtrace:

    def parse(self, trace_dir: Path) -> frozenset[str]:

        names: set[str] = set()

        for raw in trace_dir.glob('env.*'):
            with open(raw, 'r', errors='replace') as f:
                names.update(line.strip() for line in f if line.strip())

        return frozenset(names)

envtrace = Envtrace()

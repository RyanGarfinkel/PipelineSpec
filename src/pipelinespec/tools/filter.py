from pipelinespec.models import FileAccess, JobRun, NetworkAccess, TraceResult, Version
from pipelinespec.utils import UNATTRIBUTED, relative
from singleton_decorator import singleton
from pipelinespec import settings
from .runlog import runlog
from collections import Counter
from pathlib import Path
import logging as log
import json

Key = tuple[str, str]
Versions = dict[Key, list[Version]]

@singleton
class TraceFilter:

    def clean(self, result: TraceResult, target: Key, versions: Versions) -> TraceResult:

        run_dir = settings.file.output / 'runs' / str(result.id)
        others = {key: run for key, run in runlog.parse(run_dir / 'run.jsonl').items() if key != target}

        if not others:
            return result

        files, requests = self.__files(run_dir), self.__requests(run_dir)
        file_counts = Counter(key for lines in files.values() for key in lines.elements())
        request_counts = Counter(self.__request(line) for lines in requests.values() for line in lines)

        for key, run in others.items():
            source = self.__source(key, run, target, versions, run_dir)
            file_counts.subtract(self.__files(source).get(key, Counter()))
            request_counts.subtract(self.__request(line) for line in self.__requests(source).get(key, []))

        accesses = [FileAccess(path=path, access=frozenset({kind})) for (path, kind), count in file_counts.items() if count > 0]
        access = result.access.model_copy(update={'files': FileAccess.combine(accesses), 'networks': self.__networks(requests, request_counts, target)})
        subtracted = result.model_copy(update={'access': access})

        (run_dir / 'result.json').write_text(subtracted.model_dump_json(indent=4))

        return subtracted

    def __source(self, key: Key, run: JobRun, target: Key, versions: Versions, run_dir: Path) -> Path:

        steps = [(step.id, step.outcome) for step in run.steps]
        known = versions.get(key, [])
        version = next((version for version in known if version.steps == steps), None) or next((version for version in known if version.outcome == run.outcome), None)

        if version is None:
            if run.steps:
                log.warning(f'{target[0]} / {target[1]}: no traced version of {key[0]} / {key[1]} matches this run, so its counts come from this run.')

            return run_dir

        return settings.file.output / 'runs' / str(version.run)

    def __files(self, run_dir: Path) -> dict[Key, Counter]:

        root, found = str(settings.repo), {}

        with open(run_dir / 'files.jsonl', errors='replace') as lines:
            for line in lines:
                event = json.loads(line)
                path = relative(event['path'], root)

                if event['job'] != UNATTRIBUTED and not path.startswith('/'):
                    found.setdefault((event['workflow'], event['job']), Counter())[path, event['kind']] += 1

        return found

    def __requests(self, run_dir: Path) -> dict[Key, list[dict]]:

        found = {}

        with open(run_dir / 'traffic.jsonl', errors='replace') as lines:
            for line in lines:
                entry = json.loads(line)

                if entry['job'] != UNATTRIBUTED:
                    found.setdefault((entry['workflow'], entry['job']), []).append(entry)

        return found

    def __request(self, entry: dict) -> tuple[str, str, str]:

        return entry['method'], entry['host'], entry['path']

    def __networks(self, requests: dict[Key, list[dict]], counts: Counter, target: Key) -> frozenset[NetworkAccess]:

        ordered = [*requests.get(target, []), *(line for key, lines in requests.items() if key != target for line in lines)]
        networks = []

        for line in ordered:
            key = self.__request(line)

            if counts[key] > 0:
                counts[key] -= 1
                networks.append(NetworkAccess.model_validate(line))

        return frozenset(networks)

trace_filter = TraceFilter()

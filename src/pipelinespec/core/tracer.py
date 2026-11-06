from pipelinespec.models import Access, FileAccess, JobRun, MockedCall, Mocks, NetworkAccess, SocketEvent, Trace, TraceResult, Variant, Workflow
from pipelinespec.utils import UNATTRIBUTED, relative, slug
from pipelinespec.tools import act, events, runlog, sidecar
from dataclasses import dataclass, field
from singleton_decorator import singleton
from collections import defaultdict
from pipelinespec import settings
from pydantic import BaseModel
from pathlib import Path
from uuid import uuid4
import logging as log
import json

Key = tuple[str, str]
GLOBAL: Key = (UNATTRIBUTED, UNATTRIBUTED)
SOCKET_WINDOW = 2.0
AMBIGUITY_WINDOW = 0.25

@dataclass
class Bucket:

    files: list[FileAccess] = field(default_factory=list)
    networks: list[NetworkAccess] = field(default_factory=list)
    connections: set[str] = field(default_factory=set)
    markers: set[str] = field(default_factory=set)
    commands: list[tuple[str, ...]] = field(default_factory=list)

@singleton
class Tracer:

    def run(self, workflow: Workflow, variant: Variant, mocks: Mocks) -> TraceResult:

        if not variant.workflow or not variant.job or variant.context is None:
            raise ValueError(f'The variant "{variant.reason}" is not bound to a job and a context.')

        job = next((job for job in workflow.jobs if job.name == variant.job), None)

        if workflow.name != variant.workflow or job is None:
            raise ValueError(f'The variant "{variant.reason}" names job "{variant.job}" of workflow "{variant.workflow}", which is not in workflow "{workflow.name}".')

        target = (slug(variant.workflow), variant.job)

        secret_values = {name: f'pspec-{uuid4()}' for name in sorted({*(set(job.secret_names) - {'GITHUB_TOKEN'}), *mocks.credentials})}

        run_id = uuid4()
        run_dir = settings.file.output / 'runs' / str(run_id)
        run_dir.mkdir(parents=True)

        traffic_file = run_dir / 'traffic.jsonl'
        traffic_file.touch()

        with open(run_dir / 'mocked_calls.json', 'w') as f:
            json.dump([call.model_dump() for call in mocks.calls], f, indent=4)

        with open(run_dir / 'secrets.json', 'w') as f:
            json.dump(secret_values, f, indent=4)

        with open(run_dir / 'config.json', 'w') as f:
            json.dump({**variant.model_dump(mode='json'), 'mocks': mocks.model_dump(mode='json')}, f, indent=4)

        with sidecar.session(run_dir) as port:
            act.run(job, run_dir, port, variant.context, secret_values, str(run_id))

        parsed = events.parse(run_dir, str(settings.repo), secret_values, str(run_id))

        log.debug(f'{variant.job} finished running. Saving data to {run_dir}...')

        self.__write_lines(run_dir / 'files.jsonl', parsed.files)
        self.__write_lines(run_dir / 'sockets.jsonl', parsed.sockets)

        runs = runlog.parse(run_dir / 'run.jsonl')
        root = str(settings.repo)
        buckets: dict[Key, Bucket] = defaultdict(Bucket)

        for event in parsed.files:
            bucket = buckets[self.__bucket((event.workflow, event.job), runs)]
            path = relative(event.path, root)

            if not path.startswith('/'):
                bucket.files.append(FileAccess(path=path, access=frozenset({event.kind})))

            if event.kind == 'execute' and event.argv and event.argv not in bucket.commands:
                bucket.commands.append(event.argv)

        for event in parsed.connections:
            address = f'[{event.address}]' if ':' in event.address else event.address

            if event.port not in (0, port) and not event.address.startswith('127.') and event.address != '::1':
                buckets[self.__bucket((event.workflow, event.job), runs)].connections.add(f'{address}:{event.port}')

        for key, found in parsed.markers.items():
            buckets[self.__bucket(key, runs)].markers.update(found)

        proxied = [event for event in parsed.sockets if event.port == port]
        entries = [json.loads(line) for line in traffic_file.read_text().splitlines()]

        ambiguous = 0
        unowned = 0

        for entry in entries:
            owner, close = self.__owner(proxied, entry['client_time'])
            ambiguous += close
            unowned += owner is None
            entry['workflow'], entry['job'] = (owner.workflow, owner.job) if owner else GLOBAL
            buckets[self.__bucket((entry['workflow'], entry['job']), runs)].networks.append(NetworkAccess.model_validate(entry))

        if entries and unowned == len(entries):
            log.error(f'None of the {len(entries)} proxied requests could be attributed to a job; all network access is unattributed.')
        elif unowned:
            log.warning(f'{unowned} of {len(entries)} proxied requests could not be attributed to a job.')

        if ambiguous:
            log.warning(f'{ambiguous} of {len(entries)} proxied requests have connections from different jobs within {AMBIGUITY_WINDOW}s; their attribution may be wrong.')

        traffic_file.write_text(''.join(json.dumps(entry) + '\n' for entry in entries))

        results = {key: self.__result(run_id, workflow, target, run, buckets) for key, run in runs.items()}
        result = results.get(target) or TraceResult(id=run_id, path=workflow.path, job=variant.job, outcome='unknown', unattributed=self.__access([], buckets[GLOBAL]))

        (run_dir / 'jobs').mkdir()

        for key, other in results.items():
            if key != target:
                (run_dir / 'jobs' / f'{key[0]}.{key[1]}.json').write_text(other.model_dump_json())

        with open(run_dir / 'result.json', 'w') as f:
            f.write(result.model_dump_json(indent=4))

        return result

    def __result(self, run_id, workflow: Workflow, target: tuple[str, str], run: JobRun, buckets: dict[Key, Bucket]) -> TraceResult:

        key = (run.workflow, run.job)
        job = next((job for job in workflow.jobs if job.name == run.job), None) if run.workflow == target[0] else None
        bucket = buckets[key]
        unattributed = self.__access([], buckets[GLOBAL]) if key == target else Access()

        return TraceResult(
            id=run_id,
            path=workflow.path,
            job=run.job,
            outcome=run.outcome,
            steps=run.steps,
            access=self.__access(job.secret_names if job else [], bucket),
            commands=tuple(bucket.commands),
            unattributed=unattributed,
        )

    def __access(self, named: list[str], bucket: Bucket) -> Access:

        used = frozenset(secret for network in bucket.networks for secret in network.secrets) | frozenset(bucket.markers)

        return Access(
            files=FileAccess.combine(bucket.files),
            networks=frozenset(bucket.networks),
            connections=frozenset(bucket.connections),
            secrets=used,
            referenced=frozenset(named) - used,
        )

    def __bucket(self, key: Key, runs: dict[tuple[str, str], JobRun]) -> Key:

        return key if key in runs else GLOBAL

    def __owner(self, candidates: list[SocketEvent], time: float | None) -> tuple[SocketEvent | None, bool]:

        if time is None or not candidates:
            return None, False

        ranked = sorted(candidates, key=lambda event: abs(event.time - time))
        nearest = ranked[0]

        if abs(nearest.time - time) > SOCKET_WINDOW:
            return None, False

        owner = (nearest.workflow, nearest.job)
        rival = next((event for event in ranked[1:] if (event.workflow, event.job) != owner), None)

        return nearest, rival is not None and abs(rival.time - time) <= AMBIGUITY_WINDOW

    def __write_lines(self, path: Path, models: list[BaseModel]) -> None:

        with open(path, 'w') as f:
            for model in models:
                f.write(model.model_dump_json() + '\n')

tracer = Tracer()

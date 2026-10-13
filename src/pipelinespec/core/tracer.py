from pipelinespec.models import Job, NetworkAccess, TraceConfig, TraceResult, Workflow
from pipelinespec.tools import act, envtrace, mitm, strace
from singleton_decorator import singleton
from pipelinespec import settings
from pathlib import Path
from uuid import uuid4
import logging as log
import tempfile
import json

@singleton
class Tracer:

    def run(self, config: TraceConfig) -> TraceResult:

        job = self.__find_job(config)

        secret_values = self.__entries(settings.file.secrets)

        run_id = uuid4()
        run_dir = settings.file.output / 'runs' / str(run_id)
        run_dir.mkdir(parents=True)

        traffic_file = run_dir / 'traffic.jsonl'
        traffic_file.touch()

        with open(run_dir / 'mocked_calls.json', 'w') as f:
            json.dump([call.model_dump() for call in config.mocked_calls], f, indent=4)

        with open(run_dir / 'secrets.json', 'w') as f:
            json.dump(secret_values, f, indent=4)

        log.info(f'About to run {job.name} from {config.workflow}...')

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as trace_dir, mitm.proxy(run_dir) as port:
            act.run(job, run_dir, port, Path(trace_dir))
            files = strace.parse(Path(trace_dir))
            names_read = envtrace.parse(Path(trace_dir))
            executed_secrets = strace.find(Path(trace_dir), secret_values)

        log.info(f'{job.name} finished running. Saving data to {run_dir}...')

        with open(run_dir / 'files.jsonl', 'w') as f:
            for file in files:
                f.write(file.model_dump_json() + '\n')

        networks = [NetworkAccess.model_validate_json(line) for line in traffic_file.read_text().splitlines()]

        env = names_read & (self.__names(settings.file.env) | frozenset(job.env))
        sent_secrets = frozenset(secret for network in networks for secret in network.secrets)
        mapped_secrets = frozenset(secret for name in names_read for secret in job.secrets.get(name, []))
        secrets = (names_read & frozenset(secret_values)) | mapped_secrets | sent_secrets | executed_secrets

        result = TraceResult(id=run_id, path=job.path, job=job.name, files=frozenset(files), networks=frozenset(networks), env=env, secrets=secrets)

        with open(run_dir / 'result.json', 'w') as f:
            f.write(result.model_dump_json(indent=4))

        return result

    def __entries(self, path: Path) -> dict[str, str]:

        lines = [line.strip() for line in path.read_text().splitlines()]
        pairs = [line.partition('=') for line in lines if line and not line.startswith('#')]

        return {name: value.strip('"\'') for name, _, value in pairs}

    def __names(self, path: Path) -> frozenset[str]:

        return frozenset(self.__entries(path))

    def __find_job(self, config: TraceConfig) -> Job:

        workflows_dir = settings.repo / '.github' / 'workflows'
        paths = [*workflows_dir.glob('*.yml'), *workflows_dir.glob('*.yaml')]

        for workflow in map(Workflow.parse, paths):
            if workflow.name != config.workflow:
                continue

            for job in workflow.jobs:
                if job.name == config.job:
                    return job

        raise ValueError(f'Job "{config.job}" not found in workflow "{config.workflow}".')

tracer = Tracer()

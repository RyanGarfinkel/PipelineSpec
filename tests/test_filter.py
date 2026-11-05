from pipelinespec.models import TraceResult, Version, Access, NetworkAccess
from pipelinespec.tools import trace_filter
from pipelinespec import settings
from pathlib import Path
from uuid import uuid4
import json

def request(job, path, status=200):

    return {'scheme': 'https', 'host': 'a.example', 'port': 443, 'method': 'GET', 'path': path, 'headers': [], 'secrets': [], 'status': status, 'result': 'passed', 'workflow': 'W', 'job': job}

def write_run(output, jobs, files, traffic):

    run = uuid4()
    run_dir = output / 'runs' / str(run)
    run_dir.mkdir(parents=True)
    log = [{'job': f'W/{job}', 'jobID': job, 'stepID': ['0'], 'stage': 'Main', 'step': 's', 'stepResult': outcome, 'msg': ''} for job, outcome in jobs.items()]
    (run_dir / 'run.jsonl').write_text('\n'.join(json.dumps(line) for line in log))
    (run_dir / 'files.jsonl').write_text(''.join(json.dumps({'workflow': 'W', 'job': job, 'path': path, 'kind': kind}) + '\n' for job, path, kind in files))
    (run_dir / 'traffic.jsonl').write_text(''.join(json.dumps(line) + '\n' for line in traffic))

    return run

def setup(tmp_path, monkeypatch):

    monkeypatch.setattr(settings.file, 'output', tmp_path)
    monkeypatch.setattr(settings, 'repo', Path('/repo'))

def test_subtracts_the_matching_version_of_other_jobs(tmp_path, monkeypatch):

    setup(tmp_path, monkeypatch)
    failed = write_run(tmp_path, {'up': 'failure'}, [('up', 'wrong.txt', 'read')], [])
    match = write_run(tmp_path, {'up': 'success'}, [('up', 'shared.txt', 'read'), ('up', 'up.txt', 'read')], [request('up', '/shared')])
    run = write_run(
        tmp_path,
        {'up': 'success', 'down': 'success'},
        [('up', 'shared.txt', 'read'), ('up', 'up.txt', 'read'), ('down', 'shared.txt', 'read'), ('down', 'down.txt', 'write'), ('down', '/etc/hosts', 'read'), ('_', 'setup.txt', 'read')],
        [request('up', '/shared'), request('down', '/shared'), request('down', '/down')],
    )
    versions = {('W', 'up'): [Version(run=failed, outcome='failure', steps=[('0', 'failure')]), Version(run=match, outcome='success', steps=[('0', 'success')])]}

    result = trace_filter.clean(TraceResult(id=run, path=Path('w.yml'), job='down', outcome='success'), ('W', 'down'), versions)

    assert {item.path: set(item.access) for item in result.access.files} == {'shared.txt': {'read'}, 'down.txt': {'write'}}
    assert sorted(network.path for network in result.access.networks) == ['/down', '/shared']
    assert TraceResult.model_validate_json((tmp_path / 'runs' / str(run) / 'result.json').read_text()).access == result.access

def test_a_job_alone_in_its_run_is_unchanged(tmp_path, monkeypatch):

    setup(tmp_path, monkeypatch)
    run = write_run(tmp_path, {'down': 'success'}, [('down', 'a.txt', 'read')], [])
    result = TraceResult(id=run, path=Path('w.yml'), job='down', outcome='success', access=Access(networks=frozenset({NetworkAccess.model_validate(request('down', '/kept'))})))

    assert trace_filter.clean(result, ('W', 'down'), {}) is result

def test_an_untraced_job_falls_back_to_its_lines_in_this_run(tmp_path, monkeypatch):

    setup(tmp_path, monkeypatch)
    run = write_run(tmp_path, {'up': 'success', 'down': 'success'}, [('up', 'up.txt', 'read'), ('down', 'down.txt', 'read')], [])

    result = trace_filter.clean(TraceResult(id=run, path=Path('w.yml'), job='down', outcome='success'), ('W', 'down'), {})

    assert {item.path for item in result.access.files} == {'down.txt'}

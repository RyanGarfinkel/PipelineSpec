from pipelinespec.models import Context, Diagnosis, FileAccess, Job, JobConstraints, MockedCall, Mocks, StepResult, TraceResult, Variant, Workflow, WorkflowTrigger
from pipelinespec.models import Access
from pipelinespec import settings
from importlib import import_module
from pathlib import Path
from uuid import uuid4
import pytest
import json

class NoFilter:

    def clean(self, result, _, __):

        return result

def access(*paths, kind='read'):

    return Access(files=frozenset(FileAccess(path=path, access=frozenset({kind})) for path in paths))

def paths(found):

    return {item.path: set(item.access) for item in found.files}

def test_volatile_paths_are_left_out():

    first = access('package-lock.json', 'tmp/a1', 'tmp/keep', 'stray.log')
    second = access('package-lock.json', 'tmp/b2', 'tmp/keep', kind='write')

    assert paths(first.without_volatile(second)) == {
        'package-lock.json': {'read', 'write'},
        'tmp/keep': {'read', 'write'},
    }

def test_identical_runs_are_kept_and_the_rest_merged():

    first = access('a/b').model_copy(update={'secrets': frozenset({'ONE'})})
    second = access('a/b').model_copy(update={'secrets': frozenset({'TWO'})})
    merged = first.without_volatile(second)

    assert paths(merged) == {'a/b': {'read'}}
    assert merged.secrets == {'ONE', 'TWO'}

def test_a_secret_used_in_either_run_is_not_only_referenced():

    first = Access(secrets=frozenset({'USED'}), referenced=frozenset({'NAMED'}))
    second = Access(referenced=frozenset({'USED', 'NAMED'}))
    merged = first.merge(second)

    assert merged.secrets == {'USED'} and merged.referenced == {'NAMED'}

def traces(module, variants):

    return module.runner.get_traces([workflow_of(found.job, uses=found.uses) for found in variants], variants)

def run(monkeypatch, tmp_path, outcomes):

    module = import_module('pipelinespec.core.runner')
    results = [TraceResult(id=uuid4(), path=Path('ci.yml'), job='job', outcome=outcome, access=access(f'dir/{index}')) for index, outcome in enumerate(outcomes)]
    calls = []

    class Tracer:

        def run(self, _, variant, mocks):

            calls.append((variant, mocks.model_copy(deep=True)))

            return results[len(calls) - 1]

    monkeypatch.setattr(module, 'tracer', Tracer())
    monkeypatch.setattr(module, 'trace_filter', NoFilter())
    monkeypatch.setattr(settings.file, 'output', tmp_path)

    [trace] = traces(module, [variant('job')])

    return (trace.trial, trace.result), results, calls

def test_loop_repeats_a_variant_and_leaves_out_volatile_paths(monkeypatch, tmp_path):

    (trial, result), results, calls = run(monkeypatch, tmp_path, ['success', 'success'])

    assert len(calls) == 2 and calls[0] == calls[1]
    assert trial.runs == (results[0].id, results[1].id)
    assert paths(result.access) == {}

    for found in results:
        assert TraceResult.model_validate_json((tmp_path / 'runs' / str(found.id) / 'result.json').read_text()).files == frozenset()

def test_loop_keeps_the_first_run_when_outcomes_differ(monkeypatch, tmp_path):

    (_, result), results, _ = run(monkeypatch, tmp_path, ['success', 'failure'])

    assert result == results[0]

def step(outcome):

    return StepResult(id='0', name='s', outcome=outcome)

def repairing(monkeypatch, tmp_path, results, diagnose):

    module = import_module('pipelinespec.core.runner')
    calls = []

    class Tracer:

        def run(self, _, variant, mocks):

            calls.append((variant, mocks.model_copy(deep=True)))

            return TraceResult(id=uuid4(), path=Path('ci.yml'), job=variant.job, outcome=results[len(calls) - 1][0], steps=tuple(step(outcome) for outcome in results[len(calls) - 1][1]))

    class Diagnoser:

        def run(self, _, mocks):

            return diagnose(mocks)

    monkeypatch.setattr(module, 'tracer', Tracer())
    monkeypatch.setattr(module, 'trace_filter', NoFilter())
    monkeypatch.setattr(module, 'diagnoser', Diagnoser())
    monkeypatch.setattr(settings.file, 'output', tmp_path)

    return module, calls

def workflow_of(job, needs=(), uses=None):

    return Workflow(name='CI', path=Path('ci.yml'), jobs=[*(Job(name=need, path=Path('ci.yml'), needs=[], steps=[]) for need in needs), Job(name=job, path=Path('ci.yml'), needs=list(needs), steps=[], uses=uses)])

def variant(job, uses=None):

    workflow = workflow_of(job, uses=uses)

    return Variant(reason='r', assignment={'event': 'push'}).bound(workflow, workflow.jobs[-1], [WorkflowTrigger(event='push')], JobConstraints())

def test_bound_builds_the_context_and_carries_the_job(monkeypatch):

    triggers = [WorkflowTrigger(event='push', payload={'ref': 'trigger', 'head': {'sha': 'old'}})]
    constraints = JobConstraints(constants={'payload.ref': 'constant', 'payload.head.sha': 'new'})
    workflow = workflow_of('job', needs=('setup',))
    found = Variant(reason='r', assignment={'event': 'push', 'actor': 'octo', 'payload.ref': 'assigned'}).bound(workflow, workflow.jobs[-1], triggers, constraints)

    assert (found.workflow, found.job, found.needs, found.uses, found.call) == ('CI', 'job', ('setup',), None, False)
    assert found.constraints == constraints
    assert found.context == Context(event='push', actor='octo', payload={'ref': 'assigned', 'head': {'sha': 'new'}})
    assert triggers[0].payload['ref'] == 'trigger'
    assert Variant.model_validate_json(found.model_dump_json()) == found

def test_tracing_refuses_a_variant_that_is_not_bound(monkeypatch, tmp_path):

    module, _ = repairing(monkeypatch, tmp_path, [], None)

    with pytest.raises(ValueError, match='not bound'):
        traces(module, [Variant(reason='r', assignment={'event': 'push'})])

def test_tracing_refuses_a_job_missing_from_the_workflows(monkeypatch, tmp_path):

    module, calls = repairing(monkeypatch, tmp_path, [], None)

    with pytest.raises(ValueError, match='not in the repository'):
        module.runner.get_traces([workflow_of('other')], [variant('job')])

    assert calls == []

def test_tracer_refuses_a_variant_that_is_not_bound():

    tracer = import_module('pipelinespec.core.tracer').tracer

    with pytest.raises(ValueError, match='not bound'):
        tracer.run(workflow_of('job'), Variant(reason='r', assignment={'event': 'push'}), Mocks())

def test_tracing_records_a_call_job_without_running_it(monkeypatch, tmp_path):

    module, calls = repairing(monkeypatch, tmp_path, [], None)

    [trace] = traces(module, [variant('checks', uses='./.github/workflows/checks.yml')])

    assert calls == [] and trace.trial.runs == () and trace.result.files == frozenset()
    assert trace.trial.candidate.call

def test_loop_drops_a_repair_that_does_not_get_further(monkeypatch, tmp_path):

    mock = MockedCall(method='GET', url='https://a.example/x')

    def diagnose(mocks):

        fixable = not mocks.calls
        mocks.calls = [mock]

        return Diagnosis(fixable=fixable, reason='r')

    failed = ('failure', ['success', 'failure'])
    module, calls = repairing(monkeypatch, tmp_path, [failed, failed, failed], diagnose)

    [trace] = traces(module, [variant('job')])

    assert trace.trial.mocks == Mocks()
    assert calls[-1][1].calls == []

def test_loop_reuses_mocks_in_later_jobs(monkeypatch, tmp_path):

    mock = MockedCall(method='PUT', url='https://a.example/x')

    def diagnose(mocks):

        mocks.credentials.append('KEY')
        mocks.calls.append(mock)

        return Diagnosis(fixable=True, reason='r')

    done = ('success', ['success'])
    module, calls = repairing(monkeypatch, tmp_path, [('failure', ['failure']), done, done, done, done], diagnose)

    traces(module, [variant('one'), variant('two')])

    assert calls[0][1].credentials == [] and calls[-1][0].job == 'two'
    assert calls[-1][1].credentials == ['KEY'] and calls[-1][1].calls == [mock]

def test_versions_are_saved_only_when_verbose(monkeypatch, tmp_path):

    done = ('success', ['success'])
    module, _ = repairing(monkeypatch, tmp_path, [done, done, done, done], None)

    traces(module, [variant('job')])
    assert not (tmp_path / 'versions.json').exists()

    monkeypatch.setattr(settings, 'verbose', True)
    traces(module, [variant('job')])

    [saved] = json.loads((tmp_path / 'versions.json').read_text())['CI/job']
    assert saved['outcome'] == 'success' and saved['steps'] == [['0', 'success']]

def test_loop_keeps_github_token_out_of_a_jobs_first_run(monkeypatch, tmp_path):

    def diagnose(mocks):

        mocks.credentials.append('GITHUB_TOKEN')

        return Diagnosis(fixable=True, reason='r')

    done = ('success', ['success'])
    failed = ('failure', ['failure'])
    module, calls = repairing(monkeypatch, tmp_path, [failed, done, done, failed, done, done], diagnose)

    traces(module, [variant('one'), variant('two')])

    assert [mocks.credentials for _, mocks in calls] ==[[], ['GITHUB_TOKEN'], ['GITHUB_TOKEN'], [], ['GITHUB_TOKEN'], ['GITHUB_TOKEN']]

def test_loop_does_not_repeat_a_skipped_job(monkeypatch, tmp_path):

    (trial, result), results, calls = run(monkeypatch, tmp_path, ['skipped'])

    assert len(calls) == 1 and trial.runs == (results[0].id,)
    assert result == results[0]

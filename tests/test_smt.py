from pipelinespec.models import Gate, JobConstraints, Term, Variable, WorkflowTrigger
from pipelinespec.tools import smt
from pipelinespec import settings
import pytest

def test_solve(tmp_path, monkeypatch):

    monkeypatch.setattr(settings.file, 'output', tmp_path)

    job = Gate(name='job.if', type='scope', location='ci.yml:12', any_of=[[Term(name='label', op='==', value='deploy')]])
    step = Gate(name='step.if', type='scope', location='ci.yml:35', any_of=[[Term(name='inputs.dry_run', op='==', value=False), Term(name='event', op='==', value='issues')]])
    variables = {
        'label': Variable(target='payload.label.name', values=('deploy', 'docs')),
        'dry_run': Variable(target='payload.inputs.dry_run', values=(False, True)),
    }
    candidates = smt.solve(JobConstraints(gates=[job, step], variables=variables), [WorkflowTrigger(event='issues'), WorkflowTrigger(event='workflow_dispatch')])
    baseline = candidates[0]

    assert baseline.reason == 'issues: all conditions hold'
    assert baseline.assignment == {'event': 'issues', 'payload.label.name': 'deploy', 'payload.inputs.dry_run': False}
    assert any(candidate.reason == 'issues: job.if fails' and candidate.assignment == {**baseline.assignment, 'payload.label.name': 'docs'} for candidate in candidates)
    assert any(candidate.reason == 'issues: step.if fails' and candidate.assignment['payload.inputs.dry_run'] for candidate in candidates)
    assert all(candidate.assignment['event'] == candidate.reason.split(':')[0] for candidate in candidates)
    assert any(candidate.reason == 'workflow_dispatch: job.if holds' and candidate.assignment['event'] == 'workflow_dispatch' for candidate in candidates)

def test_alternatives_and_text_operators(tmp_path, monkeypatch):

    monkeypatch.setattr(settings.file, 'output', tmp_path)

    tag = Gate(name='tag.if', type='scope', location='ci.yml:5', any_of=[
        [Term(name='ref', op='starts_with', value='refs/tags/v'), Term(name='ref', op='!=', value='refs/tags/v0')],
        [Term(name='ref', op='==', value='refs/heads/release')],
    ])
    variables = {'ref': Variable(target='payload.ref', values=('refs/heads/release', 'refs/tags/v1', 'refs/heads/dev'))}
    candidates = smt.solve(JobConstraints(gates=[tag], variables=variables), [WorkflowTrigger(event='push')])

    assert {candidate.assignment['payload.ref'] for candidate in candidates if candidate.reason in ('push: all conditions hold', 'push: tag.if holds')} <= {'refs/heads/release', 'refs/tags/v1'}
    assert any(candidate.reason == 'push: tag.if fails' and candidate.assignment['payload.ref'] == 'refs/heads/dev' for candidate in candidates)

def test_equivalent():

    keep = Gate(name='a', type='scope', location='x:1', any_of=[[Term(name='n', op='>', value=2)]])
    same = Gate(name='b', type='scope', location='x:1', any_of=[[Term(name='n', op='>=', value=3)]])
    other = Gate(name='c', type='scope', location='x:1', any_of=[[Term(name='n', op='>', value=3)]])
    constraints = JobConstraints(variables={'n': Variable(target='payload.n', values=(1, 5))})

    assert smt.equivalent(constraints, [keep], constraints, [same], ['push'])
    assert not smt.equivalent(constraints, [keep], constraints, [other], ['push'])

def test_solve_needs_an_event():

    with pytest.raises(ValueError, match='no event'):
        smt.solve(JobConstraints(), [])

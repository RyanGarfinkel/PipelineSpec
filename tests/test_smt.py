from pipelinespec.models import Constraints, Gate, Term, Variable
from pipelinespec.tools import smt
from pipelinespec import settings

def test_solve(tmp_path, monkeypatch):

    monkeypatch.setattr(settings.file, 'output', tmp_path)

    job = Gate(name='job.if', type='scope', location='ci.yml:12', any_of=[[Term(name='label', op='==', value='deploy')]])
    step = Gate(name='step.if', type='scope', location='ci.yml:35', any_of=[[Term(name='inputs.dry_run', op='==', value=False), Term(name='event', op='==', value='issues')]])
    variables = {
        'label': Variable(target='payload.label.name', values=('deploy', 'docs')),
        'dry_run': Variable(target='payload.inputs.dry_run', values=(False, True)),
    }
    candidates = smt.solve(Constraints(events=['issues', 'workflow_dispatch'], gates=[job, step], variables=variables))
    baseline = candidates[0]

    assert baseline.reason == 'all conditions hold'
    assert baseline.assignment == {'event': 'issues', 'payload.label.name': 'deploy', 'payload.inputs.dry_run': False}
    assert any(candidate.reason == 'job.if fails' and candidate.assignment == {**baseline.assignment, 'payload.label.name': 'docs'} for candidate in candidates)
    assert any(candidate.reason == 'step.if fails' and (candidate.assignment['event'] == 'workflow_dispatch' or candidate.assignment['payload.inputs.dry_run']) for candidate in candidates)

def test_alternatives_and_text_operators(tmp_path, monkeypatch):

    monkeypatch.setattr(settings.file, 'output', tmp_path)

    tag = Gate(name='tag.if', type='scope', location='ci.yml:5', any_of=[
        [Term(name='ref', op='starts_with', value='refs/tags/v'), Term(name='ref', op='!=', value='refs/tags/v0')],
        [Term(name='ref', op='==', value='refs/heads/release')],
    ])
    variables = {'ref': Variable(target='payload.ref', values=('refs/heads/release', 'refs/tags/v1', 'refs/heads/dev'))}
    candidates = smt.solve(Constraints(events=['push'], gates=[tag], variables=variables))

    assert {candidate.assignment['payload.ref'] for candidate in candidates if candidate.reason in ('all conditions hold', 'tag.if holds')} <= {'refs/heads/release', 'refs/tags/v1'}
    assert any(candidate.reason == 'tag.if fails' and candidate.assignment['payload.ref'] == 'refs/heads/dev' for candidate in candidates)

def test_equivalent():

    keep = Gate(name='a', type='scope', location='x:1', any_of=[[Term(name='n', op='>', value=2)]])
    same = Gate(name='b', type='scope', location='x:1', any_of=[[Term(name='n', op='>=', value=3)]])
    other = Gate(name='c', type='scope', location='x:1', any_of=[[Term(name='n', op='>', value=3)]])
    constraints = Constraints(events=['push'], variables={'n': Variable(target='payload.n', values=(1, 5))})

    assert smt.equivalent(constraints, [keep], constraints, [same])
    assert not smt.equivalent(constraints, [keep], constraints, [other])

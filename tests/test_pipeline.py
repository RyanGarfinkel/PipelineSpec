from pipelinespec.models import AccessMap, JobConstraints, TraceResult, Variant, Workflow, WorkflowTrigger
from pipelinespec.core import access_map, runner
from pipelinespec.cli.main import main
from click.testing import CliRunner
from pipelinespec import settings
from pathlib import Path
from uuid import uuid4
import importlib
import pytest
import json

CI = '''
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo build
  shared:
    uses: ./.github/workflows/shared.yml
'''

SHARED = '''
name: Shared
on: workflow_call
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - run: echo lint
'''

class NoFilter:

    def clean(self, result, _, __):

        return result

class FakeAgent:

    def __init__(self):

        self.calls = []
        self.samples = []

    def find_workflow_triggers(self, workflow, sample=None):

        self.calls.append(workflow.name)
        self.samples.append(sample)

        return [WorkflowTrigger(event='workflow_call' if workflow.name == 'Shared' else 'push')]

    def find_job_constraints(self, workflow, job, sample=None):

        self.calls.append((workflow.name, job.name))

        return JobConstraints()

def repository(tmp_path):

    workflows = tmp_path / 'repo' / '.github' / 'workflows'
    workflows.mkdir(parents=True)
    (workflows / 'ci.yml').write_text(CI)
    (workflows / 'shared.yml').write_text(SHARED)

    return tmp_path / 'repo'

def test_constraints_only_runs_every_workflow_then_its_jobs_and_stops(tmp_path, monkeypatch):

    module = importlib.import_module('pipelinespec.core.pipeline')
    agent = FakeAgent()
    monkeypatch.setattr(module, 'constraint_agent', agent)
    monkeypatch.setattr(settings, 'constraints_only', False)
    output = tmp_path / 'out'

    result = CliRunner().invoke(main, ['-r', str(repository(tmp_path)), '-o', str(output), '--constraints-only'], catch_exceptions=False)

    assert result.exit_code == 0
    assert agent.calls == ['Shared', ('Shared', 'lint'), 'CI', ('CI', 'build'), ('CI', 'shared')]
    assert agent.samples == [None, None]
    assert not (output / 'variants.json').exists()

def test_constraints_only_runs_the_agent_n_times_into_numbered_files(tmp_path, monkeypatch):

    module = importlib.import_module('pipelinespec.core.pipeline')
    agent = FakeAgent()
    monkeypatch.setattr(module, 'constraint_agent', agent)
    monkeypatch.setattr(settings, 'constraints_only', False)
    output = tmp_path / 'out'

    result = CliRunner().invoke(main, ['-r', str(repository(tmp_path)), '-o', str(output), '--constraints-only', '-n', '2'], catch_exceptions=False)

    assert result.exit_code == 0
    assert agent.calls == ['Shared', ('Shared', 'lint'), 'CI', ('CI', 'build'), ('CI', 'shared')] * 2
    assert agent.samples == [1, 1, 2, 2]

def test_a_sampled_run_saves_numbered_constraints_and_records(tmp_path, monkeypatch):

    module = importlib.import_module('pipelinespec.constraint.agent')
    agent = module.constraint_agent
    names = []

    def run(name, _, __, ___, ____, save):

        names.append(name)
        save()

    monkeypatch.setattr(agent, '_ConstraintAgent__run', run)
    monkeypatch.setattr(settings, 'repo', repository(tmp_path))
    monkeypatch.setattr(settings.file, 'output', tmp_path / 'out')
    monkeypatch.setattr(module.git, 'head', lambda: None)
    monkeypatch.setattr(module.git, 'parent', lambda: None)
    monkeypatch.setattr(module.git, 'repository', lambda: None)

    workflow = Workflow.find_all(settings.repo / '.github' / 'workflows')[0]
    agent.find_workflow_triggers(workflow, 2)
    agent.find_job_constraints(workflow, workflow.jobs[0], 2)
    agent.find_workflow_triggers(workflow)

    assert names == [f'agents/{workflow.name}/workflow_agent_2', f'agents/{workflow.name}/{workflow.jobs[0].name}/constraint_agent_2', f'agents/{workflow.name}/workflow_agent']
    assert set(json.loads((tmp_path / 'out' / 'constraints_2.json').read_text())[workflow.name]['jobs']) == {workflow.jobs[0].name}
    assert json.loads((tmp_path / 'out' / 'constraints.json').read_text())[workflow.name]['jobs'] == {}

def test_trace_only_reads_constraints_runs_z3_and_never_calls_the_agent(tmp_path, monkeypatch):

    module = importlib.import_module('pipelinespec.core.pipeline')
    runner_module = importlib.import_module('pipelinespec.core.runner')
    agent, traced = FakeAgent(), []

    class Tracer:

        def run(self, _, variant, __):

            traced.append((variant.workflow, variant.job, variant.context.event))

            return TraceResult(id=uuid4(), path=Path('ci.yml'), job=variant.job, outcome='success')

    monkeypatch.setattr(module, 'constraint_agent', agent)
    monkeypatch.setattr(runner_module, 'tracer', Tracer())
    monkeypatch.setattr(runner_module, 'trace_filter', NoFilter())
    monkeypatch.setattr(settings, 'constraints', None)
    monkeypatch.setattr(settings, 'constraints_only', False)

    saved = saved_constraints(tmp_path)
    certificate = tmp_path / 'certificate'
    certificate.mkdir()
    output = tmp_path / 'out'

    result = CliRunner().invoke(main, ['-r', str(repository(tmp_path)), '-o', str(output), '-C', str(certificate), '--trace-only', '--constraints', str(saved)], catch_exceptions=False)

    assert result.exit_code == 0
    assert agent.calls == []
    assert set(traced) == {('Shared', 'lint', 'workflow_call'), ('CI', 'build', 'push')}
    assert (output / 'variants.json').exists()
    assert [node.name for node in AccessMap.model_validate_json((output / 'map.json').read_text()).jobs] == ['lint', 'build', 'shared']

def test_get_constraints_then_get_variants_for_every_job(tmp_path, monkeypatch):

    module = importlib.import_module('pipelinespec.core.pipeline')
    agent = FakeAgent()
    monkeypatch.setattr(module, 'constraint_agent', agent)
    monkeypatch.setattr(settings.file, 'output', tmp_path)

    workflows = Workflow.find_all(repository(tmp_path) / '.github' / 'workflows')
    constraints = module.pipeline.get_constraints(workflows)
    variants = module.pipeline.get_variants(workflows, constraints)

    assert agent.calls == ['Shared', ('Shared', 'lint'), 'CI', ('CI', 'build'), ('CI', 'shared')]
    assert set(constraints) == {'Shared', 'CI'} and set(constraints['CI'].jobs) == {'build', 'shared'}
    assert [(variant.workflow, variant.job, variant.context.event, variant.call) for variant in variants] == [('Shared', 'lint', 'workflow_call', False), ('CI', 'build', 'push', False), ('CI', 'shared', 'push', True)]
    assert variants[2].uses == './.github/workflows/shared.yml'
    assert [Variant.model_validate(variant) for variant in json.loads((tmp_path / 'variants.json').read_text())] == variants

def saved_constraints(tmp_path, jobs=('build', 'shared')):

    earlier = tmp_path / 'earlier'
    earlier.mkdir()
    gate = {'name': 'build.if', 'type': 'scope', 'location': 'ci.yml:5', 'any_of': [[{'name': 'event', 'op': '==', 'value': 'push'}]]}
    found = {'build': {'gates': [gate]}, 'shared': {}}
    content = {
        'Shared': {'triggers': [{'event': 'workflow_call'}], 'jobs': {'lint': {}}},
        'CI': {'triggers': [{'event': 'push', 'payload': {'ref': 'r'}}], 'jobs': {job: found[job] for job in jobs}},
    }
    saved = earlier / 'constraints.json'
    saved.write_text(json.dumps(content))

    return saved

def test_load_constraints_reads_the_file(tmp_path, monkeypatch):

    module = importlib.import_module('pipelinespec.core.pipeline')
    monkeypatch.setattr(settings, 'constraints', saved_constraints(tmp_path))

    found = module.pipeline.load_constraints(Workflow.find_all(repository(tmp_path) / '.github' / 'workflows'))

    assert [trigger.event for trigger in found['CI'].triggers] == ['push']
    assert [gate.name for gate in found['CI'].jobs['build'].gates] == ['build.if']

def test_load_constraints_refuses_a_file_missing_a_job(tmp_path, monkeypatch):

    module = importlib.import_module('pipelinespec.core.pipeline')
    monkeypatch.setattr(settings, 'constraints', saved_constraints(tmp_path, jobs=('build',)))

    with pytest.raises(ValueError, match='no entry for: CI / shared'):
        module.pipeline.load_constraints(Workflow.find_all(repository(tmp_path) / '.github' / 'workflows'))

def test_tracing_from_saved_constraints_builds_the_map(tmp_path, monkeypatch):

    module = importlib.import_module('pipelinespec.core.pipeline')
    runner_module = importlib.import_module('pipelinespec.core.runner')
    saved = saved_constraints(tmp_path)
    output = tmp_path / 'out'
    output.mkdir()
    traced = []

    class Tracer:

        def run(self, _, variant, __):

            traced.append((variant.job, variant.context.payload))

            return TraceResult(id=uuid4(), path=Path('ci.yml'), job=variant.job, outcome='success')

    monkeypatch.setattr(runner_module, 'tracer', Tracer())
    monkeypatch.setattr(runner_module, 'trace_filter', NoFilter())
    monkeypatch.setattr(settings, 'constraints', saved)
    monkeypatch.setattr(settings.file, 'output', output)

    workflows = Workflow.find_all(repository(tmp_path) / '.github' / 'workflows')
    variants = module.pipeline.get_variants(workflows, module.pipeline.load_constraints(workflows))
    monkeypatch.setattr(access_map, 'jobs', {})

    for trace in runner.get_traces(workflows, variants):
        access_map.add(trace)

    access_map.save()

    assert ('build', {'ref': 'r'}) in traced

    found = AccessMap.model_validate_json((output / 'map.json').read_text())
    assert [(node.name, node.events, node.uses) for node in found.jobs] == [('lint', ('workflow_call',), None), ('build', ('push',), None), ('shared', ('push',), './.github/workflows/shared.yml')]
    assert [gate.name for gate in found.jobs[1].gates] == ['build.if']

def test_load_constraints_needs_a_file(monkeypatch):

    module = importlib.import_module('pipelinespec.core.pipeline')
    monkeypatch.setattr(settings, 'constraints', None)

    with pytest.raises(ValueError, match='no constraints file'):
        module.pipeline.load_constraints([])

    monkeypatch.setattr(settings, 'constraints', Path('/missing/constraints.json'))

    with pytest.raises(ValueError, match='no constraints file'):
        module.pipeline.load_constraints([])

def test_cli_flags_must_come_together(tmp_path):

    saved = tmp_path / 'saved.json'
    saved.write_text('{}')
    repo = str(repository(tmp_path))

    assert 'requires --constraints' in CliRunner().invoke(main, ['-r', repo, '--trace-only']).output
    assert '--trace-only is missing' in CliRunner().invoke(main, ['-r', repo, '--constraints', str(saved)]).output
    assert 'cannot be used together' in CliRunner().invoke(main, ['-r', repo, '--trace-only', '--constraints-only', '--constraints', str(saved)]).output
    assert '-n requires --constraints-only' in CliRunner().invoke(main, ['-r', repo, '-n', '3']).output
    assert 'Invalid value' in CliRunner().invoke(main, ['-r', repo, '--constraints-only', '-n', '0']).output

def test_traces_every_job_except_a_call_site_and_maps_them(tmp_path, monkeypatch):

    module = importlib.import_module('pipelinespec.core.pipeline')
    runner_module = importlib.import_module('pipelinespec.core.runner')
    traced = []

    class Tracer:

        def run(self, _, variant, __):

            traced.append((variant.workflow, variant.job))

            return TraceResult(id=uuid4(), path=Path('ci.yml'), job=variant.job, outcome='success')

    monkeypatch.setattr(module, 'constraint_agent', FakeAgent())
    monkeypatch.setattr(runner_module, 'tracer', Tracer())
    monkeypatch.setattr(runner_module, 'trace_filter', NoFilter())
    monkeypatch.setattr(settings, 'repo', repository(tmp_path))
    monkeypatch.setattr(settings, 'constraints_only', False)
    monkeypatch.setattr(settings.file, 'output', tmp_path)

    workflows = Workflow.find_all(settings.repo / '.github' / 'workflows')
    variants = module.pipeline.get_variants(workflows, module.pipeline.get_constraints(workflows))

    monkeypatch.setattr(access_map, 'jobs', {})

    for trace in runner.get_traces(workflows, variants):
        access_map.add(trace)

    access_map.save()

    assert traced == [('Shared', 'lint')] * 2 + [('CI', 'build')] * 2

    saved = AccessMap.model_validate_json((tmp_path / 'map.json').read_text())
    assert [(node.workflow, node.name, len(node.tested)) for node in saved.jobs] == [('Shared', 'lint', 1), ('CI', 'build', 1), ('CI', 'shared', 0)]

    trials = json.loads((tmp_path / 'trials.json').read_text())
    assert set(trials) == {'CI', 'Shared'}

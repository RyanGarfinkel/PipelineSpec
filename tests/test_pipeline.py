from pipelinespec.models import AccessMap, JobConstraints, TraceResult, Variant, Workflow, WorkflowTrigger
from pipelinespec.core import Tracing, mapper
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

class NoSubtraction:

    def run(self, result, _, __):

        return result

class FakeAgent:

    def __init__(self):

        self.calls = []

    def find_workflow_triggers(self, workflow):

        self.calls.append(workflow.name)

        return [WorkflowTrigger(event='workflow_call' if workflow.name == 'Shared' else 'push')]

    def find_job_constraints(self, workflow, job):

        self.calls.append((workflow.name, job.name))

        return JobConstraints()

def repository(tmp_path):

    workflows = tmp_path / 'repo' / '.github' / 'workflows'
    workflows.mkdir(parents=True)
    (workflows / 'ci.yml').write_text(CI)
    (workflows / 'shared.yml').write_text(SHARED)

    return tmp_path / 'repo'

def test_every_workflow_then_its_jobs(tmp_path, monkeypatch):

    module = importlib.import_module('pipelinespec.core.pipeline')
    agent = FakeAgent()
    monkeypatch.setattr(module, 'constraint_agent', agent)
    output = tmp_path / 'out'

    result = CliRunner().invoke(main, ['-r', str(repository(tmp_path)), '-o', str(output), '--variants-only'], catch_exceptions=False)

    assert result.exit_code == 0
    assert agent.calls == ['Shared', ('Shared', 'lint'), 'CI', ('CI', 'build'), ('CI', 'shared')]

    variants = json.loads((output / 'variants.json').read_text())
    assert [(variant['workflow'], variant['job'], variant['call']) for variant in variants] == [('Shared', 'lint', False), ('CI', 'build', False), ('CI', 'shared', True)]

def test_trace_only_reads_variants_and_never_calls_the_agent_or_z3(tmp_path, monkeypatch):

    module = importlib.import_module('pipelinespec.core.pipeline')
    loop = importlib.import_module('pipelinespec.core.loop')
    agent, traced = FakeAgent(), []

    class Tracer:

        def run(self, config):

            traced.append((config.workflow, config.job, config.context.event))

            return TraceResult(id=uuid4(), path=Path('ci.yml'), job=config.job, outcome='success')

    monkeypatch.setattr(module, 'constraint_agent', agent)
    monkeypatch.setattr(loop, 'tracer', Tracer())
    monkeypatch.setattr(loop, 'subtractor', NoSubtraction())

    class NoSolver:

        def solve(self, *_):

            raise AssertionError('Z3 must not run')

    monkeypatch.setattr(module, 'smt', NoSolver())

    saved = saved_run(tmp_path)
    certificate = tmp_path / 'certificate'
    certificate.mkdir()
    output = tmp_path / 'out'

    result = CliRunner().invoke(main, ['-r', str(repository(tmp_path)), '-o', str(output), '-C', str(certificate), '--trace-only', '--variants', str(saved)], catch_exceptions=False)

    assert result.exit_code == 0
    assert agent.calls == []
    assert traced == [('CI', 'build', 'push')] * 2
    assert [node.name for node in AccessMap.model_validate_json((output / 'map.json').read_text()).jobs] == ['build', 'shared']

    settings.variants = None

def test_get_variants_runs_the_agent_and_z3_for_every_job(tmp_path, monkeypatch):

    module = importlib.import_module('pipelinespec.core.pipeline')
    agent = FakeAgent()
    monkeypatch.setattr(module, 'constraint_agent', agent)
    monkeypatch.setattr(settings.file, 'output', tmp_path)

    workflows = Workflow.find_all(repository(tmp_path) / '.github' / 'workflows')
    variants = module.pipeline.get_variants(workflows)

    assert agent.calls == ['Shared', ('Shared', 'lint'), 'CI', ('CI', 'build'), ('CI', 'shared')]
    assert [(variant.workflow, variant.job, variant.context.event, variant.call) for variant in variants] == [('Shared', 'lint', 'workflow_call', False), ('CI', 'build', 'push', False), ('CI', 'shared', 'push', True)]
    assert variants[2].uses == './.github/workflows/shared.yml'
    assert [Variant.model_validate(variant) for variant in json.loads((tmp_path / 'variants.json').read_text())] == variants

def saved_run(tmp_path):

    earlier = tmp_path / 'earlier'
    earlier.mkdir()
    gate = {'name': 'build.if', 'type': 'scope', 'location': 'ci.yml:5', 'any_of': [[{'name': 'event', 'op': '==', 'value': 'push'}]]}
    build = {'workflow': 'CI', 'job': 'build', 'reason': 'push: picked', 'assignment': {'event': 'push'}, 'context': {'event': 'push', 'payload': {'ref': 'r'}}, 'constraints': {'gates': [gate]}, 'needs': ['setup']}
    shared = {'workflow': 'CI', 'job': 'shared', 'reason': 'push: call', 'assignment': {'event': 'push'}, 'context': {'event': 'push'}, 'constraints': {}, 'call': True, 'uses': './.github/workflows/shared.yml'}
    saved = earlier / 'variants.json'
    saved.write_text(json.dumps([build, shared]))

    return saved

def test_load_variants_reads_the_list(tmp_path, monkeypatch):

    module = importlib.import_module('pipelinespec.core.pipeline')

    monkeypatch.setattr(settings, 'variants', saved_run(tmp_path))

    variants = module.pipeline.load_variants()

    assert [(variant.workflow, variant.job, variant.context.payload) for variant in variants] == [('CI', 'build', {'ref': 'r'}), ('CI', 'shared', {})]

def test_tracing_each_variant_and_saving_builds_the_map_from_variants_alone(tmp_path, monkeypatch):

    module = importlib.import_module('pipelinespec.core.pipeline')
    loop = importlib.import_module('pipelinespec.core.loop')
    saved = saved_run(tmp_path)
    output = tmp_path / 'out'
    output.mkdir()
    traced = []

    class Tracer:

        def run(self, config):

            traced.append((config.job, config.context.payload))

            return TraceResult(id=uuid4(), path=Path('ci.yml'), job=config.job, outcome='success')

    monkeypatch.setattr(loop, 'tracer', Tracer())
    monkeypatch.setattr(loop, 'subtractor', NoSubtraction())
    monkeypatch.setattr(settings, 'variants', saved)
    monkeypatch.setattr(settings.file, 'output', output)

    variants = module.pipeline.load_variants()
    results = []

    with Tracing(len(variants)) as tracer:
        for variant in variants:
            results.append(tracer.trace(variant))
            mapper.save(mapper.build(results))

    assert traced == [('build', {'ref': 'r'})] * 2

    found = AccessMap.model_validate_json((output / 'map.json').read_text())
    assert [(node.name, node.events, node.needs, node.uses, len(node.tested), len(node.variants)) for node in found.jobs] == [('build', ('push',), ('setup',), None, 1, 1), ('shared', ('push',), (), './.github/workflows/shared.yml', 0, 0)]
    assert [gate.name for gate in found.jobs[0].gates] == ['build.if']

def test_load_variants_needs_a_file(monkeypatch):

    module = importlib.import_module('pipelinespec.core.pipeline')
    monkeypatch.setattr(settings, 'variants', None)

    with pytest.raises(ValueError, match='no variants file'):
        module.pipeline.load_variants()

    monkeypatch.setattr(settings, 'variants', Path('/missing/variants.json'))

    with pytest.raises(ValueError, match='no variants file'):
        module.pipeline.load_variants()

def test_trace_only_flags_must_come_together(tmp_path):

    saved = tmp_path / 'saved.json'
    saved.write_text('{}')
    repo = str(repository(tmp_path))

    assert 'requires --variants' in CliRunner().invoke(main, ['-r', repo, '--trace-only']).output
    assert 'missing --trace-only' in CliRunner().invoke(main, ['-r', repo, '--variants', str(saved)]).output
    assert 'cannot be used together' in CliRunner().invoke(main, ['-r', repo, '--trace-only', '--variants-only', '--variants', str(saved)]).output

def test_traces_every_job_except_a_call_site_and_maps_them(tmp_path, monkeypatch):

    module = importlib.import_module('pipelinespec.core.pipeline')
    loop = importlib.import_module('pipelinespec.core.loop')
    traced = []

    class Tracer:

        def run(self, config):

            traced.append((config.workflow, config.job))

            return TraceResult(id=uuid4(), path=Path('ci.yml'), job=config.job, outcome='success')

    monkeypatch.setattr(module, 'constraint_agent', FakeAgent())
    monkeypatch.setattr(loop, 'tracer', Tracer())
    monkeypatch.setattr(loop, 'subtractor', NoSubtraction())
    monkeypatch.setattr(settings, 'repo', repository(tmp_path))
    monkeypatch.setattr(settings, 'variants_only', False)
    monkeypatch.setattr(settings.file, 'output', tmp_path)

    variants = module.pipeline.get_variants(Workflow.find_all(settings.repo / '.github' / 'workflows'))
    results = []

    with Tracing(len(variants)) as tracer:
        for variant in variants:
            results.append(tracer.trace(variant))

    mapper.save(mapper.build(results))

    assert traced == [('Shared', 'lint')] * 2 + [('CI', 'build')] * 2

    saved = AccessMap.model_validate_json((tmp_path / 'map.json').read_text())
    assert [(node.workflow, node.name, len(node.tested)) for node in saved.jobs] == [('Shared', 'lint', 1), ('CI', 'build', 1), ('CI', 'shared', 0)]

    trials = json.loads((tmp_path / 'trials.json').read_text())
    assert set(trials) == {'CI', 'Shared'}

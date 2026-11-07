from langgraph.errors import GraphRecursionError
from pipelinespec.models import Mocks, Workflow
from importlib import import_module
from pipelinespec import settings
import json

CI = '''
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo build
'''

class Stuck:

    def __init__(self, before=None):

        self.before = before

    def invoke(self, *_, **__):

        if self.before:
            self.before()

        raise GraphRecursionError('Recursion limit reached')

def test_a_constraint_agent_at_its_step_limit_keeps_what_it_recorded(tmp_path, monkeypatch):

    module = import_module('pipelinespec.constraint.agent')
    workflows = tmp_path / 'repo' / '.github' / 'workflows'
    workflows.mkdir(parents=True)
    (workflows / 'ci.yml').write_text(CI)
    captured = {}

    def create_agent(_, tools, **__):

        captured['tools'] = {tool.name: tool for tool in tools}

        return Stuck(lambda: captured['tools']['add_constant'].invoke({'target': 'payload.ref', 'value': 'refs/heads/main'}))

    monkeypatch.setattr(module, 'create_agent', create_agent)
    monkeypatch.setattr(module.model, 'get_llm', lambda: None)
    monkeypatch.setattr(module.model, 'middleware', lambda: [])
    monkeypatch.setattr(settings, 'repo', tmp_path / 'repo')
    monkeypatch.setattr(settings.file, 'output', tmp_path / 'out')

    for name in ('head', 'parent', 'repository'):
        monkeypatch.setattr(module.git, name, lambda: None)

    workflow = Workflow.find_all(workflows)[0]
    found = module.constraint_agent.find_job_constraints(workflow, workflow.jobs[0])

    assert found.constants == {'payload.ref': 'refs/heads/main'}
    assert json.loads((tmp_path / 'out' / 'constraints.json').read_text())['CI']['jobs']['build']['constants'] == {'payload.ref': 'refs/heads/main'}

    record = json.loads((tmp_path / 'out' / 'agents' / 'CI' / 'build' / 'constraint_agent.json').read_text())
    assert record['events'][-1]['type'] == 'limit'

def test_a_diagnoser_at_its_step_limit_answers_not_fixable(tmp_path, monkeypatch):

    module = import_module('pipelinespec.diagnose.agent')
    run_dir = tmp_path / 'runs' / 'r1'
    run_dir.mkdir(parents=True)
    (run_dir / 'config.json').write_text(json.dumps({'workflow': 'CI', 'job': 'build', 'context': {'event': 'push'}}))
    (run_dir / 'result.json').write_text(json.dumps({'outcome': 'failure', 'steps': [], 'commands': []}))

    monkeypatch.setattr(module, 'create_agent', lambda *_, **__: Stuck())
    monkeypatch.setattr(module.model, 'get_llm', lambda: None)
    monkeypatch.setattr(module.model, 'middleware', lambda: [])
    monkeypatch.setattr(settings.file, 'output', tmp_path)

    diagnosis = module.diagnoser.run(run_dir, Mocks())

    assert not diagnosis.fixable and 'limit' in diagnosis.reason
    assert json.loads((run_dir / 'diagnose_agent.json').read_text())['events'][-1]['type'] == 'limit'

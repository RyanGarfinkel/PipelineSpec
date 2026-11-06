from pipelinespec.utils.guard import GuardCallbackHandler, MAX_ERRORS, REJECTED
from pipelinespec.diagnose.tools import RunTools
from pipelinespec.diagnose.prompt import DIAGNOSE
from pipelinespec.models import Mocks
import pytest
import json

def tools(tmp_path, mocks):

    (tmp_path / 'config.json').write_text(json.dumps({'workflow': 'CI', 'job': 'build', 'context': {'event': 'push'}}))
    (tmp_path / 'result.json').write_text(json.dumps({'outcome': 'failure', 'steps': [], 'commands': [['curl', 'x']]}))
    (tmp_path / 'secrets.json').write_text(json.dumps({'PROVIDED': 'pspec-1'}))

    return {tool.name: tool for tool in RunTools(tmp_path, mocks).get()}

def test_prompt_names_only_tools_that_exist(tmp_path):

    found = tools(tmp_path, Mocks())

    assert set(found) == {'failed_steps', 'step_source', 'step_output', 'commands', 'traffic', 'additions', 'add_credential', 'add_mock'}
    assert all(name in DIAGNOSE for name in found)
    assert all(block in DIAGNOSE for block in ('<role>', '<platform>', '<goal>', '<inputs>', '<procedure>', '<rules>', '<example>'))

def test_write_tools_reject_what_changes_nothing(tmp_path):

    mocks = Mocks()
    found = tools(tmp_path, mocks)
    mock = {'method': 'GET', 'url': 'https://api.example.com/*', 'json_body': '{"ok": true}'}

    assert found['add_credential'].invoke({'name': 'DEPLOY_KEY'}).startswith('Added credential DEPLOY_KEY')
    assert found['add_mock'].invoke(mock).startswith('Added the mock')
    assert found['add_mock'].invoke({**mock, 'status': 201}).startswith('Replaced the mock')
    assert mocks.credentials == ['DEPLOY_KEY'] and len(mocks.calls) == 1

    for rejection in (
        found['add_credential'].invoke({'name': 'DEPLOY_KEY'}),
        found['add_credential'].invoke({'name': 'PROVIDED'}),
        found['add_credential'].invoke({'name': 'not valid'}),
        found['add_mock'].invoke({**mock, 'status': 201}),
        found['add_mock'].invoke({**mock, 'json_body': 'not json'}),
        found['add_mock'].invoke({'method': 'GET', 'url': 'http://localhost:3000/'}),
        found['add_mock'].invoke({'method': 'GET', 'url': 'http://host.docker.internal/x'}),
    ):
        assert rejection.startswith(REJECTED)

    assert mocks.credentials == ['DEPLOY_KEY'] and len(mocks.calls) == 1

def test_guard_stops_a_model_repeating_a_rejected_call(tmp_path):

    found = tools(tmp_path, Mocks())
    guard = GuardCallbackHandler()

    for _ in range(MAX_ERRORS - 1):
        guard.on_tool_end(found['add_credential'].invoke({'name': 'PROVIDED'}))

    with pytest.raises(RuntimeError, match='rejected tool calls'):
        guard.on_tool_end(found['add_credential'].invoke({'name': 'PROVIDED'}))

def test_github_token_can_be_added(tmp_path):

    mocks = Mocks()

    assert tools(tmp_path, mocks)['add_credential'].invoke({'name': 'GITHUB_TOKEN'}).startswith('Added credential')
    assert mocks.credentials == ['GITHUB_TOKEN']

def test_step_output_includes_error_lines(tmp_path):

    found = tools(tmp_path, Mocks())
    lines = [
        {'jobID': 'build', 'stepID': ['1'], 'raw_output': True, 'msg': 'printed\n'},
        {'jobID': 'build', 'stepID': ['1'], 'level': 'error', 'msg': '::error::the cause\n'},
        {'jobID': 'build', 'stepID': ['1'], 'level': 'debug', 'msg': 'noise\n'},
    ]
    (tmp_path / 'run.jsonl').write_text('\n'.join(json.dumps(line) for line in lines))

    output = found['step_output'].invoke({'step': '1'})

    assert 'printed' in output and 'the cause' in output and 'noise' not in output

def test_commands_lists_the_job_programs(tmp_path):

    assert tools(tmp_path, Mocks())['commands'].invoke({}) == 'curl x'

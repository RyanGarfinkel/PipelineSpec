from pipelinespec.constraint.tools import constraint_tools
from pipelinespec.models import Constraints, Trigger
from pydantic import ValidationError
import pytest
import json

def term(name, op, value):

    return {'name': name, 'op': op, 'value': value}

def test_triggers():

    found: list[Trigger] = []
    tools = {tool.name: tool for tool in constraint_tools.triggers(found)}
    push = {'event': 'push', 'payload': {'ref': 'refs/heads/release/1.0'}}

    assert set(tools) == {'add_trigger', 'recorded'}
    assert tools['add_trigger'].invoke(push) == 'Recorded successfully.'
    assert tools['add_trigger'].invoke({'event': 'schedule'}) == 'Recorded successfully.'
    assert tools['add_trigger'].invoke(push).startswith('Rejected, nothing recorded: The example for "push" is already recorded')
    assert tools['add_trigger'].invoke({**push, 'payload': {'ref': 'refs/heads/release/2.0'}}) == 'Recorded successfully. It replaced the earlier example for "push".'
    assert json.loads(tools['recorded'].invoke({})) == [{'event': 'push', 'payload': {'ref': 'refs/heads/release/2.0'}}, {'event': 'schedule', 'payload': {}}]

def test_tools():

    constraints = Constraints(events=['push', 'workflow_dispatch'])
    tools = {tool.name: tool for tool in constraint_tools.get(constraints)}

    assert set(tools) == {'add_gate', 'add_variable', 'add_unsolved', 'add_constant', 'recorded'}

    tag = {'name': 'job.if', 'type': 'scope', 'location': 'ci.yml:10', 'any_of': [[term('ref', 'starts_with', 'refs/tags/v')]]}
    step = {'name': 'step.if', 'type': 'scope', 'location': 'ci.yml:35', 'any_of': [[term('dry_run', '==', False)]]}
    branch = {'name': 'run.sh.upload', 'type': 'branch', 'location': 'run.sh:3', 'any_of': [[term('event', '==', 'push')]]}
    ref = {'name': 'ref', 'target': 'payload.ref', 'values': ['refs/tags/v1', 'refs/heads/dev']}
    dry_run = {'name': 'dry_run', 'target': 'payload.inputs.dry_run', 'values': [False, True]}

    assert tools['add_gate'].invoke(branch) == 'Recorded successfully.'
    assert tools['add_gate'].invoke(tag) == 'Recorded successfully. Declare a variable with add_variable for: ref.'
    assert tools['add_gate'].invoke(step) == 'Recorded successfully. Declare a variable with add_variable for: dry_run.'
    assert constraint_tools.pending(constraints) == {'job.if': ['ref'], 'step.if': ['dry_run']}

    assert tools['add_variable'].invoke(ref) == 'Recorded successfully.'
    assert tools['add_variable'].invoke(dry_run) == 'Recorded successfully.'
    assert constraint_tools.pending(constraints) == {}
    assert tools['add_gate'].invoke(step).startswith('Rejected, nothing recorded: "step.if" is already recorded exactly like this')
    assert tools['add_variable'].invoke(dry_run).startswith('Rejected, nothing recorded: "dry_run" is already declared exactly like this')

    assert tools['add_gate'].invoke({**step, 'any_of': [[term('dry_run', '==', 'true')]]}).startswith('Rejected, nothing recorded: "dry_run" holds bool values, but it is compared with \'true\', a str. Compare it with true or false.')
    assert tools['add_gate'].invoke({**step, 'any_of': [[term('dry_run', 'contains', 'x')]]}).startswith('Rejected, nothing recorded: contains works on strings, but "dry_run" holds bool values.')
    assert tools['add_gate'].invoke({**step, 'any_of': [[term('event', '<', 3)]]}).startswith('Rejected, nothing recorded: < compares numbers, but "event" holds str values.')
    assert tools['add_variable'].invoke({'name': 'unused', 'target': 'payload.number', 'values': [1, 2]}).startswith('Rejected, nothing recorded: No recorded gate uses the name "unused"')
    assert tools['add_variable'].invoke({'name': 'ref', 'target': 'payload.inputs.dry_run', 'values': ['refs/tags/v1', 'refs/heads/dev']}).startswith('Rejected, nothing recorded: "ref" (payload.inputs.dry_run) has str values')

    count = {'name': 'num.if', 'type': 'branch', 'location': 'run.sh:7', 'any_of': [[term('count', '>', 3)]]}

    assert tools['add_gate'].invoke(count).startswith('Recorded successfully. Declare')
    assert tools['add_variable'].invoke({'name': 'count', 'target': 'payload.count', 'values': ['3', '4']}).startswith('Rejected, nothing recorded: With this variable, gate "num.if" is not valid')
    assert tools['add_variable'].invoke({'name': 'count', 'target': 'payload.count', 'values': [3, 4]}) == 'Recorded successfully.'

    assert tools['add_unsolved'].invoke({'name': 'step.success', 'reason': 'success() is the run status', 'location': 'ci.yml:39'}) == 'Recorded successfully.'
    assert tools['add_constant'].invoke({'target': 'payload.head_commit.id', 'value': 'abc'}) == 'Recorded successfully.'
    assert tools['add_constant'].invoke({'target': 'payload.head_commit.id', 'value': 'abc'}).startswith('Rejected, nothing recorded: "payload.head_commit.id" is already recorded')
    assert tools['add_constant'].invoke({'target': 'payload.number', 'value': 1}) == 'Recorded successfully.'
    assert tools['add_constant'].invoke({'target': 'payload.ref', 'value': 'refs/heads/main'}).startswith('Rejected, nothing recorded: "payload.ref" is a variable of the gates')

    sha = {'name': 'sha.if', 'type': 'branch', 'location': 'run.sh:5', 'any_of': [[term('sha', '==', 'abc')]]}

    assert tools['add_gate'].invoke(sha).startswith('Recorded successfully. Declare')
    assert 'It replaced the constant for payload.head_commit.id' in tools['add_variable'].invoke({'name': 'sha', 'target': 'payload.head_commit.id', 'values': ['abc', 'def']})
    assert 'payload.head_commit.id' not in constraints.constants

    shown = json.loads(tools['recorded'].invoke({}))

    assert shown['events'] == ['push', 'workflow_dispatch']
    assert [gate['name'] for gate in shown['gates']] == ['run.sh.upload', 'job.if', 'step.if', 'num.if', 'sha.if']
    assert shown['gates'][2]['any_of'] == [[term('dry_run', '==', False)]]
    assert set(shown['variables']) == {'ref', 'dry_run', 'count', 'sha'}
    assert shown['constants'] == {'payload.number': 1}

    aliased = {'name': 'alias.if', 'type': 'scope', 'location': 'ci.yml:50', 'any_of': [[term('inputs.dry_run', '==', False)]]}
    ambiguous = {**aliased, 'name': 'ambiguous.if', 'any_of': [[term('dry_run2', '==', False), term('other.flag', '==', False), term('flag', '==', False)]]}

    assert tools['add_gate'].invoke(aliased) == 'Recorded successfully.'
    assert tools['add_gate'].invoke(ambiguous).startswith('Recorded successfully. Declare')
    assert tools['add_variable'].invoke({'name': 'first', 'target': 'payload.unrelated.value', 'values': [False, True]}).startswith('Rejected, nothing recorded: No recorded gate uses')
    assert tools['add_variable'].invoke({'name': 'dry_run2', 'target': 'payload.inputs.dry_run2', 'values': [False, True]}) == 'Recorded successfully.'
    assert tools['add_variable'].invoke({'name': 'a', 'target': 'payload.one.flag', 'values': [False, True]}) == 'Recorded successfully.'
    assert tools['add_variable'].invoke({'name': 'b', 'target': 'payload.other.flag', 'values': [False, True]}) == 'Recorded successfully.'
    assert constraint_tools.pending(constraints) == {'ambiguous.if': ['flag']}

    with pytest.raises(ValidationError, match='location'):
        tools['add_gate'].invoke({key: value for key, value in step.items() if key != 'location'})

    with pytest.raises(ValidationError, match='any_of'):
        tools['add_gate'].invoke({**step, 'any_of': []})

    with pytest.raises(ValidationError, match='at least 1 item'):
        tools['add_gate'].invoke({**step, 'any_of': [[]]})

    with pytest.raises(ValidationError, match='op'):
        tools['add_gate'].invoke({**step, 'any_of': [[term('dry_run', 'is', False)]]})

    with pytest.raises(ValidationError, match='not something the run context sets'):
        tools['add_variable'].invoke({'name': 'dry_run', 'target': 'github.repository', 'values': [True]})

    with pytest.raises(ValidationError, match='event is built in'):
        tools['add_variable'].invoke({'name': 'dry_run', 'target': 'event', 'values': [True]})

    with pytest.raises(ValidationError, match='mix types'):
        tools['add_variable'].invoke({'name': 'dry_run', 'target': 'payload.inputs.dry_run', 'values': [False, 'true']})

    with pytest.raises(ValidationError, match='not something the run context sets'):
        tools['add_constant'].invoke({'target': 'base_sha', 'value': 'x'})

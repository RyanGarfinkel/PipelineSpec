from pipelinespec.utils.guard import GuardCallbackHandler, MAX_ERRORS, REJECTED
from pipelinespec.constraint.tools import constraint_tools
from pipelinespec.models import Constraints
import pytest

def test_guard_counts_the_rejections_of_the_tools():

    tools = {tool.name: tool for tool in constraint_tools.get(Constraints())}
    rejection = tools['add_variable'].invoke({'name': 'unused', 'target': 'payload.number', 'values': [1, 2]})
    guard = GuardCallbackHandler()

    assert rejection.startswith(REJECTED)

    for _ in range(MAX_ERRORS - 1):
        guard.on_tool_end(rejection)

    with pytest.raises(RuntimeError, match='No recorded gate uses'):
        guard.on_tool_end(rejection)

def test_guard():

    guard = GuardCallbackHandler()

    for _ in range(MAX_ERRORS - 1):
        guard.on_tool_error(ValueError('rejected'))

    guard.on_tool_end('Recorded successfully.')

    for _ in range(MAX_ERRORS - 1):
        guard.on_tool_error(ValueError('rejected'))

    with pytest.raises(RuntimeError, match='rejected tool calls in a row'):
        guard.on_tool_error(ValueError('still rejected'))

    handled = GuardCallbackHandler()

    for _ in range(MAX_ERRORS - 1):
        handled.on_tool_end(f'{REJECTED} wrong type')

    with pytest.raises(RuntimeError, match='wrong type'):
        handled.on_tool_end(f'{REJECTED} wrong type')

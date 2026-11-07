from pipelinespec.utils.guard import GuardCallbackHandler, MAX_ERRORS, REJECTED
from pipelinespec.constraint.tools import constraint_tools
from pipelinespec.models import JobConstraints
import pytest

def test_guard_counts_the_rejections_of_the_tools():

    tools = {tool.name: tool for tool in constraint_tools.get(JobConstraints())}
    rejection = tools['add_variable'].invoke({'name': 'unused', 'target': 'payload.number', 'values': [1, 2]})
    guard = GuardCallbackHandler()

    assert rejection.startswith(REJECTED)

    for _ in range(MAX_ERRORS):
        guard.on_chat_model_start()
        guard.on_tool_end(rejection)

    with pytest.raises(RuntimeError, match='No recorded gate uses'):
        guard.on_chat_model_start()

def test_guard():

    guard = GuardCallbackHandler()

    for _ in range(MAX_ERRORS - 1):
        guard.on_chat_model_start()
        guard.on_tool_error(ValueError('rejected'))

    guard.on_chat_model_start()
    guard.on_tool_error(ValueError('rejected'))
    guard.on_tool_end('Recorded successfully.')

    for _ in range(MAX_ERRORS):
        guard.on_chat_model_start()
        guard.on_tool_error(ValueError('rejected'))

    with pytest.raises(RuntimeError, match='all rejected'):
        guard.on_chat_model_start()

    handled = GuardCallbackHandler()

    for _ in range(MAX_ERRORS):
        handled.on_chat_model_start()
        handled.on_tool_end(f'{REJECTED} wrong type')

    with pytest.raises(RuntimeError, match='wrong type'):
        handled.on_chat_model_start()

def test_guard_lets_the_model_see_a_reply_of_rejected_calls():

    guard = GuardCallbackHandler()
    guard.on_chat_model_start()

    for _ in range(MAX_ERRORS * 2):
        guard.on_tool_error(ValueError('rejected'))

    guard.on_chat_model_start()

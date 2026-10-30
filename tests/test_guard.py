from pipelinespec.utils.guard import GuardCallbackHandler, MAX_ERRORS, REJECTED
import pytest

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

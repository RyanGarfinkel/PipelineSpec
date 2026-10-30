from langchain_core.outputs import ChatGeneration, LLMResult
from pipelinespec.utils.record import RecordCallbackHandler
from langchain_core.messages import AIMessage
from pipelinespec import settings
from unittest.mock import patch
from uuid import uuid4
import json

def llm_result(content: str, input_tokens: int, output_tokens: int, tool_calls: list | None = None) -> LLMResult:

    usage = {'input_tokens': input_tokens, 'output_tokens': output_tokens, 'total_tokens': input_tokens + output_tokens}

    return LLMResult(generations=[[ChatGeneration(message=AIMessage(content=content, tool_calls=tool_calls or [], usage_metadata=usage))]])

def test_record(tmp_path):

    with patch.object(settings.file, 'output', tmp_path):
        recorder = RecordCallbackHandler('agent')

        recorder.on_chain_start({}, {}, run_id=uuid4(), parent_run_id=None)

        model_run, tool_run, failed_run = uuid4(), uuid4(), uuid4()
        recorder.on_chat_model_start({}, [], run_id=model_run)
        recorder.on_llm_end(llm_result('', 100, 20, [{'name': 'add_gate', 'args': {}, 'id': '1'}]), run_id=model_run)
        recorder.on_tool_start({'name': 'add_gate'}, "{'gate': {}}", run_id=tool_run, inputs={'gate': {'name': 'g'}})
        recorder.on_tool_end('Recorded successfully.', run_id=tool_run)
        recorder.on_tool_start({'name': 'add_variable'}, '', run_id=failed_run, inputs={'variable': {}})
        recorder.on_tool_error(ValueError('Rejected'), run_id=failed_run)

        recorder.on_chain_start({}, {}, run_id=uuid4(), parent_run_id=None)
        recorder.on_chain_start({}, {}, run_id=uuid4(), parent_run_id=uuid4())
        recorder.on_llm_end(llm_result('done', 50, 5), run_id=uuid4())

    saved = json.loads((tmp_path / 'agent.json').read_text())

    assert [event['type'] for event in saved['events']] == ['llm', 'tool', 'tool', 'llm']
    assert [event['run'] for event in saved['events']] == [1, 1, 1, 2]

    assert saved['events'][0]['tool_calls'] == 1
    assert saved['events'][1]['name'] == 'add_gate' and saved['events'][1]['input'] == {'gate': {'name': 'g'}}
    assert saved['events'][1]['output'] == 'Recorded successfully.'
    assert saved['events'][2]['error'] == 'Rejected' and 'output' not in saved['events'][2]
    assert saved['events'][3]['text'] == 'done'

    assert saved['usage']['total'] == {'input_tokens': 150, 'output_tokens': 25, 'total_tokens': 175}
    assert saved['usage']['runs'] == [
        {'run': 1, 'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120},
        {'run': 2, 'input_tokens': 50, 'output_tokens': 5, 'total_tokens': 55},
    ]

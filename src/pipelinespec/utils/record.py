from langchain_core.callbacks import BaseCallbackHandler
from pipelinespec import settings
from threading import Lock
from typing import Any
import json
import time

class RecordCallbackHandler(BaseCallbackHandler):

    def __init__(self, name: str):

        self.name = name
        self.events: list[dict[str, Any]] = []
        self.starts: dict[Any, float] = {}
        self.calls: dict[Any, tuple[str, Any]] = {}
        self.runs = 0
        self.lock = Lock()

    def on_chain_start(self, *_, parent_run_id=None, **__):

        if parent_run_id is None:
            self.runs += 1

    def on_chat_model_start(self, _, __, *, run_id, **___):

        self.starts[run_id] = time.monotonic()

    def on_llm_end(self, response, *, run_id, **__):

        message = response.generations[0][0].message
        usage = message.usage_metadata or {}
        content = message.content if isinstance(message.content, str) else ''.join(block.get('text', '') for block in message.content if isinstance(block, dict))
        input_tokens, output_tokens = usage.get('input_tokens', 0), usage.get('output_tokens', 0)

        self.__add({
            'type': 'llm',
            'seconds': self.__elapsed(run_id),
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': usage.get('total_tokens', input_tokens + output_tokens),
            'tool_calls': len(message.tool_calls),
            'text': content,
        })

    def on_tool_start(self, serialized, input_str, *, run_id, inputs=None, **__):

        self.starts[run_id] = time.monotonic()
        self.calls[run_id] = (serialized.get('name', 'tool'), inputs if inputs is not None else input_str)

    def on_tool_end(self, output, *, run_id, **__):

        name, arguments = self.calls.pop(run_id, ('tool', None))

        self.__add({'type': 'tool', 'name': name, 'input': arguments, 'output': str(getattr(output, 'content', output)), 'seconds': self.__elapsed(run_id)})

    def on_tool_error(self, error, *, run_id, **__):

        name, arguments = self.calls.pop(run_id, ('tool', None))

        self.__add({'type': 'tool', 'name': name, 'input': arguments, 'error': str(error), 'seconds': self.__elapsed(run_id)})

    def usage(self) -> dict[str, Any]:

        def total(events: list[dict[str, Any]]) -> dict[str, int]:

            return {key: sum(event[key] for event in events) for key in ('input_tokens', 'output_tokens', 'total_tokens')}

        calls = [event for event in self.events if event['type'] == 'llm']

        return {'total': total(calls), 'runs': [{'run': number, **total([event for event in calls if event['run'] == number])} for number in range(1, self.runs + 1)]}

    def __add(self, event: dict[str, Any]) -> None:

        with self.lock:
            self.events.append({'run': self.runs, **event})

            path = settings.file.output / f'{self.name}.json'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({'usage': self.usage(), 'events': self.events}, indent=4, default=str))

    def __elapsed(self, run_id) -> float:

        return round(time.monotonic() - self.starts.pop(run_id, time.monotonic()), 3)

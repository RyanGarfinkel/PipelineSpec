from langchain.agents.structured_output import ToolStrategy
from langgraph.errors import GraphRecursionError
from pipelinespec.models import Diagnosis, Mocks
from singleton_decorator import singleton
from langchain.agents import create_agent
from pipelinespec import log, settings
from pipelinespec.utils import *
from .prompt import DIAGNOSE
from .tools import RunTools
from pathlib import Path
import json

@singleton
class Diagnoser:

    def run(self, run_dir: Path, mocks: Mocks) -> Diagnosis:

        config = json.loads((run_dir / 'config.json').read_text())
        credentials, calls = len(mocks.credentials), len(mocks.calls)
        task = f'Workflow: "{config["workflow"]}"\nTarget job id: "{config["job"]}"\nEvent: {config["context"]["event"]}\n\nThe latest run of this job failed.'
        tools = [*shared_tools.get(), *RunTools(run_dir, mocks).get()]
        agent = create_agent(model.get_llm(), tools=tools, system_prompt=DIAGNOSE, middleware=model.middleware(), response_format=ToolStrategy(Diagnosis))
        messages = [('user', task)]
        recorder, guard = RecordCallbackHandler(str(run_dir.relative_to(settings.file.output) / 'diagnose_agent')), GuardCallbackHandler()

        log(f'{config["workflow"]} / {config["job"]}: diagnosing the failed run...')

        for _ in range(settings.agent.retries):
            try:
                state = agent.invoke({'messages': messages}, config={'recursion_limit': settings.agent.max_steps * 2 + 2, 'callbacks': [recorder, guard]})
            except GraphRecursionError:
                recorder.note({'type': 'limit', 'max_steps': settings.agent.max_steps})
                log(f'{config["workflow"]} / {config["job"]}: the diagnoser reached its limit of {settings.agent.max_steps} tool calls; the failure is treated as not fixable.', style='yellow')

                return Diagnosis(fixable=False, reason=f'The diagnoser reached its limit of {settings.agent.max_steps} tool calls before it answered.')
            except GuardError as error:
                issue = str(error)
                break

            diagnosis = state.get('structured_response')

            if diagnosis is not None:
                log(f'{config["workflow"]} / {config["job"]}: {"fixable" if diagnosis.fixable else "not fixable"}, added {len(mocks.credentials) - credentials} credentials and {len(mocks.calls) - calls} mocked calls. {diagnosis.reason}', style=None if diagnosis.fixable else 'yellow')

                return diagnosis

            issue = 'Text in a reply is not an answer. Give your answer by calling the Diagnosis tool with every field filled in.'

            if recorder.events and recorder.events[-1].get('finish_reason') == 'length':
                issue = f'Your last reply was cut off at the token limit before it made a call. Think less and call the tools. {issue}'

            log(f'The agent stopped before finishing: {issue}', style='yellow')
            messages = [*state['messages'], ('user', issue)]

        recorder.note({'type': 'unfinished', 'issue': issue})
        log(f'{config["workflow"]} / {config["job"]}: the diagnoser did not finish; the failure is treated as not fixable. {issue}', style='yellow')

        return Diagnosis(fixable=False, reason=f'The diagnoser did not finish: {issue}')

diagnoser = Diagnoser()

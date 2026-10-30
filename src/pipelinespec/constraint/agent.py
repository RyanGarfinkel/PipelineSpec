from pipelinespec.models import Constraints, Trigger, Workflow
from langchain_core.tools import BaseTool
from singleton_decorator import singleton
from langchain.agents import create_agent
from pipelinespec import log, settings
from .tools import constraint_tools
from pipelinespec.tools import git
from .prompt import JOB, WORKFLOW
from pipelinespec.utils import *
from typing import Callable
import json

@singleton
class ConstraintAgent:

    def find_workflow_triggers(self, workflow: str) -> list[Trigger]:

        parsed = Workflow.find(settings.repo / '.github' / 'workflows', workflow)
        triggers: list[Trigger] = []
        task = f'Workflow: "{workflow}" ({parsed.path.relative_to(settings.repo)})\n\n{parsed.path.read_text()}'

        def problem(_: RecordCallbackHandler) -> str | None:

            return None if triggers else 'No example is recorded yet. Call add_trigger for each event that triggers the workflow.'

        def save() -> None:

            self.__save(workflow, lambda entry: entry.update(triggers=[trigger.model_dump(mode='json') for trigger in triggers]))

        log(f'Finding how to trigger {workflow}...')
        self.__run('workflow_agent', WORKFLOW, constraint_tools.triggers(triggers), task, problem, save)
        log(f'Found {len(triggers)} ways to trigger {workflow}.')

        return triggers

    def find_job_constraints(self, workflow: str, job: str, events: list[str]) -> Constraints:

        parsed = Workflow.find(settings.repo / '.github' / 'workflows', workflow, job)
        constraints = Constraints(events=events)
        task = f'Workflow: "{workflow}" ({parsed.path.relative_to(settings.repo)})\nTarget job id: "{job}"\nHEAD commit of the repository: {git.head() or "unknown"}\nName of the repository: {git.repository() or "unknown"}\n\n{parsed.excerpt(job)}'

        def problem(recorder: RecordCallbackHandler) -> str | None:

            pending = constraint_tools.pending(constraints)

            if pending:
                return f'These gates use names that have no variable yet: {"; ".join(f"{gate}: {", ".join(names)}" for gate, names in pending.items())}. Declare each with add_variable.'

            if constraints.gates or constraints.unsolved or constraints.constants or any(event.get('name') == 'recorded' for event in recorder.events):
                return None

            return 'Nothing is recorded yet. Text in a reply is not recorded: go through the steps and call add_gate, add_unsolved and add_constant for what you find. If the job has nothing to record, call recorded and stop.'

        def save() -> None:

            self.__save(workflow, lambda entry: entry['jobs'].update({job: constraints.model_dump(mode='json')}))

        log(f'Extracting the conditions of {job} in {workflow}...')
        self.__run('constraint_agent', JOB,[*shared_tools.get(), *constraint_tools.get(constraints)], task, problem, save)
        log(f'Found {len(constraints.gates)} gates, {len(constraints.variables)} variables, {len(constraints.constants)} constants and {len(constraints.unsolved)} unsolved conditions.')

        return constraints

    def __run(self, name: str, prompt: str, tools: list[BaseTool], task: str, problem: Callable[[RecordCallbackHandler], str | None], save: Callable[[], None]) -> None:

        agent = create_agent(model.get_llm(), tools=tools, system_prompt=prompt, middleware=model.middleware())
        messages = [('user', task)]
        recorder, guard = RecordCallbackHandler(name), GuardCallbackHandler()

        for _ in range(settings.agent.retries):
            try:
                state = agent.invoke({'messages': messages}, config={'recursion_limit': settings.agent.max_steps * 2 + 2, 'callbacks': [ProgressCallbackHandler('Constraint Agent'), recorder, guard]})
            finally:
                save()

            issue = problem(recorder)

            if recorder.events and recorder.events[-1].get('finish_reason') == 'length':
                issue = f'Your last reply was cut off at the token limit before it made a call. Think less and call the tools. {issue or "Continue with the steps you have not recorded yet."}'

            if issue is None:
                return

            log(f'The agent stopped before finishing: {issue}', style='yellow')
            messages = [*state['messages'], ('user', issue)]

        raise RuntimeError(f'The agent did not finish its work: {issue}')

    def __save(self, workflow: str, change: Callable[[dict], None]) -> None:

        path = settings.file.output / 'constraints.json'
        path.parent.mkdir(parents=True, exist_ok=True)

        content = json.loads(path.read_text()) if path.exists() else {}
        change(content.setdefault(workflow, {'triggers': [], 'jobs': {}}))
        path.write_text(json.dumps(content, indent=4))

constraint_agent = ConstraintAgent()

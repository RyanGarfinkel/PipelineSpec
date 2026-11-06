from pipelinespec.models import MockedCall, Mocks, Workflow
from langchain_core.tools import BaseTool, tool
from pipelinespec.utils.guard import REJECTED
from pydantic import ValidationError
from pipelinespec import settings
from typing import Literal
from pathlib import Path
import json
import re

CREDENTIAL = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
LOCAL = re.compile(r'localhost|127\.0\.0\.1|\[::1\]|host\.docker\.internal')
MAX_ADDED = 20
MAX_LINE = 300
MAX_BODY = 200

class RunTools:

    def __init__(self, run_dir: Path, mocks: Mocks):

        self.run_dir = run_dir
        self.mocks = mocks
        self.config = json.loads((run_dir / 'config.json').read_text())
        self.result = json.loads((run_dir / 'result.json').read_text())

    def get(self) -> list[BaseTool]:

        @tool(parse_docstring=True)
        def failed_steps() -> str:
            """Show how the latest run of the job ended: the job outcome, the outcome of every step, and the exit code of the steps that failed."""

            return self.__failed_steps()

        @tool(parse_docstring=True)
        def step_source(step: str) -> str:
            """Show how a step is written in the workflow: its name, condition, command or action, inputs and env.

            Args:
                step: The step id, as shown by failed_steps.
            """

            return self.__step_source(step)

        @tool(parse_docstring=True)
        def step_output(step: str, tail: int = 60) -> str:
            """Show the last lines of what a step printed in the latest run, including its errors.

            Args:
                step: The step id, as shown by failed_steps.
                tail: How many of the last lines to show.
            """

            return self.__step_output(step, tail)

        @tool(parse_docstring=True)
        def commands() -> str:
            """List the programs the job ran in the latest run, with their arguments, in order."""

            return self.__commands()

        @tool(parse_docstring=True)
        def traffic(host: str | None = None, failed_only: bool = False) -> str:
            """List the network requests of the latest run, with status, whether they were mocked, and the start of their request and response bodies. Shows the most recent ones.

            Args:
                host: Only the requests to a host containing this text.
                failed_only: Only requests that failed or got an error status (400 or above).
            """

            return self.__traffic(host, failed_only)

        @tool(parse_docstring=True)
        def additions() -> str:
            """Show the credentials and mocks that were already provided or added for the next run."""

            return self.__additions()

        @tool(parse_docstring=True)
        def add_credential(name: str) -> str:
            """Provide a secret for the next run, by name. A fake value is generated; you never see or choose it.

            Args:
                name: The secret name exactly as the workflow writes it after `secrets.`, for example DEPLOY_KEY.
            """

            return self.__add_credential(name)

        @tool(parse_docstring=True)
        def add_mock(method: str, url: str, status: int = 200, json_body: str | None = None, text: str | None = None, headers: dict[str, str] | None = None, failure: Literal['reset', 'timeout', 'unreachable'] | None = None) -> str:
            """Answer a network request with a fixed response in the next run, so the job does not call the real service. A mock for the same method and url replaces the earlier one.

            Args:
                method: The HTTP method, such as GET or PUT.
                url: A pattern for the scheme, host and path without the query, where * matches anything, for example https://api.example.com/*.
                status: The status code to return.
                json_body: The response body as JSON text. Give the shape the caller reads. Leave out for an empty body.
                text: A raw response body that is not JSON. Used instead of json_body.
                headers: Response headers.
                failure: Make the request fail instead: reset drops the connection, timeout stalls and then drops it, unreachable returns 502.
            """

            return self.__add_mock(method, url, status, json_body, text, headers, failure)

        return [failed_steps, step_source, step_output, commands, traffic, additions, add_credential, add_mock]

    def __failed_steps(self) -> str:

        steps = self.result['steps']
        lines = [f'The job {self.config["job"]} ended with: {self.result["outcome"]}.']
        lines += [f'step {step["id"]}: {step["outcome"]}' + (f', exit code {step["exit_code"]}' if step['exit_code'] is not None else '') + f' ({step["name"][:70]!r})' for step in steps]

        if not any(step['outcome'] == 'failure' for step in steps):
            lines.append('No step failed. The job stopped before its steps ran, or in a step that was not reported.')

        return '\n'.join(lines)

    def __step_source(self, step: str) -> str:

        workflow = Workflow.find(settings.repo / '.github' / 'workflows', self.config['workflow'], self.config['job'])
        job = next(job for job in workflow.jobs if job.name == self.config['job'])
        found = next((candidate for candidate in job.steps if candidate.id == step), None)

        if found is None:
            return f'Error: there is no step "{step}". The steps are: {", ".join(candidate.id for candidate in job.steps)}.'

        fields = {'name': found.name, 'if': found.condition, 'uses': found.uses, 'with': found.inputs, 'shell': found.shell, 'env': found.env, 'run': found.run}

        return '\n'.join(f'{key}: {value}' for key, value in fields.items() if value)

    def __step_output(self, step: str, tail: int) -> str:

        lines = []

        for line in (self.run_dir / 'run.jsonl').read_text(errors='replace').splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            ids = entry.get('stepID') or []

            if (entry.get('raw_output') or entry.get('level') == 'error') and entry.get('jobID') == self.config['job'] and ids and ids[0] == step:
                lines += entry.get('msg', '').rstrip('\n').split('\n')

        if not lines:
            return f'No output was recorded for step "{step}".'

        shown = [line[:MAX_LINE] for line in lines[-max(1, min(tail, settings.agent.max_items)):]]

        return f'Last {len(shown)} of {len(lines)} output lines of step {step}:\n' + '\n'.join(shown)

    def __commands(self) -> str:

        if not self.result['commands']:
            return 'No programs were recorded for the job.'

        return '\n'.join(' '.join(command)[:MAX_LINE] for command in self.result['commands'][:settings.agent.max_items])

    def __traffic(self, host: str | None, failed_only: bool) -> str:

        rows = []

        for line in (self.run_dir / 'traffic.jsonl').read_text(errors='replace').splitlines():
            entry = json.loads(line)
            failed = entry['result'] == 'failed' or entry['status'] is None or entry['status'] >= 400

            if (host and host not in entry['host']) or (failed_only and not failed):
                continue

            rows.append(entry)

        if not rows:
            return 'No requests match.'

        shown = rows[-settings.agent.max_items:]
        lines = []

        for entry in shown:
            lines.append(f'{entry["method"]} {entry["scheme"]}://{entry["host"]}{entry["path"][:150]} -> {entry["status"]} ({entry["result"]})')

            for label, body in (('request', entry.get('request_body')), ('response', entry.get('response_body'))):
                if body:
                    lines.append(f'    {label} body: {body[:MAX_BODY]!r}')

        return f'Showing the last {len(shown)} of {len(rows)} matching requests:\n' + '\n'.join(lines)

    def __additions(self) -> str:

        provided = sorted(json.loads((self.run_dir / 'secrets.json').read_text()))
        lines = [f'Credentials provided in the latest run: {", ".join(provided) or "none"}.']
        lines.append(f'Credentials added since: {", ".join(self.mocks.credentials) or "none"}.')
        lines += [f'Mock: {mock.method} {mock.url} -> {mock.failure or mock.status}' for mock in self.mocks.calls]

        return '\n'.join(lines)

    def __add_credential(self, name: str) -> str:

        provided = json.loads((self.run_dir / 'secrets.json').read_text())

        if not CREDENTIAL.match(name):
            return f'{REJECTED} "{name}" is not a valid secret name.'

        if name in self.mocks.credentials:
            return f'{REJECTED} "{name}" was already added for the next run.'

        if name in provided:
            return f'{REJECTED} "{name}" was already provided in this run, so a missing "{name}" is not the cause of this failure.'

        if len(self.mocks.credentials) >= MAX_ADDED:
            return f'{REJECTED} at most {MAX_ADDED} credentials can be added.'

        self.mocks.credentials.append(name)

        return f'Added credential {name}. The next run provides it as secrets.{name}.'

    def __add_mock(self, method: str, url: str, status: int, json_body: str | None, text: str | None, headers: dict[str, str] | None, failure: str | None) -> str:

        try:
            body = json.loads(json_body) if json_body is not None else None
            mock = MockedCall(method=method.upper(), url=url, status=status, headers=headers or {}, body=body, text=text, failure=failure)
        except (json.JSONDecodeError, ValidationError) as problem:
            return f'{REJECTED} the mock is not valid: {problem}'

        if LOCAL.search(mock.url):
            return f'{REJECTED} {mock.url} is local to the job or the sandbox. A server the job starts itself is part of the job, so it cannot be replaced by a mock.'

        if mock in self.mocks.calls:
            return f'{REJECTED} this mock for {mock.method} {mock.url} is already added exactly like this.'

        others = [existing for existing in self.mocks.calls if (existing.method, existing.url) != (mock.method, mock.url)]

        if len(others) >= MAX_ADDED:
            return f'{REJECTED} at most {MAX_ADDED} mocks can be added.'

        replaced = len(others) != len(self.mocks.calls)
        self.mocks.calls = [*others, mock]

        return f'{"Replaced" if replaced else "Added"} the mock for {mock.method} {mock.url}. The next run uses it.'

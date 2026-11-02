from mitmproxy.http import HTTPFlow, Message, Response
from fnmatch import fnmatchcase
from pathlib import Path
import asyncio
import base64
import json
import os

class TrafficLogger:

    def __init__(self):

        run_dir = os.environ.get('RUN_DIR', None)

        if run_dir is None:
            raise ValueError('Traffic logger missing RUN_DIR.')

        self.body_limit = int(os.environ.get('BODY_LIMIT', '2048'))
        self.traffic_file = Path(run_dir) / 'traffic.jsonl'

        with open(Path(run_dir) / 'mocked_calls.json', 'r') as f:
            self.mocks = json.load(f)

        with open(Path(run_dir) / 'secrets.json', 'r') as f:
            self.secrets = json.load(f)

    async def request(self, flow: HTTPFlow) -> None:

        request = flow.request
        url = f'{request.scheme}://{request.pretty_host}{request.path.split("?")[0]}'

        for mock in self.mocks:
            if mock['method'].upper() != request.method or not fnmatchcase(url, mock['url']):
                continue

            flow.metadata['result'] = 'mocked'

            if mock['failure'] == 'timeout':
                await asyncio.sleep(mock['delay'])
                flow.kill()
            elif mock['failure'] == 'reset':
                flow.kill()
            elif mock['failure'] == 'unreachable':
                flow.response = Response.make(502, b'Bad Gateway')
            else:
                flow.response = Response.make(mock['status'], self.__mock_body(mock), mock['headers'])

            return

    def response(self, flow: HTTPFlow) -> None:

        self.__log(flow, flow.metadata.get('result', 'passed'), flow.response.status_code)

    def error(self, flow: HTTPFlow) -> None:

        self.__log(flow, 'failed', None)

    def __mock_body(self, mock: dict) -> bytes:

        if mock['text'] is not None:
            return mock['text'].encode()

        return b'' if mock['body'] is None else json.dumps(mock['body']).encode()

    @staticmethod
    def __marker_forms(value: str) -> list[bytes]:

        forms = [value.encode()]

        for offset, cut in ((0, 0), (1, 2), (2, 3)):
            encoded = base64.b64encode(b'\0' * offset + value.encode()).rstrip(b'=')
            forms.append(encoded[cut:-1])

        return forms

    def __sent_secrets(self, request) -> list[str]:

        parts = [request.pretty_url, *(f'{key}: {value}' for key, value in request.headers.items(multi=True))]
        content = '\n'.join(parts).encode() + (request.raw_content or b'')

        return sorted(name for name, value in self.secrets.items() if any(form in content for form in self.__marker_forms(value)))

    def __body(self, message: Message | None) -> tuple[str | None, int]:

        if message is None:
            return None, 0

        content = message.get_content(strict=False) or b''

        try:
            return content[:self.body_limit].decode(), len(content)
        except UnicodeDecodeError:
            return None, len(content)

    def __log(self, flow: HTTPFlow, result: str, status: int | None) -> None:

        request = flow.request
        request_body, request_size = self.__body(request)
        response_body, response_size = self.__body(flow.response)

        with open(self.traffic_file, 'a') as f:
            f.write(json.dumps({
                'scheme': request.scheme,
                'host': request.pretty_host,
                'port': request.port,
                'method': request.method,
                'path': request.path,
                'headers': list(request.headers.items(multi=True)),
                'secrets': self.__sent_secrets(request),
                'client_time': flow.client_conn.timestamp_start,
                'time': request.timestamp_start,
                'status': status,
                'result': result,
                'request_body': request_body,
                'request_size': request_size,
                'response_headers': list(flow.response.headers.items(multi=True)) if flow.response else [],
                'response_body': response_body,
                'response_size': response_size,
            }) + '\n')

addons = [TrafficLogger()]

from mitmproxy.http import HTTPFlow, Response
from fnmatch import fnmatchcase
from pathlib import Path
import json
import os

class TrafficLogger:

    def __init__(self):

        run_dir = os.environ.get('RUN_DIR', None)

        if run_dir is None:
            raise ValueError('Traffic logger missing RUN_DIR.')

        self.traffic_file = Path(run_dir) / 'traffic.jsonl'

        with open(Path(run_dir) / 'mocked_calls.json', 'r') as f:
            self.mocks = json.load(f)

        with open(Path(run_dir) / 'secrets.json', 'r') as f:
            self.secrets = json.load(f)

    def request(self, flow: HTTPFlow) -> None:

        request = flow.request
        url = f'{request.scheme}://{request.pretty_host}{request.path.split("?")[0]}'

        for mock in self.mocks:
            if mock['method'].upper() == request.method and fnmatchcase(url, mock['url']):
                flow.response = Response.make(mock['status'], json.dumps(mock['body']).encode(), mock['headers'])
                flow.metadata['result'] = 'mocked'
                return

    def response(self, flow: HTTPFlow) -> None:

        self.__log(flow, flow.metadata.get('result', 'passed'), flow.response.status_code)

    def error(self, flow: HTTPFlow) -> None:

        self.__log(flow, 'failed', None)

    def __sent_secrets(self, request) -> list[str]:

        parts = [request.pretty_url, *(f'{key}: {value}' for key, value in request.headers.items(multi=True))]
        content = '\n'.join(parts).encode() + (request.raw_content or b'')

        return sorted(name for name, value in self.secrets.items() if value.encode() in content)

    def __log(self, flow: HTTPFlow, result: str, status: int | None) -> None:

        request = flow.request

        with open(self.traffic_file, 'a') as f:
            f.write(json.dumps({
                'scheme': request.scheme,
                'host': request.pretty_host,
                'port': request.port,
                'method': request.method,
                'path': request.path,
                'headers': list(request.headers.items(multi=True)),
                'secrets': self.__sent_secrets(request),
                'status': status,
                'result': result,
            }) + '\n')

addons = [TrafficLogger()]

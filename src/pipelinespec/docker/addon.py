from mitmproxy.http import HTTPFlow, Response
from pathlib import Path
import json
import os

class TrafficController:

    def __init__(self):

        run_dir_str = os.environ.get('RUN_DIR', None)

        if run_dir_str is None:
            raise ValueError('Network proxy missing RUN_DIR.')
        
        self.run_dir = Path(run_dir_str)

        with open(self.run_dir / 'network_policy.json', 'r') as f:
            policy_data = json.load(f)

        self.network_policy = [{
                'url': item['url'],
                'method': item['method'],
                'status': item['status'],
                'headers': item['headers'],
                'response': item['response']
            } for item in policy_data]

    def request(self, flow: HTTPFlow) -> None:

        url = flow.request.pretty_url
        method = flow.request.method

        mocked = False

        # Mock request or return error

        for mock in self.network_policy:
            if url == mock['url'] and method == mock['method']:
                flow.response = Response.make(
                    status_code=mock['status'],
                    headers=mock['headers'],
                    content=json.dumps(mock['response']).encode('utf-8')
                )
                mocked = True
                break
        
        if not mocked:
            flow.response = Response.make(
                status_code=403,
                content=b'{"error": "Network request blocked by TrafficController."}'
            )

        # Log request and response

        with open(self.run_dir / 'traffic.jsonl', 'a') as f:
            f.write(json.dumps({
                'scheme': flow.request.scheme,
                'host': flow.request.host,
                'port': flow.request.port,
                'method': flow.request.method,
                'path': flow.request.path,
                'headers': dict(flow.request.headers),
                'status': flow.response.status_code,
                'result': 'mocked' if mocked else 'blocked'
            }) + '\n')

addons = [TrafficController()]

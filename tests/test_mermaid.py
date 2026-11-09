from pipelinespec.models import AccessMap
from pipelinespec.core import mermaid
import re

def job(name, needs=(), outcome='success', hosts=()):

    access = {
        'files': [{'path': 'a.txt', 'access': ['read', 'write']}],
        'networks': [{'scheme': 'https', 'host': host, 'port': 443, 'method': 'GET', 'path': '/x', 'headers': [], 'status': 200, 'result': 'passed'} for host in hosts],
        'secrets': ['TOKEN'],
    }

    return {
        'workflow': 'CI', 'name': name, 'events': ['push'], 'needs': list(needs), 'uses': None,
        'gates': [], 'variables': {}, 'unsolved': [],
        'tested': [{'context': {'event': 'push', 'payload.ref': 'main'}, 'reason': 'push: all "conditions" hold', 'outcome': outcome, 'runs': []}],
        'variants': [{'outcome': outcome, 'access': access, 'contexts': [{'event': 'push', 'payload.ref': 'main'}]}],
    }

def test_workflow_event_job_variant_and_access_are_separate_linked_nodes():

    diagram = mermaid.render(AccessMap.model_validate({'repository': 'r', 'jobs': [job('build', hosts=['api.x.com']), job('test', needs=['build'], outcome='failure')]}))

    assert diagram.startswith('flowchart TD\n')
    assert re.search(r'(n\d+)\["<b>CI</b>"\]:::workflow\n(?:.*\n)*?\s+\1 --> (n\d+)\n', diagram)
    assert diagram.count(':::event') == 1
    assert re.search(r'(n\d+) -\.->\|needs\| (n\d+)', diagram)
    assert '<b>success</b><br/>push: all #quot;conditions#quot; hold<br/>payload.ref = main' in diagram
    assert '<b>Files (1)</b><br/>a.txt (rw)' in diagram
    assert '<b>Network (1)</b><br/>GET https://api.x.com/x 200 passed' in diagram
    assert '<b>Secrets (1)</b><br/>used TOKEN' in diagram
    assert ':::success' in diagram and ':::failure' in diagram

def test_a_long_list_is_cut_and_an_empty_one_has_no_node():

    diagram = mermaid.render(AccessMap.model_validate({'repository': 'r', 'jobs': [job('build', hosts=[f'h{index}.com' for index in range(25)])]}))

    assert '<b>Network (25)</b>' in diagram and '+15 more' in diagram

    quiet = job('quiet')
    quiet['variants'][0]['access'] = {}

    assert ':::files' not in mermaid.render(AccessMap.model_validate({'repository': 'r', 'jobs': [quiet]}))

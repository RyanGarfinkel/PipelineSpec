from pipelinespec.models import Context, Job
from unittest.mock import MagicMock, patch
from pipelinespec.tools.act import act
from pipelinespec import settings
from pathlib import Path
import pytest
import json

CERT_PATH = '/opt/hostedtoolcache/pspec/ca.pem'

def run(tmp_path: Path, returncode: int = 0, context: Context | None = None, credentials: dict[str, str] | None = None) -> list[list[str]]:

    settings.trace.mitm_certificate = tmp_path
    job = MagicMock(spec=Job)
    job.path = tmp_path / 'ci.yml'
    job.name = 'build'

    with patch('pipelinespec.tools.act.subprocess.run', return_value=MagicMock(returncode=returncode, stderr='no daemon')) as subprocess_run:
        act.run(job, tmp_path, 8080, context or Context(event='push', payload={}, actor=None), credentials or {}, 'run-id')

    return [call.args[0] for call in subprocess_run.call_args_list]

def test_certificate_reaches_the_toolcache_volume_before_act(tmp_path: Path) -> None:

    install, command = run(tmp_path)

    assert install[:2] == ['docker', 'run']
    assert 'act-toolcache:/opt/hostedtoolcache' in install
    assert install[-1] == CERT_PATH
    assert command[0] == 'act'

def test_clients_trust_the_certificate_in_the_volume(tmp_path: Path) -> None:

    _, command = run(tmp_path)

    for name in ('SSL_CERT_FILE', 'NODE_EXTRA_CA_CERTS', 'REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE', 'GIT_SSL_CAINFO'):
        assert f'{name}={CERT_PATH}' in command

def test_local_traffic_skips_the_proxy(tmp_path: Path) -> None:

    _, command = run(tmp_path)

    for name in ('NO_PROXY', 'no_proxy'):
        assert f'{name}=localhost,127.0.0.1,::1' in command

def test_container_options_mount_nothing(tmp_path: Path) -> None:

    _, command = run(tmp_path)

    assert '-v' not in command[command.index('--container-options') + 1]

def test_event_file_writes_inputs_as_strings_only_on_events_that_have_them() -> None:

    payload = {'inputs': {'update': True, 'count': 2, 'name': 'x'}, 'ref': 'r'}

    assert Context(event='workflow_dispatch', payload=payload).event_file == {'inputs': {'update': 'true', 'count': '2', 'name': 'x'}, 'ref': 'r'}
    assert Context(event='workflow_call', payload=payload).event_file['inputs']['update'] == 'true'
    assert Context(event='pull_request', payload=payload).event_file == {'ref': 'r'}

def test_event_is_a_temporary_file_outside_the_run_directory(tmp_path: Path) -> None:

    settings.trace.mitm_certificate = tmp_path
    job = MagicMock(spec=Job)
    job.path = tmp_path / 'ci.yml'
    job.name = 'build'
    seen = []

    def fake_run(command, **_):

        if command[0] == 'act':
            seen.append(json.loads(Path(command[command.index('-e') + 1]).read_text()))

        return MagicMock(returncode=0)

    with patch('pipelinespec.tools.act.subprocess.run', side_effect=fake_run):
        act.run(job, tmp_path, 8080, Context(event='push', payload={'ref': 'r'}), {}, 'run-id')

    assert seen == [{'ref': 'r'}]
    assert not (tmp_path / 'event.json').exists()

def test_github_token_is_empty_until_it_is_provided(tmp_path: Path) -> None:

    _, empty = run(tmp_path)
    _, fake = run(tmp_path, credentials={'GITHUB_TOKEN': 'pspec-1'})

    assert 'GITHUB_TOKEN=' in empty and '--action-offline-mode' not in empty
    assert 'GITHUB_TOKEN=pspec-1' in fake and 'GITHUB_TOKEN=' not in fake and '--action-offline-mode' in fake

def test_failed_install_stops_the_run(tmp_path: Path) -> None:

    with pytest.raises(RuntimeError, match='no daemon'):
        run(tmp_path, returncode=1)

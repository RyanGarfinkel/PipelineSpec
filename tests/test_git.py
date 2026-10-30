from pipelinespec.tools import git
from pipelinespec import settings
import subprocess
import pytest

@pytest.mark.parametrize('url', [
    'https://github.com/octo/project.git',
    'https://github.com/octo/project',
    'git@github.com:octo/project.git',
    'ssh://git@github.com/octo/project.git',
])
def test_repository(tmp_path, monkeypatch, url):

    subprocess.run(['git', '-C', str(tmp_path), 'init', '-q'], check=True)
    subprocess.run(['git', '-C', str(tmp_path), 'remote', 'add', 'origin', url], check=True)
    monkeypatch.setattr(settings, 'repo', tmp_path)

    assert git.repository() == 'octo/project'

def test_repository_without_a_remote(tmp_path, monkeypatch):

    subprocess.run(['git', '-C', str(tmp_path), 'init', '-q'], check=True)
    monkeypatch.setattr(settings, 'repo', tmp_path)

    assert git.repository() is None

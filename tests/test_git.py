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

def commit(path, message):

    subprocess.run(['git', '-C', str(path), '-c', 'user.email=a@b.c', '-c', 'user.name=a', 'commit', '-q', '--allow-empty', '-m', message], check=True)

def test_parent_is_none_until_head_has_one(tmp_path, monkeypatch):

    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    monkeypatch.setattr(settings, 'repo', tmp_path)

    commit(tmp_path, 'first')
    first = git.head()

    assert first is not None and git.parent() is None

    commit(tmp_path, 'second')

    assert git.parent() == first and git.head() != first

from pipelinespec.utils.tools import shared_tools
from pipelinespec import settings
from unittest.mock import patch
from pathlib import Path
import pytest

@pytest.fixture
def tools(tmp_path):

    root = tmp_path.resolve() / 'repo'
    outside = tmp_path.resolve() / 'outside'

    for path, text in {
        '.github/workflows/ci.yml': 'name: CI\non: push\n',
        'scripts/deploy.sh': '#!/bin/sh\necho "deploy $GITHUB_REF"\nexit 0\n',
        '.git/config': 'GITHUB_REF in git\n',
        'big.txt': ''.join(f'line {number}\n' for number in range(1, 11)),
    }.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)

    outside.mkdir()
    (outside / 'secret.txt').write_text('GITHUB_REF outside\n')
    (root / 'link.txt').symlink_to(outside / 'secret.txt')
    (root / 'linkdir').symlink_to(outside)

    with patch.object(settings, 'repo', root):
        yield {tool.name: tool for tool in shared_tools.get()}

def test_glob(tools):

    glob = tools['glob']

    assert glob.invoke({'pattern': '.github/workflows/*.yml'}) == '.github/workflows/ci.yml'
    assert glob.invoke({'pattern': 'scripts/../.github/workflows/*.yml'}) == '.github/workflows/ci.yml'

    for pattern in ('', '.', './'):
        assert sorted(glob.invoke({'pattern': pattern}).splitlines()) == ['.github/', 'big.txt', 'scripts/']

    everything = glob.invoke({'pattern': '**/*'}).splitlines()

    assert 'scripts/deploy.sh' in everything
    assert not [path for path in everything if '.git' in Path(path).parts or path.startswith('link')]

    assert glob.invoke({'pattern': 'nothing/*.zzz'}) == 'No matches for "nothing/*.zzz".'
    assert glob.invoke({'pattern': '.git/*'}) == 'Blocked: Unable to access ".git/*".'

    for pattern in ('../*', 'scripts/../../*', '*/../../outside/*', '/etc/*', 'linkdir/*'):
        assert glob.invoke({'pattern': pattern}) == f'Blocked: "{pattern}" is outside the repository.'

    with patch.object(settings.agent, 'max_items', 2):
        assert len(glob.invoke({'pattern': '**/*'}).splitlines()) == 3

def test_grep(tools):

    grep = tools['grep']

    assert grep.invoke({'pattern': 'github_ref', 'path': 'scripts/deploy.sh'}) == '2: echo "deploy $GITHUB_REF"'
    assert grep.invoke({'pattern': 'nothing', 'path': 'scripts/deploy.sh'}) == 'No matches.'
    assert grep.invoke({'pattern': 'line', 'path': './big.txt'}) == grep.invoke({'pattern': 'line', 'path': 'big.txt'})
    assert grep.invoke({'pattern': '(unclosed', 'path': 'big.txt'}).startswith('Error: invalid regular expression')

    assert grep.invoke({'pattern': 'x', 'path': 'scripts'}) == 'Error: grep only searches a single file; use glob to list the files in a directory.'
    assert grep.invoke({'pattern': 'x', 'path': 'missing.txt'}) == 'Error: "missing.txt" does not exist.'
    assert grep.invoke({'pattern': 'x', 'path': '.git/config'}) == 'Blocked: Unable to access ".git/config".'

    for path in ('link.txt', 'linkdir/secret.txt', '../outside/secret.txt', '/etc/passwd', str(settings.repo / 'big.txt')):
        assert grep.invoke({'pattern': 'x', 'path': path}) == f'Blocked: "{path}" is outside the repository.'

    with patch.object(settings.agent, 'max_items', 3):
        result = grep.invoke({'pattern': 'line', 'path': 'big.txt'}).splitlines()

        assert result == ['1: line 1', '2: line 2', '3: line 3', '(stopped after 3 matches; 7 more matches truncated)']

def test_chunk(tools):

    chunk = tools['chunk']

    assert chunk.invoke({'path': 'big.txt', 'start': 2, 'end': 3}) == '2: line 2\n3: line 3'
    assert chunk.invoke({'path': 'big.txt', 'start': 10, 'end': 10}) == '10: line 10\n(end of file)'
    assert chunk.invoke({'path': 'scripts/deploy.sh'}) == '1: #!/bin/sh\n2: echo "deploy $GITHUB_REF"\n3: exit 0\n(end of file)'

    with patch.object(settings.agent, 'max_items', 3):
        assert chunk.invoke({'path': 'big.txt'}) == '1: line 1\n2: line 2\n3: line 3'
        assert chunk.invoke({'path': 'big.txt', 'start': 1, 'end': 4}) == 'Error: too many lines requested (4 > 3).'

    assert chunk.invoke({'path': 'big.txt', 'start': 0}) == 'Error: start (0) must be at least 1.'
    assert chunk.invoke({'path': 'big.txt', 'start': 5, 'end': 2}) == 'Error: end (2) is before start (5).'
    assert chunk.invoke({'path': 'big.txt', 'start': 11}) == 'Error: "big.txt" has only 10 lines.'
    assert chunk.invoke({'path': 'scripts'}) == 'Error: chunk only reads a single file; use glob to list the files in a directory.'
    assert chunk.invoke({'path': 'missing.txt'}) == 'Error: "missing.txt" does not exist.'
    assert chunk.invoke({'path': '.git/config'}) == 'Blocked: Unable to access ".git/config".'

    for path in ('link.txt', '../outside/secret.txt', '/etc/passwd'):
        assert chunk.invoke({'path': path}) == f'Blocked: "{path}" is outside the repository.'

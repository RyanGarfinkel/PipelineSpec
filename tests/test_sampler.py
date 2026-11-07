from importlib import import_module
import subprocess
import pytest
import json

WORKFLOW = '''
name: CI
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets.NPM_TOKEN }} ${{ secrets.GITHUB_TOKEN }}
  deploy:
    runs-on: ubuntu-latest
    steps:
      - run: echo ${{ secrets['DEPLOY_KEY'] }} ${{ secrets.NPM_TOKEN }}
'''

def repository(root, name, files):

    path = root / name
    path.mkdir(parents=True)

    for relative, content in files.items():
        target = path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if isinstance(content, bytes) else content.encode())

    for command in (['init', '--quiet'], ['add', '.'], ['-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '--quiet', '-m', 'init']):
        subprocess.run(['git', '-C', str(path), *command], check=True)

    return {'name': name, 'full_name': f'owner/{name}', 'clone_url': path.as_uri(), 'html_url': f'https://github.com/owner/{name}', 'stargazers_count': 1500, 'forks_count': 40, 'topics': ['ci', 'tools'], 'language': 'Python'}

@pytest.fixture
def sources(tmp_path, monkeypatch):

    module = import_module('pipelinespec.cli.sample')
    found = [
        repository(tmp_path / 'sources', 'empty', {'README.md': 'no workflows\n'}),
        repository(tmp_path / 'sources', 'app', {'.github/workflows/ci.yml': WORKFLOW, 'main.py': 'a\nb\nc', 'logo.png': b'\x89PNG\0\0data\n'}),
        repository(tmp_path / 'sources', 'lib', {'.github/workflows/ci.yml': WORKFLOW, 'lib.py': 'x\n'}),
    ]

    class Search:

        def search(self, page, _):

            return found if page == 1 else []

        def languages(self, name):

            assert name.startswith('owner/')

            return ['Python', 'Shell']

    monkeypatch.setattr(module, 'github', Search())

    return module

def test_sampling_measures_each_repository_and_removes_its_clone(sources, tmp_path):

    output = tmp_path / 'out'
    samples = sources.sample_repositories(2, 1, output, False)

    assert [sample.name for sample in samples] == ['app', 'lib']

    app = samples[0]
    assert (app.workflows, app.jobs, app.files) == (1, 2, 3)
    assert app.lines == WORKFLOW.count('\n') + 3
    assert len(app.commit) == 40 and app.commit_date.tzinfo is not None
    assert (app.stars, app.forks, app.topics, app.primary_language, app.languages) == (1500, 40, ['ci', 'tools'], 'Python', ['Python', 'Shell'])
    assert list((output / 'repositories').iterdir()) == []

def test_an_existing_directory_with_the_repository_name_is_left_alone(sources, tmp_path):

    output = tmp_path / 'out'
    kept = output / 'repositories' / 'app'
    kept.mkdir(parents=True)
    (kept / 'mine.txt').write_text('keep')

    samples = sources.sample_repositories(1, 1, output, False)

    assert [sample.name for sample in samples] == ['lib']
    assert (kept / 'mine.txt').read_text() == 'keep'
    assert sorted(path.name for path in (output / 'repositories').iterdir()) == ['app']

def test_a_repository_with_an_excluded_topic_is_never_cloned(sources, tmp_path, monkeypatch):

    found = sources.github.search(1, 100)
    found[1]['topics'] = ['python', 'interview-preparation']
    cloned = []
    clone = sources.git.clone

    monkeypatch.setattr(sources.git, 'clone', lambda url, destination: cloned.append(url) or clone(url, destination))

    samples = sources.sample_repositories(1, 1, tmp_path / 'out', False)

    assert [sample.name for sample in samples] == ['lib']
    assert not any(url.endswith('/app') for url in cloned)

def test_threads_keep_the_search_order_and_stop_at_n(sources, tmp_path):

    samples = sources.sample_repositories(1, 3, tmp_path / 'out', False)

    assert [sample.name for sample in samples] == ['app']

def test_the_manifest_is_written_as_repositories_are_sampled(sources, tmp_path, monkeypatch):

    output = tmp_path / 'out'
    written = []
    save = sources.save_manifest

    def recorded(samples, directory):

        written.append(len(samples))

        return save(samples, directory)

    monkeypatch.setattr(sources, 'save_manifest', recorded)
    sources.sample_repositories(2, 1, output, False)
    [app, lib] = json.loads((output / 'manifest.json').read_text())

    assert written == [0, 1, 2]
    assert set(app) == {'name', 'clone_url', 'commit', 'commit_date', 'stars', 'forks', 'topics', 'primary_language', 'languages', 'workflows', 'jobs', 'files', 'lines'}
    assert lib['name'] == 'lib'

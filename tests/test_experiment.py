from pipelinespec.models import Sample
from click.testing import CliRunner
from importlib import import_module
from types import SimpleNamespace
import subprocess
import pytest
import click
import json

def sample_of(name, clone_url='u', commit='c', stars=1):

    return Sample(name=name, clone_url=clone_url, commit=commit, commit_date='2026-01-01T00:00:00+00:00', stars=stars, forks=0, topics=[], primary_language=None, languages=[], workflows=1, jobs=1, files=1, lines=1)

def source(tmp_path):

    path = tmp_path / 'source'
    path.mkdir()
    (path / 'a.txt').write_text('first\n')

    for command in (['init', '--quiet'], ['add', '.'], ['-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '--quiet', '-m', 'one']):
        subprocess.run(['git', '-C', str(path), *command], check=True)

    commit = subprocess.run(['git', '-C', str(path), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True).stdout.strip()
    (path / 'a.txt').write_text('second\n')
    subprocess.run(['git', '-C', str(path), '-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '--quiet', '-am', 'two'], check=True)

    return sample_of('repo', path.as_uri(), commit)

def test_the_manifest_is_read_and_cut_to_n(tmp_path):

    module = import_module('pipelinespec.cli.experiment')
    samples = [sample_of(f'r{index}', stars=index) for index in range(3)]
    (tmp_path / 'manifest.json').write_text(json.dumps([sample.model_dump(mode='json') for sample in samples]))

    assert module.load_samples(2, tmp_path) == samples[:2]

def test_a_missing_manifest_is_an_error(tmp_path):

    module = import_module('pipelinespec.cli.experiment')

    with pytest.raises(click.UsageError, match='Run sample first'):
        module.load_samples(5, tmp_path)

def test_the_flags_are_checked_before_anything_runs(tmp_path, monkeypatch):

    module = import_module('pipelinespec.cli.experiment')
    monkeypatch.setenv('CERTIFICATE', str(tmp_path))
    runner = CliRunner()

    assert 'cannot be used together' in runner.invoke(module.main, ['-m', 'x', '-o', str(tmp_path), '--constraints-only', '--trace-only']).output
    assert '-k has no effect' in runner.invoke(module.main, ['-m', 'x', '-o', str(tmp_path), '--trace-only', '-k', '3']).output
    assert 'Run sample first' in runner.invoke(module.main, ['-m', 'x', '-o', str(tmp_path), '--trace-only']).output
    assert 'Run sample first' in runner.invoke(module.main, ['-m', 'x', '-o', str(tmp_path)]).output

    monkeypatch.delenv('CERTIFICATE')

    assert 'CERTIFICATE is not set' in runner.invoke(module.main, ['-m', 'x', '-o', str(tmp_path)]).output
    assert 'Run sample first' in runner.invoke(module.main, ['-m', 'x', '-o', str(tmp_path), '--constraints-only']).output

def fake_runs(module, monkeypatch, tmp_path, codes):

    seen = []

    def run(command, **_):

        repo = command[command.index('-r') + 1]
        seen.append((command[3:], (tmp_path / repo / 'a.txt').read_text()))

        return SimpleNamespace(returncode=codes[len(seen) - 1])

    monkeypatch.setattr(module, 'subprocess', SimpleNamespace(run=run, STDOUT=subprocess.STDOUT))

    return seen

def test_k_constraint_runs_then_one_trace_of_the_first_on_the_manifest_commit(tmp_path, monkeypatch):

    module = import_module('pipelinespec.cli.experiment')
    sample = source(tmp_path)
    seen = fake_runs(module, monkeypatch, tmp_path, [0, 0])
    results = tmp_path / 'out' / 'results' / 'gpt-x' / 'repo'

    assert module.run_pipeline(sample, 'gpt-x', 3, tmp_path / 'out', True, True, tmp_path / 'journal.log', 'header\n')

    [(constraints, first), (tracing, second)] = seen
    assert first == second == 'first\n'
    assert constraints[2:] == ['-o', str(results), '-m', 'gpt-x', '--constraints-only', '-n', '3']
    assert tracing[2:] == ['-o', str(results), '-m', 'gpt-x', '--trace-only', '--constraints', str(results / 'constraints_1.json')]
    assert list((tmp_path / 'out' / 'repositories').iterdir()) == []
    assert (results / 'terminal.log').read_text().startswith(f'header\nrepository: repo at {sample.commit}\n')
    assert 'repo: done' in (tmp_path / 'journal.log').read_text()

def test_the_experiment_writes_its_parameters_to_its_terminal_log(tmp_path, monkeypatch):

    module = import_module('pipelinespec.cli.experiment')
    (tmp_path / 'manifest.json').write_text(json.dumps([sample_of('repo').model_dump(mode='json')]))
    monkeypatch.setattr(module, 'run_pipeline', lambda *arguments: True)

    result = CliRunner().invoke(module.main, ['-m', 'gpt-x', '-k', '3', '-o', str(tmp_path), '--constraints-only'])
    journal = (tmp_path / 'terminal.log').read_text()

    assert result.exit_code == 0
    assert '===== experiment started' in journal and '  model: gpt-x' in journal and '  constraint runs (-k): 3' in journal
    assert '1 of 1 repositories finished' in journal

def test_one_constraint_run_traces_constraints_json(tmp_path, monkeypatch):

    module = import_module('pipelinespec.cli.experiment')
    seen = fake_runs(module, monkeypatch, tmp_path, [0, 0])

    assert module.run_pipeline(source(tmp_path), 'gpt-x', 1, tmp_path / 'out', True, True, tmp_path / 'journal.log', 'header\n')
    assert seen[1][0][-1] == str(tmp_path / 'out' / 'results' / 'gpt-x' / 'repo' / 'constraints.json')

def test_a_failed_constraint_run_skips_tracing(tmp_path, monkeypatch):

    module = import_module('pipelinespec.cli.experiment')
    seen = fake_runs(module, monkeypatch, tmp_path, [1])

    assert not module.run_pipeline(source(tmp_path), 'gpt-x', 2, tmp_path / 'out', True, True, tmp_path / 'journal.log', 'header\n')
    assert len(seen) == 1

def test_constraints_only_skips_tracing(tmp_path, monkeypatch):

    module = import_module('pipelinespec.cli.experiment')
    seen = fake_runs(module, monkeypatch, tmp_path, [0])

    assert module.run_pipeline(source(tmp_path), 'gpt-x', 2, tmp_path / 'out', True, False, tmp_path / 'journal.log', 'header\n')
    assert [arguments[-3:] for arguments, _ in seen] == [['--constraints-only', '-n', '2']]

def test_trace_only_traces_the_saved_constraints(tmp_path, monkeypatch):

    module = import_module('pipelinespec.cli.experiment')
    seen = fake_runs(module, monkeypatch, tmp_path, [0])
    results = tmp_path / 'out' / 'results' / 'gpt-x' / 'repo'
    results.mkdir(parents=True)
    (results / 'constraints_1.json').write_text('{}')
    (results / 'terminal.log').write_text('earlier\n')

    assert module.run_pipeline(source(tmp_path), 'gpt-x', 1, tmp_path / 'out', False, True, tmp_path / 'journal.log', 'header\n')
    assert [arguments[-3:] for arguments, _ in seen] == [['--trace-only', '--constraints', str(results / 'constraints_1.json')]]
    assert (results / 'terminal.log').read_text().startswith('earlier\nheader\n')

def test_trace_only_without_saved_constraints_clones_nothing(tmp_path, monkeypatch):

    module = import_module('pipelinespec.cli.experiment')
    seen = fake_runs(module, monkeypatch, tmp_path, [])

    assert not module.run_pipeline(source(tmp_path), 'gpt-x', 1, tmp_path / 'out', False, True, tmp_path / 'journal.log', 'header\n')
    assert seen == [] and not (tmp_path / 'out' / 'repositories').exists()

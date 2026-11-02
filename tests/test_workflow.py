from pipelinespec.models import Workflow

def write(directory, name, job):

    (directory / f'{name}.yml').write_text(f'name: {name}\non: push\njobs:\n  j:\n{job}')

STEPS = '    runs-on: ubuntu-latest\n    steps:\n      - run: echo\n'

def workflows(tmp_path):

    directory = tmp_path / '.github' / 'workflows'
    directory.mkdir(parents=True)

    return directory

def names(directory):

    return [workflow.name for workflow in Workflow.find_all(directory)]

def test_job_yaml_is_only_the_job_with_file_line_numbers(tmp_path):

    directory = workflows(tmp_path)
    (directory / 'w.yml').write_text('name: W\non: push\nenv:\n  K: v\njobs:\n  a:\n    runs-on: x\n  b:\n    runs-on: y\n')

    assert Workflow.find_all(directory)[0].get_job_yaml('b') == '5\tjobs:\n8\t  b:\n9\t    runs-on: y'

def test_a_called_workflow_comes_before_its_caller(tmp_path):

    directory = workflows(tmp_path)
    write(directory, 'a', '    uses: ./.github/workflows/m.yml\n')
    write(directory, 'm', '    uses: ./.github/workflows/z.yml\n')
    write(directory, 'z', STEPS)
    write(directory, 'b', STEPS)

    assert names(directory) == ['z', 'm', 'a', 'b']

def test_a_remote_workflow_and_a_cycle_do_not_break_the_order(tmp_path):

    directory = workflows(tmp_path)
    write(directory, 'a', '    uses: ./.github/workflows/b.yml\n')
    write(directory, 'b', '    uses: ./.github/workflows/a.yml\n')
    write(directory, 'c', '    uses: octo/repo/.github/workflows/x.yml@main\n')

    assert names(directory) == ['b', 'a', 'c']

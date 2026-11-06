from pipelinespec.tools.events import _EventParser

def feed(parser, *lines):

    for line in lines:
        parser.feed(line)

def test_access_is_attributed_to_the_job():

    parser = _EventParser('/work', {'TOKEN': 'pspec-1'}, set())

    feed(
        parser,
        'env pid=10 ns=1 GITHUB_WORKFLOW=CI',
        'env pid=10 ns=1 GITHUB_JOB=build',
        'env pid=10 ns=1 GITHUB_ACTION=first',
        'exec pid=10 ppid=1 ns=1 comm=<bash> /usr/bin/bash',
        'open pid=11 ppid=10 ns=1 comm=<cat> flags=0 dfd=-100 fd=3 a.txt',
        'env pid=20 ns=1 GITHUB_WORKFLOW=CI',
        'env pid=20 ns=1 GITHUB_JOB=build',
        'env pid=20 ns=1 GITHUB_ACTION=second',
        'arg pid=20 ns=1 n=0 curl',
        'arg pid=20 ns=1 n=1 pspec-1',
        'exec pid=20 ppid=1 ns=1 comm=<curl> /usr/bin/curl',
        'env pid=30 ns=2 GITHUB_WORKFLOW=CI',
        'env pid=30 ns=2 GITHUB_JOB=test',
        'open pid=30 ppid=1 ns=2 comm=<cat> flags=577 dfd=-100 fd=3 /tmp/out',
        'open pid=40 ppid=1 ns=2 comm=<runc> flags=0 dfd=-100 fd=3 /proc/self/maps',
    )

    found = {(event.workflow, event.job, event.path, event.kind) for event in parser.files.values()}

    assert ('CI', 'build', '/work/a.txt', 'read') in found
    assert ('CI', 'build', '/usr/bin/curl', 'execute') in found
    assert ('CI', 'test', '/tmp/out', 'write') in found
    assert ('_', '_', '/proc/self/maps', 'read') in found
    assert parser.markers == {('CI', 'build'): {'TOKEN'}}

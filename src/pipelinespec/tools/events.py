from pipelinespec.models import ConnectionEvent, FileEvent, Parsed, SocketEvent
from singleton_decorator import singleton
from dataclasses import dataclass, field
from pipelinespec.utils import slug
from pathlib import Path
import logging as log
import ipaddress
import os
import re

Key = tuple[str, str]

MARKER = 'PSPEC_RUN'
CWD = -100
WRITE_FLAGS = 0o1 | 0o2 | 0o100 | 0o1000 | 0o2000
IDENTITY = ('GITHUB_WORKFLOW', 'GITHUB_JOB')

OPEN = re.compile(r'open pid=(\d+) ppid=(\d+) comm=.*? flags=(\d+)(?: dfd=(-?\d+))?(?: fd=(-?\d+))? (.*)')
PATH = re.compile(r'(?:stat|access|readlink|write|chdir) pid=(\d+) ppid=(\d+) comm=.*? dfd=(-?\d+) (.*)')
EXEC = re.compile(r'exec pid=(\d+) ppid=(\d+) comm=.*? ((?:\.{0,2}/).*)')
EXEC_BARE = re.compile(r'exec pid=(\d+) ppid=(\d+) comm=\S+ (.*)')
ARG = re.compile(r'arg pid=(\d+) n=(\d+) (.*)')
ENV = re.compile(r'env pid=(\d+) (\w+)=(.*)')
CONN = re.compile(r'conn pid=(\d+) ppid=(\d+) comm=.*? (\d+\.\d+\.\d+\.\d+):(\d+)')
CONN6 = re.compile(r'conn6 pid=(\d+) ppid=(\d+) comm=.*? hi=([0-9a-fA-F]+) lo=([0-9a-fA-F]+) port=(\d+)')
SOCK = re.compile(r'sock pid=(\d+) ppid=(\d+) sport=(\d+) dst=\[?([^\]]*?)\]?:(\d+) t=([\d.]+)')
NAMESPACE = re.compile(r'(\w+ pid=\d+(?: ppid=\d+)?) ns=(\d+)')
MARKED = re.compile(r'env pid=\d+ ns=(\d+) ' + MARKER + r'=(.*)')

@dataclass
class _Process:

    cwd: str
    adopted: bool = False
    fds: dict[int, str] = field(default_factory=dict)
    identity: dict[str, str] = field(default_factory=dict)
    args: list[str] = field(default_factory=list)

class _EventParser:

    def __init__(self, root: str, secrets: dict[str, str], namespaces: set[int]):

        self.root = root
        self.secrets = secrets
        self.namespaces = namespaces
        self.execs = 0
        self.bare = 0
        self.table: dict[int, _Process] = {}
        self.files: dict[tuple, FileEvent] = {}
        self.connections: dict[tuple, ConnectionEvent] = {}
        self.sockets: list[SocketEvent] = []
        self.markers: dict[Key, set[str]] = {}
        self.clock = 0.0
        self.routes = {
            'open': ((OPEN, self.__open),),
            'stat': ((PATH, self.__touch),),
            'access': ((PATH, self.__touch),),
            'readlink': ((PATH, self.__touch),),
            'write': ((PATH, self.__touch),),
            'chdir': ((PATH, self.__touch),),
            'exec': ((EXEC, self.__exec), (EXEC_BARE, self.__exec)),
            'arg': ((ARG, self.__arg),),
            'env': ((ENV, self.__env),),
            'conn': ((CONN, self.__conn),),
            'conn6': ((CONN6, self.__conn6),),
            'sock': ((SOCK, self.__sock),),
        }

    def feed(self, line: str) -> None:

        line = self.__scope(line)
        if line is None:
            return

        name = line.partition(' ')[0]
        routes = self.routes.get(name)
        if routes is None:
            return

        for pattern, handler in routes:
            match = pattern.match(line)
            if match is not None:
                handler(name, *match.groups())
                return

    def __scope(self, line: str) -> str | None:

        scoped = NAMESPACE.match(line)
        if scoped is None:
            return line

        if self.namespaces and int(scoped[2]) not in self.namespaces:
            return None

        return scoped[1] + line[scoped.end():]

    def __process(self, pid: int, ppid: int | None = None) -> _Process:

        proc = self.table.get(pid)
        if proc is None:
            proc = self.table[pid] = _Process(self.root)

        if ppid is None or proc.adopted:
            return proc

        proc.adopted = True
        parent = self.table.get(ppid)
        if parent is None:
            return proc

        proc.cwd = parent.cwd
        proc.fds = dict(parent.fds)

        for name, value in parent.identity.items():
            proc.identity.setdefault(name, value)

        return proc

    def __key(self, proc: _Process) -> Key:

        workflow, job = (proc.identity.get(name, '') for name in IDENTITY)

        return slug(workflow), slug(job)

    def __resolve(self, proc: _Process, dfd: int, path: str) -> str:

        if path.startswith('/'):
            return path

        base = proc.cwd if dfd == CWD else proc.fds.get(dfd)

        return path if base is None else os.path.normpath(os.path.join(base, path))

    def __add(self, pid: int, proc: _Process, path: str, kind: str, argv: tuple[str, ...] = ()) -> None:

        self.clock += 1
        key = self.__key(proc)
        identity = (*key, pid, path, kind, argv)

        if identity not in self.files:
            self.files[identity] = FileEvent(workflow=key[0], job=key[1], pid=pid, time=self.clock, path=path, kind=kind, argv=argv)

    def __open(self, _: str, pid: str, ppid: str, flags: str, dfd: str | None, fd: str | None, path: str) -> None:

        proc = self.__process(int(pid), int(ppid))
        path = self.__resolve(proc, int(dfd) if dfd else CWD, path)

        if fd and int(fd) >= 0:
            proc.fds[int(fd)] = path

        self.__add(int(pid), proc, path, 'write' if int(flags) & WRITE_FLAGS else 'read')

    def __touch(self, call: str, pid: str, ppid: str, dfd: str, path: str) -> None:

        proc = self.__process(int(pid), int(ppid))
        path = self.__resolve(proc, int(dfd), path)

        if call == 'chdir':
            proc.cwd = path
            return

        self.__add(int(pid), proc, path, 'write' if call == 'write' else 'read')

    def __arg(self, _: str, pid: str, index: str, value: str) -> None:

        proc = self.__process(int(pid))

        if int(index) == 0:
            proc.args = []

        proc.args.append(value)

    def __env(self, _: str, pid: str, name: str, value: str) -> None:

        proc = self.__process(int(pid))

        if name in IDENTITY:
            proc.identity[name] = value

    def __exec(self, _: str, pid: str, ppid: str, filename: str) -> None:

        proc = self.__process(int(pid), int(ppid))
        argv = tuple(proc.args)
        proc.args = []
        self.execs += 1
        self.bare += not argv

        path = self.__resolve(proc, CWD, filename)
        self.__add(int(pid), proc, path, 'execute', argv)

        joined = '\0'.join(argv)
        found = {name for name, value in self.secrets.items() if value in joined}
        if found:
            self.markers.setdefault(self.__key(proc), set()).update(found)

    def __conn(self, _: str, pid: str, ppid: str, address: str, port: str) -> None:

        self.__connect(int(pid), int(ppid), address, int(port))

    def __conn6(self, _: str, pid: str, ppid: str, hi: str, lo: str, port: str) -> None:

        raw = int(hi, 16).to_bytes(8, 'little') + int(lo, 16).to_bytes(8, 'little')
        self.__connect(int(pid), int(ppid), str(ipaddress.IPv6Address(raw)), int(port))

    def __sock(self, _: str, pid: str, ppid: str, source_port: str, address: str, port: str, time: str) -> None:

        key = self.__key(self.__process(int(pid), int(ppid)))
        self.sockets.append(SocketEvent(workflow=key[0], job=key[1], pid=int(pid), time=float(time), source_port=int(source_port), address=address, port=int(port)))

    def __connect(self, pid: int, ppid: int, address: str, port: int) -> None:

        proc = self.__process(pid, ppid)
        key = self.__key(proc)
        identity = (*key, pid, address, port)
        self.clock += 1

        if identity not in self.connections:
            self.connections[identity] = ConnectionEvent(workflow=key[0], job=key[1], pid=pid, time=self.clock, address=address, port=port)

@singleton
class Events:

    def parse(self, run_dir: Path, root: str, secrets: dict[str, str], run: str) -> Parsed:

        with open(run_dir / 'ebpf.txt', 'r', errors='replace') as f:
            namespaces = set()
            for line in f:
                marked = MARKED.match(line.rstrip('\n'))
                if marked is not None and marked[2] == run:
                    namespaces.add(int(marked[1]))

        if not namespaces:
            log.warning(f'No process of run {run} carried its marker; events of other containers are not filtered out.')

        parser = _EventParser(root, secrets, namespaces)

        with open(run_dir / 'ebpf.txt', 'r', errors='replace') as f:
            for line in f:
                parser.feed(line.rstrip('\n'))

        if parser.bare:
            log.warning(f'{parser.bare} of {parser.execs} executed programs have no argument lines; their commands and argv-based secret detection are incomplete.')

        return Parsed(
            files=list(parser.files.values()),
            connections=list(parser.connections.values()),
            sockets=parser.sockets,
            markers={key: frozenset(names) for key, names in parser.markers.items()},
        )

events = Events()

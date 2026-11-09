from pipelinespec.models import AccessMap, AccessVariant, JobNode, Tested
from singleton_decorator import singleton

MAX_LISTED = 10
STYLES = {
    'workflow': 'fill:#cfe2ff,stroke:#0d6efd',
    'event': 'fill:#e0cffc,stroke:#6f42c1',
    'job': 'fill:#ffffff,stroke:#212529',
    'success': 'fill:#d4edda,stroke:#28a745',
    'failure': 'fill:#f8d7da,stroke:#dc3545',
    'skipped': 'fill:#e2e3e5,stroke:#6c757d',
    'unknown': 'fill:#fff3cd,stroke:#ffc107',
    'files': 'fill:#f8f9fa,stroke:#6c757d',
    'network': 'fill:#d1ecf1,stroke:#17a2b8',
    'secrets': 'fill:#fde2c8,stroke:#fd7e14',
}
KINDS = {'read': 'r', 'write': 'w', 'execute': 'x'}

@singleton
class Mermaid:

    def render(self, access_map: AccessMap) -> str:

        lines = ['flowchart TD']
        count = 0

        def node(text: str, style: str) -> str:

            nonlocal count
            count += 1
            lines.append(f'    n{count}["{text}"]:::{style}')

            return f'n{count}'

        workflows: dict[str, list[JobNode]] = {}
        jobs: dict[tuple[str, str], str] = {}

        for job in access_map.jobs:
            workflows.setdefault(job.workflow, []).append(job)

        for workflow, members in workflows.items():
            workflow_id = node(f'<b>{self.__text(workflow)}</b>', 'workflow')
            events: dict[str, str] = {}

            for job in members:
                jobs[(workflow, job.name)] = node(self.__job(job), 'job')

                for event in job.events:
                    if event not in events:
                        events[event] = node(self.__text(event), 'event')
                        lines.append(f'    {workflow_id} --> {events[event]}')

                    lines.append(f'    {events[event]} --> {jobs[(workflow, job.name)]}')

        for job in access_map.jobs:
            job_id = jobs[(job.workflow, job.name)]
            tests = {tuple(sorted(test.context.items())): test for test in job.tested}

            for needed in job.needs:
                if (job.workflow, needed) in jobs:
                    lines.append(f'    {jobs[(job.workflow, needed)]} -.->|needs| {job_id}')

            for variant in job.variants:
                variant_id = node(self.__variant(variant, [tests[key] for context in variant.contexts if (key := tuple(sorted(context.items()))) in tests]), variant.outcome)
                lines.append(f'    {job_id} --> {variant_id}')

                for text, style in self.__access(variant):
                    lines.append(f'    {variant_id} --> {node(text, style)}')

        lines += [f'    classDef {name} {style}' for name, style in STYLES.items()]

        return '\n'.join(lines) + '\n'

    def __job(self, job: JobNode) -> str:

        parts = [f'<b>{self.__text(job.name)}</b>']

        if job.uses:
            parts.append(f'calls {self.__text(job.uses)}')

        parts += [self.__text(f'gate {gate.name} ({gate.location})') for gate in job.gates[:MAX_LISTED]]
        parts += [self.__text(f'unsolved {item.name}') for item in job.unsolved[:MAX_LISTED]]

        return '<br/>'.join(parts)

    def __variant(self, variant: AccessVariant, tests: list[Tested]) -> str:

        inputs = sorted({f'{name} = {value}' for context in variant.contexts for name, value in context.items() if name != 'event'})
        parts = [*(test.reason for test in tests), *inputs]

        return '<br/>'.join([f'<b>{variant.outcome}</b>', *(self.__text(part) for part in parts)])

    def __access(self, variant: AccessVariant) -> list[tuple[str, str]]:

        access = variant.access
        files = sorted(f'{item.path} ({"".join(KINDS[kind] for kind in sorted(item.access))})' for item in access.files)
        requests = sorted(f'{request.method} {request.scheme}://{request.host}{request.path} {request.status} {request.result}' for request in access.networks)
        requests += [f'direct {connection}' for connection in sorted(access.connections)]
        secrets = [f'used {name}' for name in sorted(access.secrets)] + [f'referenced {name}' for name in sorted(access.referenced)]

        return [(self.__list(title, items), style) for title, items, style in (('Files', files, 'files'), ('Network', requests, 'network'), ('Secrets', secrets, 'secrets')) if items]

    def __list(self, title: str, items: list[str]) -> str:

        shown = [self.__text(item) for item in items[:MAX_LISTED]]

        if len(items) > MAX_LISTED:
            shown.append(f'+{len(items) - MAX_LISTED} more')

        return '<br/>'.join([f'<b>{title} ({len(items)})</b>', *shown])

    def __text(self, value: str) -> str:

        for character, entity in (('#', '#35;'), ('"', '#quot;'), ('<', '#lt;'), ('>', '#gt;'), ('|', '#124;')):
            value = value.replace(character, entity)

        return value

mermaid = Mermaid()

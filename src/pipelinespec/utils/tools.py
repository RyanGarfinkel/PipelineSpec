from langchain_core.tools import BaseTool, ToolException, tool
from singleton_decorator import singleton
from pipelinespec import settings
from pathlib import Path
import os
import re

@singleton
class SharedTools:

    def __is_blocked(self, path: Path) -> bool:

        return '.git' in path.relative_to(settings.repo).parts

    def __resolve_path(self, path: str) -> Path:
    
            target = (settings.repo / path).resolve()
    
            if Path(path).is_absolute() or not target.is_relative_to(settings.repo):
                raise ToolException(f'Blocked: "{path}" is outside the repository.')
    
            if not target.exists():
                raise ToolException(f'Error: "{path}" does not exist.')
    
            if self.__is_blocked(target):
                raise ToolException(f'Blocked: Unable to access "{path}".')
    
            return target

    def __validate_pattern(self, pattern: str) -> str:

        fixed = []

        for part in Path(pattern).parts:
            if any(character in part for character in '*?['):
                break

            fixed.append(part)

        directory = settings.repo.joinpath(*fixed)

        if Path(pattern).is_absolute() or not directory.resolve().is_relative_to(settings.repo):
            raise ToolException(f'Blocked: "{pattern}" is outside the repository.')

        if '..' in Path(pattern).parts[len(fixed):]:
            raise ToolException(f'Blocked: "{pattern}" is outside the repository.')

        if self.__is_blocked(directory):
            raise ToolException(f'Blocked: Unable to access "{pattern}".')

        return pattern

    def __glob(self, pattern: str) -> str:

        if Path(pattern) == Path('.'):
            pattern = '*'

        pattern = self.__validate_pattern(pattern)

        results = []

        for path in settings.repo.glob(pattern):
            relative = Path(os.path.normpath(path)).relative_to(settings.repo).as_posix()

            try:
                self.__resolve_path(relative)
            except ToolException:
                continue

            results.append(relative + ('/' if path.is_dir() else ''))

        if not results:
            raise ToolException(f'No matches for "{pattern}".')

        leftover = len(results) - settings.agent.max_items
        results = results[:settings.agent.max_items]

        if leftover > 0:
            results.append(f'(stopped after {settings.agent.max_items} matches; {leftover} more matches truncated)')

        return '\n'.join(results)

    def __grep(self, pattern: str, path: str) -> str:

        path = self.__resolve_path(path)

        if not path.is_file():
            raise ToolException('Error: grep only searches a single file; use glob to list the files in a directory.')

        try:
            compiled_pattern = re.compile(pattern, re.IGNORECASE)
        except re.error as problem:
            raise ToolException(f'Error: invalid regular expression: {problem}')

        results = []
        with open(path, 'r', errors='replace', encoding='utf-8') as f:
            for line_num, line in enumerate(f, start=1):
                if compiled_pattern.search(line):
                    results.append(f'{line_num}: {line.rstrip()}')

        leftover = len(results) - settings.agent.max_items
        results = results[:settings.agent.max_items]

        if leftover > 0:
            results.append(f'(stopped after {settings.agent.max_items} matches; {leftover} more matches truncated)')

        return '\n'.join(results) if results else 'No matches.'

    def __chunk(self, path: str, start: int, end: int | None) -> str:

        path = self.__resolve_path(path)

        if not path.is_file():
            raise ToolException('Error: chunk only reads a single file; use glob to list the files in a directory.')

        if start < 1:
            raise ToolException(f'Error: start ({start}) must be at least 1.')
        
        if end is not None and end < start:
            raise ToolException(f'Error: end ({end}) is before start ({start}).')

        if end is not None and end - start + 1 > settings.agent.max_items:
            raise ToolException(f'Error: too many lines requested ({end - start + 1} > {settings.agent.max_items}).')
        elif end is None:
            end = start + settings.agent.max_items - 1

        with open(path, 'r', errors='replace', encoding='utf-8') as f:
            lines = f.readlines()

        if not lines:
            raise ToolException(f'Error: "{path.relative_to(settings.repo)}" is empty.')

        if start > len(lines):
            raise ToolException(f'Error: "{path.relative_to(settings.repo)}" has only {len(lines)} lines.')


        selected = [f'{number}: {line.rstrip()}' for number, line in enumerate(lines[start - 1:end], start=start)]

        if end >= len(lines):
            selected.append('(end of file)')

        return '\n'.join(selected)

    def get(self) -> list[BaseTool]:
    
        @tool(parse_docstring=True)
        def glob(pattern: str) -> str:
            """Find files and directories in the repository by glob pattern.

            Args:
                pattern: A glob relative to the repository root, such as `.github/workflows/*.yml` or `**/*.sh`
            """

            return self.__glob(pattern)

        @tool(parse_docstring=True)
        def grep(pattern: str, path: str) -> str:
            """Searches a file in the repository with a regular expression, ignoring case.

            Args:
                pattern: A regular expression, matched against each line.
                path: A file relative to the repository root.
            """

            return self.__grep(pattern, path)

        @tool(parse_docstring=True)
        def chunk(path: str, start: int = 1, end: int | None = None) -> str:
            """Reads range of lines from a file in the repository between two line numbers.

            Args:
                path: A file relative to the repository root.
                start: First line to read, counting from 1.
                end: Last line to read. If omitted, a fixed number of lines will be read.
            """

            return self.__chunk(path, start, end)

        tools = [glob, grep, chunk]

        for each in tools:
            each.handle_tool_error = True

        return tools
    
shared_tools = SharedTools()

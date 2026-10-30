from rich.progress import Progress, RenderableColumn, SpinnerColumn, TextColumn, TimeElapsedColumn
from langchain_core.callbacks import BaseCallbackHandler
from rich.progress_bar import ProgressBar
from pipelinespec import console
import time

MIN_TOOL_SECONDS = 1

class ProgressCallbackHandler(BaseCallbackHandler):

    def __init__(self, name: str):

        self.name = name
        self.progress = Progress(SpinnerColumn(), TextColumn('[cyan]{task.description}'), RenderableColumn(ProgressBar(total=None, pulse=True, width=40, style='grey30', pulse_style='red1')), TimeElapsedColumn(), TextColumn('{task.fields[status]}'), console=console)
        self.task = None
        self.started = 0.0

    def status(self, text: str, style: str = 'none') -> str:

        return f'[{style}]{text}[/{style}]'

    def on_chain_start(self, *_, parent_run_id=None, **__):

        if parent_run_id is not None or self.task is not None:
            return

        self.progress.start()
        self.task = self.progress.add_task(self.name, status=self.status('Thinking...'))

    def on_chain_end(self, *_, parent_run_id=None, **__):

        if parent_run_id is not None or self.task is None:
            return

        self.progress.update(self.task, status=self.status('Done', 'green'))
        self.progress.stop_task(self.task)
        self.progress.stop()
        self.task = None

    def on_chain_error(self, *_, parent_run_id=None, **__):

        if parent_run_id is not None or self.task is None:
            return

        self.progress.stop()
        self.task = None

    def on_tool_start(self, serialized, *_, **__):

        if self.task is not None:
            self.started = time.monotonic()
            self.progress.update(self.task, status=self.status(f'Calling {serialized.get("name", "tool")}...'))

    def on_tool_end(self, *_, **__):

        self.finish_tool()

    def on_tool_error(self, *_, **__):

        self.finish_tool()

    def finish_tool(self):

        if self.task is None:
            return

        time.sleep(max(0, MIN_TOOL_SECONDS - (time.monotonic() - self.started)))
        self.progress.update(self.task, status=self.status('Thinking...'))

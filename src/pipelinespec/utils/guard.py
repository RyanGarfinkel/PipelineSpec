from langchain_core.callbacks import BaseCallbackHandler
from threading import Lock

MAX_ERRORS = 5
REJECTED = 'Rejected, nothing recorded:'

class GuardCallbackHandler(BaseCallbackHandler):

    raise_error = True

    def __init__(self):

        self.errors = 0
        self.lock = Lock()

    def on_tool_end(self, output, *_, **__):

        text = str(getattr(output, 'content', output))

        if text.startswith(REJECTED):
            self.on_tool_error(text)
            return

        with self.lock:
            self.errors = 0

    def on_tool_error(self, error, *_, **__):

        with self.lock:
            self.errors += 1

            if self.errors >= MAX_ERRORS:
                raise RuntimeError(f'The agent made {MAX_ERRORS} rejected tool calls in a row without correcting them. The last error was: {error}')

from langchain_core.callbacks import BaseCallbackHandler
from threading import Lock

MAX_ERRORS = 5
REJECTED = 'Rejected, nothing recorded:'

class GuardError(RuntimeError):

    pass

class GuardCallbackHandler(BaseCallbackHandler):

    raise_error = True

    def __init__(self):

        self.strikes = 0
        self.calls = 0
        self.rejected = 0
        self.error = None
        self.lock = Lock()

    def on_chat_model_start(self, *_, **__):

        with self.lock:
            if self.calls == 0:
                return

            self.strikes = self.strikes + 1 if self.rejected == self.calls else 0
            self.calls = self.rejected = 0

            if self.strikes >= MAX_ERRORS:
                raise GuardError(f'The agent made {MAX_ERRORS} replies in a row whose tool calls were all rejected. The last error was: {self.error}')

    def on_tool_end(self, output, *_, **__):

        text = str(getattr(output, 'content', output))

        if text.startswith(REJECTED):
            self.on_tool_error(text)
            return

        with self.lock:
            self.calls += 1

    def on_tool_error(self, error, *_, **__):

        with self.lock:
            self.calls += 1
            self.rejected += 1
            self.error = error

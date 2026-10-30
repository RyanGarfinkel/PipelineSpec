from rich.console import Console
from .config import settings
import logging

console = Console(stderr=True)

def log(*objects, **options) -> None:

    options.setdefault('markup', False)
    console.log(*objects, _stack_offset=2, **options)

class ConsoleHandler(logging.Handler):

    def emit(self, record):
        console.print(self.format(record), markup=False, highlight=False, soft_wrap=True)

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    handlers=[ConsoleHandler()]
)

for noisy in ('urllib3', 'httpcore', 'httpcore2', 'httpx', 'httpx2', 'openai', 'anthropic'):
    logging.getLogger(noisy).setLevel(logging.WARNING)

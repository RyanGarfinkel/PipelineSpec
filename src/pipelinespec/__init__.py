from rich.logging import RichHandler
from rich.console import Console
from .config import settings
import logging

console = Console(stderr=True)

def log(*objects, **options) -> None:

    options.setdefault('markup', False)
    console.log(*objects, _stack_offset=2, **options)

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    datefmt='[%X]',
    handlers=[RichHandler(console=console, markup=False, show_level=True)]
)

for noisy in ('urllib3', 'httpcore', 'httpcore2', 'httpx', 'httpx2', 'openai', 'anthropic'):
    logging.getLogger(noisy).setLevel(logging.WARNING)

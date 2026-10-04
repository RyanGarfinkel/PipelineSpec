import logging

handler = logging.StreamHandler()
handler.terminator = '\n'

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    handlers=[handler]
)

logging.getLogger('urllib3').setLevel(logging.WARNING)

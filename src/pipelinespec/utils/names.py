import re

UNATTRIBUTED = '_'

def slug(name: str) -> str:

    return re.sub(r'[^A-Za-z0-9_-]', '_', name)[:60] or UNATTRIBUTED

def relative(path: str, root: str) -> str:

    if path == root:
        return '.'

    return path[len(root) + 1:] if path.startswith(root + '/') else path

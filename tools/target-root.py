"""Resolve a target filesystem path without following links into the build host."""
from collections import deque
from pathlib import Path, PurePosixPath
import os


def target_file(root, name):
    root = Path(root).resolve()
    pending = deque(PurePosixPath(str(name).lstrip('/')).parts)
    components = []
    links = 0
    while pending:
        part = pending.popleft()
        if part in ('', '.'):
            continue
        if part == '..':
            if not components:
                raise ValueError('Target path escaped root: '+str(name))
            components.pop()
            continue
        candidate = root.joinpath(*components, part)
        if candidate.is_symlink():
            links += 1
            if links > 40:
                raise ValueError('Target symlink loop: '+str(name))
            link = PurePosixPath(os.readlink(candidate))
            if link.is_absolute():
                components = []
                pending.extendleft(reversed(link.parts[1:]))
            else:
                pending.extendleft(reversed(link.parts))
        else:
            components.append(part)
    result = root.joinpath(*components)
    if not result.is_file():
        raise FileNotFoundError('Target file not found: '+str(name))
    return result

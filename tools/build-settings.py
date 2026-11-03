"""Explicit build paths, shared by the runner and its child tools."""
import json
import os
from pathlib import Path

TOP = Path(__file__).resolve().parents[1]


def settings(config=None, workspace=None):
    config = Path(config or os.environ.get('U30PRO_BUILD_CONFIG') or TOP/'tools/build-layout.json').resolve()
    data = json.loads(config.read_text())
    if 'extends' in data:
        if data['extends'] != 'build-layout.json' or config.parent != (TOP/'tools').resolve():
            raise ValueError('Local build overrides must explicitly extend tools/build-layout.json')
        defaults = json.loads((TOP/'tools/build-layout.json').read_text())
        data = {**defaults, **data}
    if data.get('format') != 1 or data.get('family') != 'u30pro':
        raise ValueError('Expected an explicit U30 Pro build layout')
    selected = Path(workspace or os.environ.get('U30PRO_WORKSPACE') or data['workspace']).expanduser()
    if not selected.is_absolute() or str(selected).lower().startswith(('/mnt/c/', 'c:')):
        raise ValueError('Select an absolute build workspace outside C:')
    work = selected.resolve()
    if work in (Path('/'), Path.home().resolve()) or str(work).lower().startswith(('/mnt/c/', 'c:')):
        raise ValueError('Select a dedicated build workspace outside C:')
    values = {'repo': str(TOP), 'workspace': str(work)}
    def expand(value):
        if isinstance(value, str):
            return value.format(**values)
        if isinstance(value, dict):
            return {k: expand(v) for k, v in value.items()}
        return value
    return config, work, expand(data)

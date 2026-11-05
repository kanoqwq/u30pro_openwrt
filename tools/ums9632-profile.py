"""One shared UMS9632 platform; explicit product capabilities and SIM wiring."""
import json
import os
from pathlib import Path

TOP = Path(__file__).resolve().parents[1]


def selected(name=None):
    name = name or os.environ.get('UMS9632_MODEL', 'u30pro')
    if name == 'u30pro':
        return dict(id=name, platform='u30pro', label='U30 Pro', hostname='U30Pro',
                    android_models=['MU5358', 'MU5358D', 'MU5358E'],
                    sim_layout='mu5358', screen=True, battery=True)
    if name != 'f50pro':
        raise ValueError('Unknown UMS9632 product profile: ' + str(name))
    data = json.loads((TOP/'devices/f50pro/profile.json').read_text(encoding='utf-8'))
    if (data['id'] != name or data['platform'] != 'u30pro' or data['screen'] or
            data['battery'] or data['sim_layout'] != 'mu3356'):
        raise ValueError('Invalid F50 Pro hardware capability profile')
    return data

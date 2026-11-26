"""Build the actual native UI host simulator and render supplied-icon previews.

Offline only: the high-rail indication is injected into a synthetic screen feed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from PIL import Image

TOP = Path(__file__).resolve().parents[1]
NATIVE = TOP / 'devices/u30pro/native/tools'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sequence = '''page 0
set highrail 0
shot 5g-normal
set highrail 1
shot 5g-rail
set highrail 0
shot 5g-restored
set rat 4G
shot 4g-normal
set highrail 1
shot 4g-rail
set highrail 0
shot 4g-restored
'''
    with tempfile.TemporaryDirectory(prefix='u30pro-high-rail-') as temporary:
        binary = Path(temporary) / 'ui-host'
        subprocess.run(['gcc', '-DUI_HOST', f'-DUI_RUN="{temporary}"', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-o', str(binary), str(NATIVE / 'u30pro_ui.c'), '-lm'], check=True)
        subprocess.run([str(binary), 'sim', str(output)], input=sequence, text=True, check=True, timeout=30)
    for rat in ('5g', '4g'):
        normal = Image.open(output / (rat + '-normal.ppm')).convert('RGB')
        restored = Image.open(output / (rat + '-restored.ppm')).convert('RGB')
        active = Image.open(output / (rat + '-rail.ppm')).convert('RGB')
        assert normal.tobytes() == restored.tobytes(), 'Rail exit must restore the original geometry and pixels'
        assert normal.crop((0, 0, 240, 128)).tobytes() == active.crop((0, 0, 240, 128)).tobytes()
        assert normal.crop((0, 151, 240, 240)).tobytes() == active.crop((0, 151, 240, 240)).tobytes()
        assert normal.crop((0, 128, 240, 151)).tobytes() != active.crop((0, 128, 240, 151)).tobytes()
        for state, picture in (('normal', normal), ('rail', active)):
            picture.resize((480, 480), Image.LANCZOS).save(output / f'{rat}-{state}.png')
    comparison = Image.new('RGB', (1000, 1000), (8, 12, 20))
    for row, rat in enumerate(('5g', '4g')):
        for col, state in enumerate(('normal', 'rail')):
            with Image.open(output / f'{rat}-{state}.png') as picture:
                comparison.paste(picture, (10 + col * 500, 10 + row * 500))
    comparison.save(output / 'comparison.png')
    manifest = {'kind': 'native UI simulator preview; no hardware deployment or live URC validation',
                'svg_sha256': hashlib.sha256((TOP / 'devices/u30pro/assets/high-rail.svg').read_bytes()).hexdigest(),
                'sources': {str(p.relative_to(TOP)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in [NATIVE / 'u30pro_ui.c'] + sorted((NATIVE / 'ui').glob('*.h'))},
                'script': sequence, 'result': '5G/4G entry/exit pixels verified; only network row changes'}
    (output / 'PREVIEW.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print('Native screen preview:', output / 'comparison.png')


if __name__ == '__main__':
    main()

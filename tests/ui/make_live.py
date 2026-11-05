#!/usr/bin/env python3
"""Write a test live wallpaper for the screen simulator: wallpaper.live in clip format 2 (tools/ui/wall.h: 16x16 tile deltas, zlib) and its
first frame as wallpaper.jpg (needs Pillow).  The frames are a moving pattern with a still part, so some tiles stay unchanged.

usage: make_live.py <dir> [frames] [fps]       the clip, its first frame, and frames.rgb (every frame, raw) in <dir>
       make_live.py --check <clip> <frames.rgb>  decode a version 2 clip on its own and compare it with the raw frames"""
import struct
import sys
import zlib
from pathlib import Path

S, T = 240, 16


def frame(i):
    """240x240 RGB bytes: a gradient sliding right, a disc circling, the bottom quarter still"""
    out = bytearray(S * S * 3)
    cx, cy = 120 + int(60 * __import__('math').cos(i / 6)), 90 + int(40 * __import__('math').sin(i / 6))
    for y in range(S):
        for x in range(S):
            o = (y * S + x) * 3
            if y >= 180:
                out[o:o + 3] = bytes((40, 60 + x // 4, 90))
            elif (x - cx) ** 2 + (y - cy) ** 2 < 900:
                out[o:o + 3] = bytes((250, 200, 40))
            else:
                out[o:o + 3] = bytes(((x + i * 4) & 255, (y * 2) & 255, (x + y - i * 3) & 255))
    return bytes(out)


def payload(prev, cur):
    if prev is None:
        return b'\0' + cur
    bits, tiles = bytearray((S // T) ** 2 // 8 + 1), bytearray()
    for t in range((S // T) ** 2):
        tx, ty = t % (S // T), t // (S // T)
        rows = [cur[((ty * T + y) * S + tx * T) * 3:((ty * T + y) * S + tx * T + T) * 3] for y in range(T)]
        olds = [prev[((ty * T + y) * S + tx * T) * 3:((ty * T + y) * S + tx * T + T) * 3] for y in range(T)]
        if rows == olds:
            continue
        bits[t >> 3] |= 1 << (t & 7)
        for r, o in zip(rows, olds):
            tiles += bytes((a - b) & 255 for a, b in zip(r, o))
    return b'\1' + bytes(bits[:((S // T) ** 2 + 7) // 8]) + bytes(tiles)


def check(clip, raw):
    data, frames = Path(clip).read_bytes(), Path(raw).read_bytes()
    magic, ver, fps, w, h, tile, n = data[:4], *struct.unpack('<BBHHHI', data[4:16])
    assert (magic, ver, w, h, tile) == (b'U3LW', 2, S, S, T), (magic, ver, w, h, tile)
    pos, cur, tx = 16, None, S // T
    for i in range(n):
        ln = struct.unpack('<I', data[pos:pos + 4])[0]
        p = zlib.decompress(data[pos + 4:pos + 4 + ln])
        pos += 4 + ln
        if p[0] == 0:
            cur = bytearray(p[1:])
        else:
            bits, d = p[1:1 + (tx * tx + 7) // 8], 1 + (tx * tx + 7) // 8
            for t in range(tx * tx):
                if not bits[t >> 3] >> (t & 7) & 1:
                    continue
                for y in range(T):
                    o = (((t // tx) * T + y) * S + (t % tx) * T) * 3
                    for k in range(T * 3):
                        cur[o + k] = (cur[o + k] + p[d]) & 255
                        d += 1
            assert d == len(p), 'frame %d: %d of %d bytes used' % (i, d, len(p))
        want = frames[i * S * S * 3:(i + 1) * S * S * 3]
        assert bytes(cur) == want, 'frame %d differs' % i
    assert pos == len(data)
    print('%s: %d frames at %d fps decode to the raw frames' % (clip, n, fps))


def main():
    if sys.argv[1] == '--check':
        return check(sys.argv[2], sys.argv[3])
    d = Path(sys.argv[1])
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 48
    fps = int(sys.argv[3]) if len(sys.argv) > 3 else 24
    frames = [frame(i) for i in range(n)]
    parts = [b'U3LW' + struct.pack('<BBHHHI', 2, fps, S, S, T, n)]
    prev = None
    for f in frames:
        z = zlib.compress(payload(prev, f), 6)
        parts.append(struct.pack('<I', len(z)) + z)
        prev = f
    d.mkdir(parents=True, exist_ok=True)
    (d / 'wallpaper.live').write_bytes(b''.join(parts))
    (d / 'frames.rgb').write_bytes(b''.join(frames))
    from PIL import Image
    Image.frombytes('RGB', (S, S), frames[0]).save(d / 'wallpaper.jpg', quality=90)
    print('%s: %d frames, %d bytes' % (d / 'wallpaper.live', n, sum(map(len, parts))))


if __name__ == '__main__':
    main()

"""The shared placeholder avatar (spec section 6): a neutral grey person silhouette in a circle, drawn in pure Python.

128x128 RGBA PNG, transparent outside the circle, byte-for-byte the same on every run. `ensure_placeholder` writes it
only when the file is missing, so a placeholder.png supplied by the user is kept."""
from __future__ import annotations

import functools
import struct
import zlib
from pathlib import Path

FILE = "placeholder.png"
SIZE = 128
_DISC = (158, 158, 158)          # neutral grey circle
_FIGURE = (226, 226, 226)        # lighter head and shoulders
_SAMPLES = 3                     # 3x3 supersampling smooths the edges


def _shade(x: float, y: float):
    """Colour at a point, or None outside the circle."""
    c = SIZE / 2
    if (x - c) ** 2 + (y - c) ** 2 > c * c:
        return None
    head = (x - c) ** 2 + (y - 50) ** 2 <= 22 ** 2
    shoulders = ((x - c) / 42) ** 2 + ((y - 120) / 36) ** 2 <= 1
    return _FIGURE if head or shoulders else _DISC


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


@functools.lru_cache(maxsize=1)
def placeholder_png() -> bytes:
    rows = []
    steps = [(i + 0.5) / _SAMPLES for i in range(_SAMPLES)]
    for py in range(SIZE):
        row = bytearray([0])                         # filter: none
        for px in range(SIZE):
            hits = [_shade(px + dx, py + dy) for dy in steps for dx in steps]
            inside = [h for h in hits if h is not None]
            if not inside:
                row += b"\0\0\0\0"
                continue
            colour = [round(sum(h[k] for h in inside) / len(inside)) for k in range(3)]
            row += bytes(colour + [round(255 * len(inside) / len(hits))])
        rows.append(bytes(row))
    header = struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
            + _chunk(b"IEND", b""))


def ensure_placeholder(folder) -> bool:
    """Write <folder>/placeholder.png when it is missing. True when it was written."""
    path = Path(folder) / FILE
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(placeholder_png())
    tmp.replace(path)
    return True

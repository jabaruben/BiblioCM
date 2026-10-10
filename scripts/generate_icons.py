"""Genera los iconos PNG de la PWA usando únicamente la biblioteca estándar."""
import struct
import zlib
from pathlib import Path


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def generate(size):
    pixels = bytearray()
    for y in range(size):
        pixels.append(0)
        for x in range(size):
            px, py = x / size * 512, y / size * 512
            color = (22, 78, 67)
            if 130 <= px <= 382 and 155 <= py <= 360:
                color = (238, 242, 232)
                if 250 <= px <= 262 or py < 170 + abs(px - 256) * -.12:
                    color = (22, 78, 67)
            pixels.extend(color)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(pixels))) + chunk(b"IEND", b""))


if __name__ == "__main__":
    folder = Path(__file__).resolve().parents[1] / "biblio" / "static"
    for size in (192, 512):
        (folder / f"icon-{size}.png").write_bytes(generate(size))
        print(f"Generado icon-{size}.png")

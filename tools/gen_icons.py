"""
Genera los íconos PWA de MicroAlerta con la librería estándar (sin PIL).

Diseño: placa Petri con partículas microscópicas sobre fondo oscuro científico.
Uso:
    python tools/gen_icons.py
"""
import math, os, struct, sys, zlib

# Consola Windows: evitar errores de encoding al imprimir
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ACCENT = (30, 136, 229)     # azul botella PET
GREEN = (46, 158, 91)       # verde botella
YELLOW = (245, 197, 24)     # amarillo plástico
PURPLE = (142, 107, 209)    # violeta plástico
BG_TOP = (18, 60, 90)       # brillo plástico superior
BG_BOT = (21, 24, 27)       # negro plástico
DISH = (30, 35, 39)
EDGE = (38, 44, 49)


def _chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data +
            struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def png_bytes(size, rgba_grid):
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            row += bytes(rgba_grid[y][x])
        rows.append(bytes(row))
    raw = b"".join(rows)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) +
            _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b""))


def _rr_inside(x, y, size, rad):
    if x < rad and y < rad:
        return (x - rad) ** 2 + (y - rad) ** 2 <= rad ** 2
    if x < rad and y >= size - rad:
        return (x - rad) ** 2 + (y - (size - rad)) ** 2 <= rad ** 2
    if x >= size - rad and y < rad:
        return (x - (size - rad)) ** 2 + (y - rad) ** 2 <= rad ** 2
    if x >= size - rad and y >= size - rad:
        return (x - (size - rad)) ** 2 + (y - (size - rad)) ** 2 <= rad ** 2
    return 0 <= x < size and 0 <= y < size


def pixel_at(x, y, size):
    """Devuelve (r,g,b,a) para coordenada entera dentro de size×size."""
    rad = size * 0.235
    if not _rr_inside(x + 0.5, y + 0.5, size, rad):
        return (0, 0, 0, 0)

    # Fondo degradado oscuro
    t = y / size
    bg = tuple(int(BG_TOP[i] * (1 - t) + BG_BOT[i] * t) for i in range(3))

    cx = size / 2.0
    cy = size * 0.46
    r = size * 0.30
    d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)

    # Plato: borde (anillo) y mezcla del interior
    ring = r * 0.075
    if abs(d - r) <= ring:
        return ACCENT + (255,)
    if d <= r:
        inter = tuple(int(DISH[i] * 0.75 + EDGE[i] * 0.25) for i in range(3))
        pscale = size * 0.055
        for pr, ang, col in _PARTICLES:
            px = cx + math.cos(ang) * pr
            py = cy + math.sin(ang) * pr
            if math.hypot(x + 0.5 - px, y + 0.5 - py) <= pscale:
                return col + (255,)
        return inter + (255,)
    return bg + (255,)  # fuera del plato: fondo


_PARTICLES = [
    (0.42 * 0.30, -0.9, GREEN),
    (0.05 * 0.30, 1.1, YELLOW),
    (0.55 * 0.30, 0.35, PURPLE),
    (0.15 * 0.30, 0.85, ACCENT),
]


def render(size, samples=2):
    """Renderiza con supersampling limitado y reduce promediando."""
    S = size * samples
    acc = [[[0, 0, 0, 0] for _ in range(size)] for _ in range(size)]
    n = samples * samples
    for y in range(size):
        for x in range(size):
            sums = [0, 0, 0, 0]
            for oy in range(samples):
                for ox in range(samples):
                    r, g, b, a = pixel_at(x * samples + ox, y * samples + oy, S)
                    sums[0] += r; sums[1] += g; sums[2] += b; sums[3] += a
            acc[y][x] = tuple(v // n for v in sums)
    return png_bytes(size, acc)


def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "static", "icons")
    os.makedirs(out, exist_ok=True)
    # De menor a mayor para que, ante una interrupción, los íconos base existan.
    for size, name in [(64, "favicon.png"), (96, "icon-96.png"),
                       (192, "icon-192.png"), (512, "icon-512.png")]:
        path = os.path.join(out, name)
        print(f"Renderizando {name} ({size}x{size})...", flush=True)
        with open(path, "wb") as f:
            f.write(render(size))
        print(f"OK {name} -> {path}", flush=True)


if __name__ == "__main__":
    main()
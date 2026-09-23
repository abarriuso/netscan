#!/usr/bin/env python3
"""Envuelve las capturas del dashboard en un mockup de ventana de navegador
con el estilo 'Terminal Brutalist' de NetScan (tema oscuro, acento cian).

Genera <nombre>-mock.png junto a cada captura original. No toca los PNG
originales. Reejecutable de forma idempotente.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent

# --- Paleta (extraída del dashboard real) -------------------------------
BG        = (8, 9, 12)         # fondo casi-negro del canvas
CHROME    = (16, 18, 22)       # barra superior de la ventana
CHROME_LO = (11, 12, 15)       # degradado inferior de la barra
BORDER    = (34, 44, 48)       # borde exterior sutil
ACCENT    = (45, 212, 191)     # cian/teal de acento
URLBAR    = (13, 15, 18)       # fondo de la barra de direcciones
URLBORDER = (40, 52, 56)
TXT_DIM   = (110, 122, 128)    # texto tenue (mono)
TXT_URL   = (150, 214, 208)    # texto de la URL, cian apagado
DOT_R     = (255, 95, 86)      # semáforo rojo
DOT_Y     = (255, 189, 46)     # semáforo ámbar
DOT_G     = (39, 201, 63)      # semáforo verde

MONO      = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_B    = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

SHOTS = [
    ("dashboard-live.png",         "netscan.local:8600/#en-vivo"),
    ("dashboard-overview.png",     "netscan.local:8600/#resumen"),
    ("dashboard-devices.png",      "netscan.local:8600/#dispositivos"),
    ("dashboard-analytics.png",    "netscan.local:8600/#analitica"),
    ("dashboard-integrations.png", "netscan.local:8600/#integraciones"),
    ("dashboard-system.png",       "netscan.local:8600/#sistema"),
]


def rounded_mask(size, radius):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius, fill=255)
    return m


def make_mock(shot_path: Path, url: str) -> Path:
    shot = Image.open(shot_path).convert("RGB")
    w, h = shot.size

    # Escala todo con el ancho de la captura para que se vea bien a 2880px.
    s          = w / 2880.0
    pad        = int(46 * s)          # margen alrededor de la ventana
    chrome_h   = int(96 * s)          # alto de la barra del navegador
    radius     = int(22 * s)          # redondeo de esquinas
    win_w      = w + pad * 2
    win_h      = h + chrome_h + pad * 2

    canvas = Image.new("RGB", (win_w, win_h), BG)
    d = ImageDraw.Draw(canvas)

    # Rejilla tenue de fondo (guiño al grid del dashboard).
    grid = int(64 * s)
    gcol = (13, 15, 19)
    for x in range(0, win_w, grid):
        d.line([(x, 0), (x, win_h)], fill=gcol, width=1)
    for y in range(0, win_h, grid):
        d.line([(0, y), (win_w, y)], fill=gcol, width=1)

    win_x0, win_y0 = pad, pad
    win_x1, win_y1 = pad + w, pad + chrome_h + h

    # Ventana con esquinas redondeadas.
    window = Image.new("RGB", (w, chrome_h + h), CHROME)
    wd = ImageDraw.Draw(window)
    # Degradado vertical de la barra de chrome.
    for i in range(chrome_h):
        t = i / max(chrome_h - 1, 1)
        c = tuple(int(CHROME[k] + (CHROME_LO[k] - CHROME[k]) * t) for k in range(3))
        wd.line([(0, i), (w, i)], fill=c)
    # La captura debajo de la barra.
    window.paste(shot, (0, chrome_h))
    mask = rounded_mask(window.size, radius)
    canvas.paste(window, (win_x0, win_y0), mask)

    # Borde exterior de la ventana.
    d.rounded_rectangle([win_x0, win_y0, win_x1 - 1, win_y1 - 1], radius,
                        outline=BORDER, width=max(1, int(2 * s)))
    # Línea separadora bajo la barra de chrome, en cian tenue.
    sep_y = win_y0 + chrome_h
    d.line([(win_x0 + radius // 2, sep_y), (win_x1 - radius // 2, sep_y)],
           fill=(24, 40, 42), width=max(1, int(2 * s)))

    # Semáforo (traffic lights).
    cy = win_y0 + chrome_h // 2
    r = int(11 * s)
    gap = int(36 * s)
    cx = win_x0 + int(40 * s)
    for i, col in enumerate((DOT_R, DOT_Y, DOT_G)):
        x = cx + i * gap
        d.ellipse([x - r, cy - r, x + r, cy + r], fill=col)

    # Barra de direcciones centrada.
    bar_h = int(52 * s)
    bar_x0 = win_x0 + int(190 * s)
    bar_x1 = win_x1 - int(190 * s)
    bar_y0 = cy - bar_h // 2
    bar_y1 = cy + bar_h // 2
    d.rounded_rectangle([bar_x0, bar_y0, bar_x1, bar_y1], int(12 * s),
                        fill=URLBAR, outline=URLBORDER, width=max(1, int(1.5 * s)))

    # Candado (lock) dibujado a mano en cian.
    lock_x = bar_x0 + int(26 * s)
    lb = int(15 * s)          # ancho del cuerpo
    lh = int(12 * s)          # alto del cuerpo
    body_top = cy - lh // 2 + int(3 * s)
    d.rounded_rectangle([lock_x, body_top, lock_x + lb, body_top + lh],
                        int(3 * s), fill=ACCENT)
    # Arco del candado.
    aw = int(9 * s)
    d.arc([lock_x + (lb - aw) // 2, body_top - int(9 * s),
           lock_x + (lb + aw) // 2, body_top + int(5 * s)],
          180, 360, fill=ACCENT, width=max(1, int(2.5 * s)))

    # Texto de la URL.
    try:
        f_url = ImageFont.truetype(MONO, int(28 * s))
        f_dim = ImageFont.truetype(MONO, int(24 * s))
        f_ttl = ImageFont.truetype(MONO_B, int(26 * s))
    except OSError:
        f_url = f_dim = f_ttl = ImageFont.load_default()

    tx = lock_x + lb + int(20 * s)
    d.text((tx, cy), url, font=f_url, fill=TXT_URL, anchor="lm")

    # Etiqueta del producto a la derecha de la barra.
    d.text((win_x1 - int(40 * s), cy), "NetScan", font=f_ttl,
           fill=(70, 82, 88), anchor="rm")

    out = shot_path.with_name(shot_path.stem + "-mock.png")
    canvas.save(out, optimize=True)
    return out


def main() -> None:
    for name, url in SHOTS:
        p = HERE / name
        if not p.is_file():
            print(f"  ! falta {name}, se omite")
            continue
        out = make_mock(p, url)
        print(f"  ✓ {out.name}  ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()

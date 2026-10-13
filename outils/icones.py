"""Génère les icônes de l'app (icone.png, icone.ico pour Windows, icone.icns pour macOS)."""

import os
import sys

import numpy as np
from PIL import Image, ImageDraw

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

import moteur  # noqa: E402

# La mascotte (même dessin que dans app.py, recopié pour ne pas charger l'interface)
CRABE = [
    ".XX.........XX.",
    "X.XX.......XX.X",
    "XX.X.......X.XX",
    ".XX..O...O..XX.",
    "..X..X...X..X..",
    "..XXXXXXXXXXX..",
    ".XXXXXXXXXXXXX.",
    "XX.XXXXXXXXX.XX",
    "X..XX.XXX.XX..X",
    "...X..X.X..X...",
]


def dessiner(n=1024):
    y, x = np.mgrid[0:n, 0:n] / n
    halo = np.clip(1 - np.hypot(x - 0.5, y - 0.52) * 2.1, 0, 1) ** 1.6
    src = (np.dstack([halo] * 3) * 255).astype(np.uint8)
    fond = moteur.traiter(src, {"algorithme": "Bayer 8×8", "taille_pixel": 16,
                                "palette": ["#0b0b0d", "#3a140c"], "perceptuel": False})
    fond = Image.fromarray(fond).resize((n, n), Image.Resampling.NEAREST)
    d = ImageDraw.Draw(fond)
    t = n * 48 // 1024
    cw, ch = len(CRABE[0]) * t, len(CRABE) * t
    x0, y0 = (n - cw) // 2, (n - ch) // 2 + n // 50
    for j, ligne in enumerate(CRABE):
        for i, c in enumerate(ligne):
            if c != ".":
                d.rectangle((x0 + i * t, y0 + j * t, x0 + (i + 1) * t - 3, y0 + (j + 1) * t - 3),
                            fill="#ece7e1" if c == "O" else "#ff5b3a")
    masque = Image.new("L", (n, n), 0)
    ImageDraw.Draw(masque).rounded_rectangle((60, 60, n - 60, n - 60), radius=210, fill=255)
    icone = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    icone.paste(fond, (0, 0), masque)
    return icone


if __name__ == "__main__":
    icone = dessiner()
    icone.save(os.path.join(RACINE, "icone.png"))
    icone.save(os.path.join(RACINE, "icone.ico"),
               sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    icone.save(os.path.join(RACINE, "icone.icns"))
    print("Icônes créées : icone.png, icone.ico, icone.icns")

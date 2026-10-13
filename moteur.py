"""
Moteur de Crunch Crab.

Tout le traitement d'image se passe ici, sans aucune interface graphique.
La fonction principale est `traiter(image, reglages, frame)` : elle prend une
image (tableau numpy RVB uint8) et renvoie l'image « croquée ».

Le pipeline, dans l'ordre :
  1. Réduction (taille des pixels)
  2. Retouche      : lumière, couleurs, flou, netteté, encrage
  3. Déformations  : miroir, ondulation, tri de pixels
  4. Tramage       : la palette et la façon de poser les points
  5. Glitch        : tranches, blocs, lignes étirées
  6. Optique       : aberration chromatique, décalage RVB, bavure VHS, lueur, fuite de lumière
  7. Écran         : artefacts JPEG, postérisation, bande VHS, lignes CRT, grille, courbure,
                     vignette, grain

Les boucles pixel par pixel sont compilées par Numba (@njit) : c'est ce qui
rend le programme presque aussi rapide que du C.
"""

import io
import os
import sys
from functools import lru_cache

if getattr(sys, "frozen", False):
    # Dans l'app empaquetée, le cache de compilation va dans le dossier utilisateur
    # (à régler avant d'importer numba)
    os.environ.setdefault("NUMBA_CACHE_DIR", os.path.join(os.path.expanduser("~"), ".cache",
                                                          "crunchcrab"))

import numpy as np  # noqa: E402
from numba import njit  # noqa: E402
from PIL import Image, ImageFilter  # noqa: E402


def compiler(fn):
    """Compile une fonction en code machine, avec un cache sur disque quand c'est possible."""
    try:
        return njit(cache=True, nogil=True)(fn)
    except Exception:  # pas de cache disponible (app empaquetée sans sources) : tant pis
        return njit(nogil=True)(fn)


LUMA = np.array([0.299, 0.587, 0.114], np.float32)

# ---------------------------------------------------------------------------
# Palettes
# ---------------------------------------------------------------------------

PALETTES = {
    "Noir & blanc": ["#000000", "#ffffff"],
    "Encre & papier": ["#1b1a17", "#efe7d6"],
    "Game Boy": ["#0f380f", "#306230", "#8bac0f", "#9bbc0f"],
    "CGA": ["#000000", "#55ffff", "#ff55ff", "#ffffff"],
    "PICO-8": ["#000000", "#1d2b53", "#7e2553", "#008751", "#ab5236", "#5f574f",
               "#c2c3c7", "#fff1e8", "#ff004d", "#ffa300", "#ffec27", "#00e436",
               "#29adff", "#83769c", "#ff77a8", "#ffccaa"],
    "Commodore 64": ["#000000", "#ffffff", "#880000", "#aaffee", "#cc44cc", "#00cc55",
                     "#0000aa", "#eeee77", "#dd8855", "#664400", "#ff7777", "#333333",
                     "#777777", "#aaff66", "#0088ff", "#bbbbbb"],
    "Télétexte": ["#000000", "#ff0000", "#00ff00", "#ffff00", "#0000ff", "#ff00ff",
                  "#00ffff", "#ffffff"],
    "Crabe": ["#120808", "#5c1a14", "#d9432b", "#ff8a5c", "#ffe2c8"],
    "Abysses": ["#03070d", "#0b2a3d", "#11667a", "#3fb8af", "#d7f5e9"],
    "Sépia": ["#2b1d0e", "#6b4a2b", "#b08a5a", "#f1e3c6"],
    "Écran ambre": ["#140a00", "#7a4100", "#ffb000"],
    "Phosphore vert": ["#001400", "#00701a", "#33ff66"],
    "Néon": ["#0b0221", "#3d0a6b", "#ff2a6d", "#05d9e8", "#d1f7ff"],
    "Vaporwave": ["#2e2157", "#ff71ce", "#01cdfe", "#05ffa1", "#b967ff", "#fffb96"],
    "Risographie": ["#1a1a1a", "#0078bf", "#ff48b0", "#f7f1e3"],
    "Coucher de soleil": ["#1a0f2e", "#5b1f4f", "#c2365a", "#f57b42", "#ffd27a"],
    "Bichromie bleue": ["#0a1033", "#e9edf7"],
}


def hex_vers_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_vers_hex(rgb):
    return "#%02x%02x%02x" % tuple(int(c) for c in rgb)


def palette_niveaux_de_gris(n):
    n = max(2, n)
    return [rgb_vers_hex((round(255 * i / (n - 1)),) * 3) for i in range(n)]


def palette_depuis_image(img, n):
    """Extrait les n couleurs dominantes d'une image (algorithme median cut)."""
    petite = Image.fromarray(img)
    petite.thumbnail((256, 256))
    q = petite.quantize(colors=max(2, n), method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[: 3 * max(2, n)]
    couleurs = [rgb_vers_hex(pal[i:i + 3]) for i in range(0, len(pal), 3)]
    couleurs.sort(key=lambda c: sum(hex_vers_rgb(c)))  # du plus sombre au plus clair
    return couleurs


# ---------------------------------------------------------------------------
# Algorithmes de tramage
# ---------------------------------------------------------------------------

# Diffusion d'erreur : (décalage x, décalage y, poids) et diviseur
NOYAUX = {
    "Floyd-Steinberg": ([(1, 0, 7), (-1, 1, 3), (0, 1, 5), (1, 1, 1)], 16),
    "Atkinson (Mac classique)": ([(1, 0, 1), (2, 0, 1), (-1, 1, 1), (0, 1, 1), (1, 1, 1),
                                  (0, 2, 1)], 8),
    "Jarvis-Judice-Ninke": ([(1, 0, 7), (2, 0, 5), (-2, 1, 3), (-1, 1, 5), (0, 1, 7),
                             (1, 1, 5), (2, 1, 3), (-2, 2, 1), (-1, 2, 3), (0, 2, 5),
                             (1, 2, 3), (2, 2, 1)], 48),
    "Stucki": ([(1, 0, 8), (2, 0, 4), (-2, 1, 2), (-1, 1, 4), (0, 1, 8), (1, 1, 4),
                (2, 1, 2), (-2, 2, 1), (-1, 2, 2), (0, 2, 4), (1, 2, 2), (2, 2, 1)], 42),
    "Burkes": ([(1, 0, 8), (2, 0, 4), (-2, 1, 2), (-1, 1, 4), (0, 1, 8), (1, 1, 4),
                (2, 1, 2)], 32),
    "Sierra": ([(1, 0, 5), (2, 0, 3), (-2, 1, 2), (-1, 1, 4), (0, 1, 5), (1, 1, 4),
                (2, 1, 2), (-1, 2, 2), (0, 2, 3), (1, 2, 2)], 32),
    "Sierra 2 lignes": ([(1, 0, 4), (2, 0, 3), (-2, 1, 1), (-1, 1, 2), (0, 1, 3),
                         (1, 1, 2), (2, 1, 1)], 16),
    "Sierra Lite": ([(1, 0, 2), (-1, 1, 1), (0, 1, 1)], 4),
    "Diffusion horizontale": ([(1, 0, 1)], 1),
    "Diffusion verticale": ([(0, 1, 1)], 1),
}

ORDONNES = ["Bayer 2×2", "Bayer 4×4", "Bayer 8×8", "Bayer 16×16", "Bruit bleu",
            "Trame en points", "Trame en lignes", "Trame diagonale", "Trame en croix",
            "Trame en vagues"]

AUTRES = ["Aucun (seuil)", "Bruit aléatoire", "Demi-teinte (points ronds)"]

ALGORITHMES = list(NOYAUX) + ORDONNES + AUTRES

AVEC_MOTIF = {"Trame en points", "Trame en lignes", "Trame diagonale", "Trame en croix",
              "Trame en vagues", "Demi-teinte (points ronds)"}

MIROIRS = ["Aucun", "Gauche → droite", "Droite → gauche", "Haut → bas", "Kaléidoscope"]
DIRECTIONS = ["Horizontal", "Vertical"]


@compiler
def _plus_proche(r, g, b, pal, wr, wg, wb):
    meilleur = 0
    dmin = 1e18
    for i in range(pal.shape[0]):
        dr = r - pal[i, 0]
        dg = g - pal[i, 1]
        db = b - pal[i, 2]
        d = wr * dr * dr + wg * dg * dg + wb * db * db
        if d < dmin:
            dmin = d
            meilleur = i
    return meilleur


@compiler
def _carte_plus_proche(img, pal, poids):
    h, w, _ = img.shape
    out = np.empty((h, w), np.int32)
    for y in range(h):
        for x in range(w):
            out[y, x] = _plus_proche(img[y, x, 0], img[y, x, 1], img[y, x, 2],
                                     pal, poids[0], poids[1], poids[2])
    return out


@compiler
def _ordonne(img, pal, carte, ecart, poids):
    """Tramage ordonné : on décale chaque pixel selon la carte de seuils, puis couleur la plus proche."""
    h, w, _ = img.shape
    th, tw = carte.shape
    out = np.empty((h, w), np.int32)
    for y in range(h):
        for x in range(w):
            d = (carte[y % th, x % tw] - 0.5) * ecart
            out[y, x] = _plus_proche(img[y, x, 0] + d, img[y, x, 1] + d, img[y, x, 2] + d,
                                     pal, poids[0], poids[1], poids[2])
    return out


@compiler
def _remap(img, yy, xx, dehors):
    """Déplace les pixels selon une carte de coordonnées (courbure d'écran)."""
    h, w = yy.shape
    out = np.empty_like(img)
    for y in range(h):
        for x in range(w):
            if dehors[y, x]:
                out[y, x, 0] = 0
                out[y, x, 1] = 0
                out[y, x, 2] = 0
            else:
                out[y, x, 0] = img[yy[y, x], xx[y, x], 0]
                out[y, x, 1] = img[yy[y, x], xx[y, x], 1]
                out[y, x, 2] = img[yy[y, x], xx[y, x], 2]
    return out


@compiler
def _remap_canal(img, canal, yy, xx, out):
    h, w = yy.shape
    for y in range(h):
        for x in range(w):
            out[y, x, canal] = img[yy[y, x], xx[y, x], canal]


@compiler
def _flou_lignes(a, rayon):
    """Flou boîte le long des lignes, en une seule passe (somme glissante)."""
    h, w, c = a.shape
    out = np.empty_like(a)
    n = 2 * rayon + 1
    for y in range(h):
        for k in range(c):
            s = 0.0
            for i in range(-rayon, rayon + 1):
                s += a[y, min(max(i, 0), w - 1), k]
            for x in range(w):
                out[y, x, k] = s / n
                s += a[y, min(x + rayon + 1, w - 1), k] - a[y, max(x - rayon, 0), k]
    return out


@compiler
def _superposer(out, halo, force, r, g, b):
    """Mode « écran » : éclaire l'image avec un halo (lueur, fuite de lumière), sur place."""
    h, w, _ = out.shape
    teinte = (r, g, b)
    plein = halo.ndim == 3
    for y in range(h):
        for x in range(w):
            for c in range(3):
                v = (halo[y, x, c] if plein else halo[y, x, 0]) * force * teinte[c]
                v = min(max(v, 0.0), 1.0)
                out[y, x, c] = 1 - (1 - out[y, x, c]) * (1 - v)


@compiler
def _en_octets_rapide(a):
    h, w, c = a.shape
    out = np.empty((h, w, c), np.uint8)
    for y in range(h):
        for x in range(w):
            for k in range(c):
                v = a[y, x, k] * 255 + 0.5
                out[y, x, k] = 0 if v < 0 else (255 if v > 255 else np.uint8(v))
    return out


@compiler
def _diffusion_erreur(img, pal, kx, ky, kw, force, zigzag, poids):
    h, w, _ = img.shape
    buf = img.copy()
    out = np.empty((h, w), np.int32)
    n = kx.shape[0]
    for y in range(h):
        inverse = zigzag and (y & 1) == 1
        for i in range(w):
            x = w - 1 - i if inverse else i
            r = min(max(buf[y, x, 0], -0.5), 1.5)
            g = min(max(buf[y, x, 1], -0.5), 1.5)
            b = min(max(buf[y, x, 2], -0.5), 1.5)
            k = _plus_proche(r, g, b, pal, poids[0], poids[1], poids[2])
            out[y, x] = k
            er = (r - pal[k, 0]) * force
            eg = (g - pal[k, 1]) * force
            eb = (b - pal[k, 2]) * force
            for j in range(n):
                dx = -kx[j] if inverse else kx[j]
                nx = x + dx
                ny = y + ky[j]
                if 0 <= nx < w and ny < h:
                    p = kw[j]
                    buf[ny, nx, 0] += er * p
                    buf[ny, nx, 1] += eg * p
                    buf[ny, nx, 2] += eb * p
    return out


@compiler
def _tri_lignes(img, lum, seuil, inverse):
    """Tri de pixels : dans chaque ligne, les zones plus claires que le seuil sont triées."""
    h, w, _ = img.shape
    out = img.copy()
    for y in range(h):
        x = 0
        while x < w:
            if lum[y, x] >= seuil:
                debut = x
                while x < w and lum[y, x] >= seuil:
                    x += 1
                if x - debut > 1:
                    ordre = np.argsort(lum[y, debut:x])
                    n = x - debut
                    for i in range(n):
                        j = ordre[n - 1 - i] if inverse else ordre[i]
                        out[y, debut + i, 0] = img[y, debut + j, 0]
                        out[y, debut + i, 1] = img[y, debut + j, 1]
                        out[y, debut + i, 2] = img[y, debut + j, 2]
            else:
                x += 1
    return out


def _bayer(n):
    m = np.array([[0, 2], [3, 1]], dtype=np.float32)
    while m.shape[0] < n:
        m = np.block([[4 * m, 4 * m + 2], [4 * m + 3, 4 * m + 1]])
    return (m + 0.5) / m.size


def _rang_uniforme(v):
    """Transforme n'importe quelle carte en seuils uniformément répartis dans ]0,1[."""
    ordre = np.argsort(v.ravel(), kind="stable")
    rangs = np.empty(v.size, np.float32)
    rangs[ordre] = (np.arange(v.size) + 0.5) / v.size
    return rangs.reshape(v.shape)


@lru_cache(maxsize=1)
def _bruit_bleu():
    # Approximation du bruit bleu : bruit blanc filtré passe-haut puis classé.
    rng = np.random.default_rng(7)
    n = 64
    v = rng.random((n, n))
    f = np.fft.fftfreq(n)
    r = np.sqrt(f[:, None] ** 2 + f[None, :] ** 2)
    for _ in range(4):
        spectre = np.fft.fft2(v) * (1 - np.exp(-(r / 0.18) ** 2))
        v = _rang_uniforme(np.real(np.fft.ifft2(spectre)))
    return v.astype(np.float32)


@lru_cache(maxsize=32)
def _carte_seuils(algo, taille):
    if algo.startswith("Bayer"):
        return _bayer(int(algo.split()[1].split("×")[0]))
    if algo == "Bruit bleu":
        return _bruit_bleu()
    s = max(2, taille)
    y, x = np.mgrid[0:s, 0:s].astype(np.float32)
    u, v = (x + 0.5) / s, (y + 0.5) / s
    if algo == "Trame en points":
        carte = -(np.cos(2 * np.pi * u) + np.cos(2 * np.pi * v))
    elif algo == "Trame en lignes":
        carte = -np.cos(2 * np.pi * v) + 1e-3 * u
    elif algo == "Trame en croix":
        carte = np.minimum(np.abs(u - 0.5), np.abs(v - 0.5)) + 1e-3 * (u + v)
    elif algo == "Trame en vagues":
        s2 = s * 2  # motif plus large pour laisser la vague se dessiner
        y, x = np.mgrid[0:s2, 0:s2].astype(np.float32)
        u, v = (x + 0.5) / s2, (y + 0.5) / s2
        carte = -np.cos(2 * np.pi * (2 * v + 0.25 * np.sin(2 * np.pi * u))) + 1e-3 * u
    else:  # diagonale
        carte = -np.cos(2 * np.pi * (u + v)) + 1e-3 * u
    return _rang_uniforme(carte)


def _demi_teinte(img, pal, taille, angle_deg):
    """Trame d'imprimerie : des points ronds dont la taille suit la luminosité."""
    h, w, _ = img.shape
    lum = img @ LUMA
    cell = float(max(2, taille))
    flou = Image.fromarray(np.clip(lum * 255, 0, 255).astype(np.uint8))
    flou = np.asarray(flou.filter(ImageFilter.BoxBlur(cell / 2)), np.float32) / 255
    a = np.deg2rad(angle_deg)
    ca, sa = np.cos(a), np.sin(a)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    u = x * ca + y * sa
    v = -x * sa + y * ca
    cu = (np.floor(u / cell) + 0.5) * cell
    cv = (np.floor(v / cell) + 0.5) * cell
    dist = np.hypot(u - cu, v - cv)
    cx = np.clip(cu * ca - cv * sa, 0, w - 1).astype(np.int32)
    cy = np.clip(cu * sa + cv * ca, 0, h - 1).astype(np.int32)
    sombre = 1 - np.clip(flou[cy, cx], 0, 1)
    rayon = cell * np.sqrt(sombre / np.pi)
    luma_pal = pal @ LUMA
    fonce, clair = int(np.argmin(luma_pal)), int(np.argmax(luma_pal))
    return np.where(dist < rayon, fonce, clair).astype(np.int32)


# ---------------------------------------------------------------------------
# Réglages par défaut
# ---------------------------------------------------------------------------

REGLAGES_DEFAUT = {
    # Tramage
    "algorithme": "Floyd-Steinberg",
    "taille_pixel": 2,
    "force": 100,          # %
    "taille_motif": 6,
    "angle": 45,
    "zigzag": True,
    "bruit_avant": 0,
    # Couleurs
    "palette": PALETTES["Noir & blanc"],
    "perceptuel": True,
    "carte_degrade": False,  # répartit la luminosité sur toute la palette
    # Retouche
    "luminosite": 0,
    "contraste": 0,
    "gamma": 100,
    "saturation": 100,
    "teinte": 0,           # degrés
    "temperature": 0,
    "flou": 0,
    "nettete": 0,
    "encrage": 0,          # contours façon BD
    "inverser": False,
    # Déformations
    "miroir": "Aucun",
    "ondulation": 0,
    "frequence_onde": 6,
    "tri_pixels": 0,
    "tri_direction": "Horizontal",
    "tri_inverse": False,
    # Glitch
    "glitch": 0,           # tranches décalées
    "blocs": 0,            # blocs corrompus
    "etirement": 0,        # lignes étirées
    "graine": 1,
    "glitch_anime": True,
    # Optique
    "aberration": 0,       # aberration chromatique radiale
    "decalage_rvb": 0,
    "angle_rvb": 0,
    "bavure": 0,           # bavure des couleurs façon VHS
    "lueur": 0,
    "fuite_lumiere": 0,
    # Écran & texture
    "jpeg": 0,
    "posterisation": 0,
    "bande_vhs": 0,
    "scanlines": 0,
    "grille": 0,
    "courbure": 0,
    "vignette": 0,
    "grain": 0,
    # Export
    "echelle_export": 1,
}

# ---------------------------------------------------------------------------
# Étapes du pipeline
# ---------------------------------------------------------------------------


def _retouche(img, r, rng):
    if r["luminosite"]:
        img += r["luminosite"] / 200
    c = r["contraste"]
    if c:
        f = 1 + c / 100 if c < 0 else 1 + c / 50
        img -= 0.5
        img *= f
        img += 0.5
    if r["temperature"]:
        t = r["temperature"] / 100 * 0.12
        img[..., 0] += t
        img[..., 2] -= t
    if r["teinte"]:
        # Rotation de la teinte dans l'espace YIQ (rapide et sans conversion HSV)
        a = np.deg2rad(r["teinte"])
        vers = np.array([[0.299, 0.587, 0.114], [0.596, -0.274, -0.322],
                         [0.211, -0.523, 0.312]], np.float32)
        rot = np.array([[1, 0, 0], [0, np.cos(a), -np.sin(a)], [0, np.sin(a), np.cos(a)]],
                       np.float32)
        m = np.linalg.inv(vers) @ rot @ vers
        img[:] = img @ m.T.astype(np.float32)
    if r["saturation"] != 100:
        lum = (img @ LUMA)[..., None]
        img[:] = lum + (img - lum) * (r["saturation"] / 100)
    np.clip(img, 0, 1, out=img)
    if r["gamma"] != 100:
        np.power(img, 100 / r["gamma"], out=img)
    if r["encrage"]:
        lum = img @ LUMA
        gx = np.zeros_like(lum)
        gy = np.zeros_like(lum)
        gx[:, 1:-1] = lum[:, 2:] - lum[:, :-2]
        gy[1:-1] = lum[2:] - lum[:-2]
        bords = np.clip(np.hypot(gx, gy) * 4, 0, 1) * (r["encrage"] / 100)
        img *= (1 - bords)[..., None]
    if r["inverser"]:
        img[:] = 1 - img
    if r["bruit_avant"]:
        img += (rng.random(img.shape[:2], np.float32)[..., None] - 0.5) * (r["bruit_avant"] / 100)
    return img


def _deformations(img, r, frame):
    h, w, _ = img.shape
    m = r["miroir"]
    if m == "Gauche → droite" or m == "Kaléidoscope":
        img[:, w - w // 2:] = img[:, :w // 2][:, ::-1]
    elif m == "Droite → gauche":
        img[:, :w // 2] = img[:, w - w // 2:][:, ::-1]
    if m == "Haut → bas" or m == "Kaléidoscope":
        img[h - h // 2:] = img[:h // 2][::-1]

    if r["ondulation"]:
        amp = r["ondulation"] / 100 * w * 0.06
        periode = h / max(1, r["frequence_onde"])
        phase = frame * 0.2 if r["glitch_anime"] else 0
        dx = (amp * np.sin(2 * np.pi * np.arange(h) / periode + phase)).astype(np.int32)
        cols = np.clip(np.arange(w)[None, :] - dx[:, None], 0, w - 1)
        img = np.take_along_axis(img, cols[..., None].repeat(3, axis=2), axis=1)

    if r["tri_pixels"]:
        vertical = r["tri_direction"] == "Vertical"
        src = np.ascontiguousarray(img.transpose(1, 0, 2) if vertical else img)
        lum = np.ascontiguousarray(src @ LUMA)
        seuil = np.float32(1 - r["tri_pixels"] / 100)
        src = _tri_lignes(src, lum, seuil, bool(r["tri_inverse"]))
        img = np.ascontiguousarray(src.transpose(1, 0, 2) if vertical else src)
    return img


def _carte_degrade(img, pal):
    """Remplace chaque pixel par la couleur du dégradé de la palette correspondant à sa luminosité."""
    ordre = np.argsort(pal @ LUMA)
    rampe = pal[ordre]
    t = np.clip(img @ LUMA, 0, 1) * (len(rampe) - 1)
    i = np.minimum(t.astype(np.int32), len(rampe) - 2)
    f = (t - i)[..., None]
    return rampe[i] * (1 - f) + rampe[i + 1] * f


def _tramer(img, r, rng):
    pal = np.array([hex_vers_rgb(c) for c in r["palette"]], np.float32) / 255
    if len(pal) < 2:
        pal = np.array([[0, 0, 0], [1, 1, 1]], np.float32)
    if r["carte_degrade"]:
        img = np.ascontiguousarray(_carte_degrade(img, pal), np.float32)
    poids = LUMA * 3 if r["perceptuel"] else np.ones(3, np.float32)
    algo = r["algorithme"]
    force = r["force"] / 100

    if algo in NOYAUX:
        noyau, div = NOYAUX[algo]
        k = np.array(noyau, np.int32)
        idx = _diffusion_erreur(img, pal, k[:, 0].copy(), k[:, 1].copy(),
                                (k[:, 2] / div).astype(np.float32), np.float32(force),
                                bool(r["zigzag"]), poids)
    elif algo == "Demi-teinte (points ronds)":
        idx = _demi_teinte(img, pal, r["taille_motif"], r["angle"])
    elif algo == "Aucun (seuil)":
        idx = _carte_plus_proche(img, pal, poids)
    else:
        if algo == "Bruit aléatoire":
            carte = rng.random(img.shape[:2], np.float32)
        else:
            carte = _carte_seuils(algo, int(r["taille_motif"]))
        # L'écart entre deux couleurs voisines diminue quand la palette grandit
        ecart = np.float32(force * 1.26 / len(pal) ** (1 / 3))
        idx = _ordonne(img, pal, carte, ecart, poids)

    return (pal[idx] * 255 + 0.5).astype(np.uint8)


@lru_cache(maxsize=8)
def _carte_radiale(h, w, k):
    """Coordonnées source pour une déformation radiale (aberration, courbure)."""
    y = np.linspace(-1, 1, h, dtype=np.float32)[:, None]
    x = np.linspace(-1, 1, w, dtype=np.float32)[None, :]
    f = 1 + k * (x * x + y * y)
    sx = (x * f + 1) / 2 * (w - 1)
    sy = (y * f + 1) / 2 * (h - 1)
    dehors = (sx < 0) | (sx > w - 1) | (sy < 0) | (sy > h - 1)
    return (np.clip(sy, 0, h - 1).astype(np.int32), np.clip(sx, 0, w - 1).astype(np.int32),
            dehors)


@lru_cache(maxsize=4)
def _carte_vignette(h, w):
    y = np.linspace(-1, 1, h, dtype=np.float32)[:, None]
    x = np.linspace(-1, 1, w, dtype=np.float32)[None, :]
    return np.clip((x * x + y * y) / 2, 0, 1)


def _agrandir(a, w, h):
    """Agrandit une petite carte lisse (float) à la taille voulue."""
    return np.asarray(Image.fromarray(a.astype(np.float32), "F")
                      .resize((w, h), Image.Resampling.BILINEAR))


def _en_octets(a):
    return _en_octets_rapide(np.ascontiguousarray(a, np.float32))


def _glitch(out, r, rng, frame):
    h, w, _ = out.shape
    if r["glitch"]:
        g = r["glitch"] / 100
        for _ in range(int(1 + g * 14)):
            y0 = int(rng.integers(0, h))
            hh = int(rng.integers(2, max(3, int(h * 0.08 * g) + 3)))
            dx = int(rng.normal(0, w * 0.06 * g))
            out[y0:y0 + hh] = np.roll(out[y0:y0 + hh], dx, axis=1)
            if rng.random() < g * 0.5:  # bande aux canaux inversés
                out[y0:y0 + hh] = out[y0:y0 + hh][..., ::-1]

    if r["blocs"]:
        b = r["blocs"] / 100
        for _ in range(int(2 + b * 30)):
            bw = int(rng.integers(max(2, w // 50), max(3, int(w * 0.25 * b) + 4)))
            bh = int(rng.integers(max(2, h // 80), max(3, int(h * 0.1 * b) + 4)))
            x0, y0 = int(rng.integers(0, max(1, w - bw))), int(rng.integers(0, max(1, h - bh)))
            bloc = out[y0:y0 + bh, x0:x0 + bw]
            choix = rng.random()
            if choix < 0.35:  # bloc copié d'ailleurs
                sx = int(rng.integers(0, max(1, w - bw)))
                sy = int(rng.integers(0, max(1, h - bh)))
                bloc[:] = out[sy:sy + bh, sx:sx + bw]
            elif choix < 0.6:  # canaux mélangés
                bloc[:] = bloc[..., rng.permutation(3)]
            elif choix < 0.8:  # première colonne étalée
                bloc[:] = bloc[:, :1]
            else:  # couleur saturée
                bloc[:] = np.clip(bloc * np.array(rng.choice([[1.6, 0.3, 0.3], [0.3, 1.6, 1.2],
                                                              [1.4, 0.2, 1.6]]), np.float32), 0, 1)

    if r["etirement"]:
        e = r["etirement"] / 100
        for _ in range(int(1 + e * 6)):
            y0 = int(rng.integers(0, h))
            hh = int(rng.integers(4, max(5, int(h * 0.15 * e) + 5)))
            out[y0:y0 + hh] = out[y0:y0 + 1]
    return out


def _optique(out, r, rng):
    h, w, _ = out.shape
    if r["aberration"]:
        k = r["aberration"] / 100 * 0.03
        yr, xr, _ = _carte_radiale(h, w, round(-k, 5))
        yb, xb, _ = _carte_radiale(h, w, round(k, 5))
        src = out.copy()
        _remap_canal(src, 0, yr, xr, out)
        _remap_canal(src, 2, yb, xb, out)

    if r["decalage_rvb"]:
        a = np.deg2rad(r["angle_rvb"])
        d = r["decalage_rvb"]
        dx, dy = int(round(np.cos(a) * d)), int(round(np.sin(a) * d))
        out[..., 0] = np.roll(out[..., 0], (dy, dx), axis=(0, 1))
        out[..., 2] = np.roll(out[..., 2], (-dy, -dx), axis=(0, 1))

    if r["bavure"]:
        # Comme une vieille cassette : la couleur bave vers la droite, la luminosité reste nette
        lum = (out @ LUMA)[..., None]
        chroma = out - lum
        rayon = int(1 + r["bavure"] / 100 * w * 0.012)
        chroma = np.roll(_flou_lignes(np.ascontiguousarray(chroma), rayon), rayon // 2, axis=1)
        out = lum + chroma * (1 + r["bavure"] / 200)

    if r["lueur"]:
        # Le halo est flou de toute façon : on le calcule en quart de résolution
        petite = Image.fromarray(_en_octets(out)).resize((max(1, w // 4), max(1, h // 4)),
                                                          Image.Resampling.BOX)
        petite = petite.filter(ImageFilter.GaussianBlur(max(1, min(h, w) / 240)))
        b = np.asarray(petite.resize((w, h), Image.Resampling.BILINEAR))
        out = np.ascontiguousarray(out)
        _superposer(out, b, np.float32(r["lueur"] / 100 * 1.5 / 255), 1.0, 1.0, 1.0)

    if r["fuite_lumiere"]:
        cx, cy = rng.uniform(-0.2, 1.2), rng.uniform(-0.2, 1.2)
        couleur = np.array(rng.choice([[1.0, 0.45, 0.2], [1.0, 0.25, 0.45], [1.0, 0.75, 0.3]]),
                           np.float32)
        ph, pw = max(2, h // 8), max(2, w // 8)
        y = np.linspace(0, 1, ph, dtype=np.float32)[:, None]
        x = np.linspace(0, 1, pw, dtype=np.float32)[None, :]
        masque = _agrandir(np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / 0.12), w, h)
        out = np.ascontiguousarray(out)
        _superposer(out, masque[..., None], np.float32(r["fuite_lumiere"] / 100),
                    *[float(c) for c in couleur])
    return out


def _ecran(out, r, rng, frame, taille_pixel):
    h, w, _ = out.shape
    if r["jpeg"]:
        qualite = max(1, int(60 - r["jpeg"] * 0.59))
        tampon = io.BytesIO()
        Image.fromarray(_en_octets(out)).save(
            tampon, "JPEG", quality=qualite, subsampling=2)
        out = np.asarray(Image.open(tampon), np.float32) / 255

    if r["posterisation"]:
        niveaux = max(2, int(round(32 - r["posterisation"] / 100 * 30)))
        out = np.round(np.clip(out, 0, 1) * (niveaux - 1)) / (niveaux - 1)

    if r["bande_vhs"]:
        v = r["bande_vhs"] / 100
        hb = max(4, int(h * (0.03 + 0.08 * v)))
        y0 = int((frame * h * 0.013 + rng.integers(0, h)) % h)
        lignes = np.arange(y0, min(h, y0 + hb))
        if len(lignes):
            for y in lignes:
                out[y] = np.roll(out[y], int(rng.normal(0, w * 0.01 * v)), axis=0)
            out[lignes] += rng.normal(0, 0.25 * v, (len(lignes), w, 1)).astype(np.float32)
            out[lignes] *= 1 + 0.25 * v
        # quelques parasites blancs
        n = int(v * 40)
        ys, xs = rng.integers(0, h, n), rng.integers(0, w, n)
        for y, x in zip(ys, xs):
            out[y, x:x + int(rng.integers(3, 20))] = 1

    if r["scanlines"]:
        periode = max(2, taille_pixel)
        lignes = (np.arange(h) % periode) == periode - 1
        out[lignes] *= 1 - r["scanlines"] / 100 * 0.85

    if r["grille"]:
        m = 1 - r["grille"] / 100 * 0.65
        motif = np.array([[1, m, m], [m, 1, m], [m, m, 1]], np.float32)
        out *= motif[np.arange(w) % 3][None, :, :]

    if r["courbure"]:
        yy, xx, dehors = _carte_radiale(h, w, round(r["courbure"] / 100 * 0.3, 4))
        out = _remap(np.ascontiguousarray(out), yy, xx, dehors)

    if r["vignette"]:
        out *= (1 - (r["vignette"] / 100 * 0.85) * _carte_vignette(h, w))[..., None]

    if r["grain"]:
        bruit = rng.standard_normal((h, w), dtype=np.float32)
        bruit *= r["grain"] / 100 * 0.15
        out += bruit[..., None]
    return out


GLITCH = ("glitch", "blocs", "etirement")
OPTIQUE = ("aberration", "decalage_rvb", "bavure", "lueur", "fuite_lumiere")
ECRAN = ("jpeg", "posterisation", "bande_vhs", "scanlines", "grille", "courbure",
         "vignette", "grain")


def traiter(src, reglages, frame=0, avec_echelle=False):
    """Applique tout le pipeline à une image RVB uint8 (H×W×3)."""
    r = {**REGLAGES_DEFAUT, **reglages}
    rng = np.random.default_rng(frame)  # même frame => même grain
    # Le glitch suit sa propre graine : figé, ou différent à chaque image
    graine = int(r["graine"]) * 100003 + (frame if r["glitch_anime"] else 0)
    rng_glitch = np.random.default_rng(graine)

    h, w, _ = src.shape
    p = max(1, int(r["taille_pixel"]))
    pw, ph = max(1, w // p), max(1, h // p)

    petite = Image.fromarray(src)
    if p > 1:
        petite = petite.resize((pw, ph), Image.Resampling.BOX)
    if r["flou"]:
        petite = petite.filter(ImageFilter.GaussianBlur(r["flou"] / 100 * 6))
    if r["nettete"]:
        petite = petite.filter(ImageFilter.UnsharpMask(radius=1.5, percent=int(r["nettete"]),
                                                       threshold=0))
    img = np.array(petite, np.float32) / 255
    img = _retouche(img, r, rng)
    img = _deformations(np.ascontiguousarray(img), r, frame)
    tramee = _tramer(np.ascontiguousarray(img, np.float32), r, rng)

    # Retour à la taille d'origine en gardant des pixels bien nets
    echelle = p * (int(r["echelle_export"]) if avec_echelle else 1)
    if echelle > 1:
        th, tw, _ = tramee.shape
        tramee = np.asarray(Image.fromarray(tramee).resize((tw * echelle, th * echelle),
                                                           Image.Resampling.NEAREST))

    if not any(r[k] for k in GLITCH + OPTIQUE + ECRAN):
        return tramee
    out = tramee.astype(np.float32) / 255
    out = _glitch(out, r, rng_glitch, frame)
    out = _optique(out, r, rng_glitch)
    out = _ecran(out, r, rng, frame, echelle)
    return _en_octets(out)


def prechauffer():
    """Compile les fonctions Numba une première fois (quelques secondes au 1er lancement)."""
    img = (np.random.default_rng(0).random((16, 16, 3)) * 255).astype(np.uint8)
    for algo in ("Floyd-Steinberg", "Bayer 4×4", "Aucun (seuil)"):
        traiter(img, {"algorithme": algo, "taille_pixel": 1, "tri_pixels": 50,
                      "aberration": 20, "courbure": 20, "bavure": 20})

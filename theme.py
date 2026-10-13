"""
Crunch Crab — thème visuel : couleurs, polices, feuille de style Qt et icônes.

Direction artistique : une « console de mixage de pixels ». Fond presque noir tramé,
cartes aux bords fins, dégradé corail → rose, police pixel pour les titres et
les repères, police à chasse fixe pour les valeurs.
"""

import os
import sys
from functools import lru_cache

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QLinearGradient, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

MAC = sys.platform == "darwin"
WINDOWS = sys.platform.startswith("win")
DOSSIER = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

# ---------------------------------------------------------------------------
# Couleurs
# ---------------------------------------------------------------------------

FOND = "#060508"           # fenêtre
SURFACE = "#0c0a10"        # cartes (aperçu, panneau)
CHAMP = "#15121a"          # champs, boutons
CHAMP_SURVOL = "#1d1924"
BORD = "#1f1b26"
BORD_FORT = "#2f2938"
TEXTE = "#f4eee8"
DISCRET = "#8b8392"
TRES_DISCRET = "#524b5a"
ACCENT = "#ff5b3a"         # le corail historique de Crunch Crab
ACCENT_CLAIR = "#ff8a63"
ROSE = "#ff3d8b"
AMBRE = "#ffb547"
VERT = "#bef264"
ENCRE = "#1a0710"          # texte posé sur le dégradé

# Dégradé signature (corail → rose), du plus chaud au plus froid
DEGRADE = ("#ff7a3d", "#ff4f62", "#ff3d9a")


def couleur_degrade(t):
    """Couleur du dégradé signature à la position t (0 → 1)."""
    t = min(1.0, max(0.0, t))
    if t < 0.5:
        a, b, u = DEGRADE[0], DEGRADE[1], t / 0.5
    else:
        a, b, u = DEGRADE[1], DEGRADE[2], (t - 0.5) / 0.5
    ca, cb = QColor(a), QColor(b)
    return QColor(round(ca.red() + (cb.red() - ca.red()) * u),
                  round(ca.green() + (cb.green() - ca.green()) * u),
                  round(ca.blue() + (cb.blue() - ca.blue()) * u))


def degrade(rect):
    """Le dégradé signature, en diagonale sur un rectangle (pour QPainter)."""
    g = QLinearGradient(rect.topLeft(), rect.bottomRight())
    for pos, c in zip((0, 0.55, 1), DEGRADE):
        g.setColorAt(pos, QColor(c))
    return g


QSS_DEGRADE = (f"qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {DEGRADE[0]}, "
               f"stop:0.55 {DEGRADE[1]}, stop:1 {DEGRADE[2]})")

# ---------------------------------------------------------------------------
# Polices
# ---------------------------------------------------------------------------
# Silkscreen (licence OFL, fournie dans polices/) pour les titres : elle est nette
# à 8, 16, 24 ou 32 px. Les valeurs utilisent une police à chasse fixe du système.

PIXEL = "Silkscreen"
MONO = "Menlo" if MAC else ("Consolas" if WINDOWS else "DejaVu Sans Mono")


def charger_polices():
    """À appeler une fois après la création de QApplication."""
    global PIXEL
    for nom in ("Silkscreen-Regular.ttf", "Silkscreen-Bold.ttf"):
        QFontDatabase.addApplicationFont(os.path.join(DOSSIER, "polices", nom))
    if PIXEL not in QFontDatabase.families():
        PIXEL = MONO  # police introuvable : on retombe sur la chasse fixe


def police_pixel(taille=8, gras=False):
    f = QFont(PIXEL)
    f.setPixelSize(taille)
    f.setBold(gras)
    f.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    return f


def police_mono(taille=11, gras=False):
    f = QFont(MONO)
    f.setPixelSize(taille)
    f.setBold(gras)
    return f


# ---------------------------------------------------------------------------
# Feuille de style
# ---------------------------------------------------------------------------

def feuille_de_style():
    return f"""
* {{ color: {TEXTE}; font-size: 12px; }}
QMainWindow, QWidget#racine {{ background: {FOND}; }}
QWidget#carte {{ background: {SURFACE}; border: 1px solid {BORD}; border-radius: 18px; }}
QScrollArea#defile, QWidget#panneauInterieur {{ background: transparent; border: none; }}
QScrollArea#defile > QWidget > QWidget {{ background: transparent; }}

QLabel#marque {{ font-family: "{PIXEL}"; font-size: 16px; }}
QLabel#version {{ font-family: "{PIXEL}"; font-size: 8px; color: {DISCRET};
                  border: 1px solid {BORD_FORT}; border-radius: 5px; padding: 3px 5px 2px 5px; }}
QLabel#etiquette {{ font-size: 12.5px; }}
QLabel#aide {{ color: {DISCRET}; font-size: 11px; }}
QLabel#sousTitre {{ color: {DISCRET}; font-size: 11.5px; padding: 0 18px 8px 18px; }}
QLabel#valeur {{ font-family: "{MONO}"; font-size: 11px; color: {DISCRET};
                 padding: 1px 6px; border-radius: 5px; }}
QLabel#valeur[modifie="true"] {{ color: {ACCENT_CLAIR}; background: rgba(255, 91, 58, 0.12); }}
QLabel#info {{ font-family: "{MONO}"; font-size: 11px; color: {DISCRET}; }}

QPushButton {{
    background: {CHAMP}; border: 1px solid {BORD}; border-radius: 10px; padding: 6px 12px;
}}
QPushButton:hover {{ background: {CHAMP_SURVOL}; border-color: {BORD_FORT}; }}
QPushButton:pressed {{ background: #241f2c; }}
QPushButton:disabled {{ color: {TRES_DISCRET}; background: transparent; }}
QPushButton#principal {{ background: {QSS_DEGRADE}; color: {ENCRE}; border: none;
                         font-weight: 700; padding: 7px 16px; }}
QPushButton#principal:hover {{ background: {QSS_DEGRADE}; border: 1px solid rgba(255,255,255,0.45); }}
QPushButton#principal:disabled {{ background: #24131a; color: #6b3a45; }}
QPushButton#icone {{ padding: 6px; min-width: 18px; }}
QPushButton#fantome {{ background: transparent; border: 1px solid transparent; }}
QPushButton#fantome:hover {{ background: {CHAMP}; border-color: {BORD}; }}
QPushButton#segment {{ background: transparent; border: none; border-radius: 7px; padding: 4px 9px;
                       font-family: "{MONO}"; font-size: 11px; color: {DISCRET}; }}
QPushButton#segment:hover {{ color: {TEXTE}; }}
QPushButton#segment:checked {{ background: {CHAMP_SURVOL}; color: {TEXTE}; }}
QPushButton#bascule:checked {{ background: rgba(255, 91, 58, 0.14); border-color: {ACCENT};
                               color: {ACCENT_CLAIR}; }}
QPushButton#fleche {{ background: transparent; border: 1px solid {BORD}; border-radius: 9px;
                      padding: 0; min-width: 28px; max-width: 28px; }}
QPushButton#fleche:hover {{ background: {CHAMP}; border-color: {BORD_FORT}; }}
QPushButton#reinit {{ background: transparent; border: none; padding: 4px; border-radius: 7px; }}
QPushButton#reinit:hover {{ background: {CHAMP}; }}
QPushButton#de {{ background: transparent; border: none; padding: 0 4px; }}
QPushButton#lecture {{ background: {QSS_DEGRADE}; border: none; border-radius: 15px;
                       min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px; padding: 0; }}

QWidget#groupe {{ background: {CHAMP}; border: 1px solid {BORD}; border-radius: 9px; }}

QComboBox {{
    background: {CHAMP}; border: 1px solid {BORD}; border-radius: 9px; padding: 6px 10px;
}}
QComboBox:hover {{ border-color: {BORD_FORT}; background: {CHAMP_SURVOL}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: none; width: 0; }}
QComboBox QAbstractItemView {{
    background: #121017; border: 1px solid {BORD_FORT}; border-radius: 8px; padding: 4px;
    selection-background-color: {ACCENT}; selection-color: {ENCRE}; outline: none;
}}

QSlider::groove:horizontal {{ height: 4px; background: {BORD_FORT}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {QSS_DEGRADE}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {TEXTE}; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px;
}}

QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px 2px 4px 0; }}
QScrollBar::handle:vertical {{ background: {BORD_FORT}; border-radius: 3px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {TRES_DISCRET}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QProgressDialog, QMessageBox {{ background: {SURFACE}; }}
QProgressBar {{ background: {CHAMP}; border: none; border-radius: 4px; height: 8px;
                text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {QSS_DEGRADE}; border-radius: 4px; }}
QToolTip {{ background: #141118; color: {TEXTE}; border: 1px solid {BORD_FORT}; padding: 6px; }}
QMenu {{ background: #121017; border: 1px solid {BORD_FORT}; padding: 4px; }}
QMenu::item {{ padding: 5px 18px; border-radius: 5px; }}
QMenu::item:selected {{ background: {ACCENT}; color: {ENCRE}; }}
"""


# ---------------------------------------------------------------------------
# Icônes (tracés SVG sur une grille de 24 px, colorés à la demande)
# ---------------------------------------------------------------------------

_ICONES = {
    "ouvrir": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "annuler": '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    "retablir": '<path d="m15 14 5-5-5-5"/><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13"/>',
    "de": ('<rect x="3.5" y="3.5" width="17" height="17" rx="4"/>'
           '<g fill="@" stroke="none"><circle cx="8.5" cy="8.5" r="1.4"/><circle cx="15.5" cy="8.5" r="1.4"/>'
           '<circle cx="12" cy="12" r="1.4"/><circle cx="8.5" cy="15.5" r="1.4"/>'
           '<circle cx="15.5" cy="15.5" r="1.4"/></g>'),
    "exporter": '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',
    "lecture": '<path d="M8 5v14l11-7z" fill="@"/>',
    "pause": '<g fill="@" stroke="none"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></g>',
    "comparer": '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M12 2v20"/>',
    "reinit": '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/>',
    "bas": '<path d="m6 9 6 6 6-6"/>',
    "droite": '<path d="m9 6 6 6-6 6"/>',
    "gauche": '<path d="m15 6-6 6 6 6"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
}


@lru_cache(maxsize=None)
def pixmap_icone(nom, couleur=TEXTE, taille=16, epaisseur=1.8):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           f'stroke="{couleur}" stroke-width="{epaisseur}" stroke-linecap="round" '
           f'stroke-linejoin="round">{_ICONES[nom].replace("@", couleur)}</svg>')
    echelle = 3  # net sur les écrans Retina comme sur les autres
    pix = QPixmap(taille * echelle, taille * echelle)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    QSvgRenderer(QByteArray(svg.encode())).render(p, QRectF(0, 0, pix.width(), pix.height()))
    p.end()
    pix.setDevicePixelRatio(echelle)
    return pix


def icone(nom, couleur=TEXTE, taille=16):
    ic = QIcon(pixmap_icone(nom, couleur, taille))
    ic.addPixmap(pixmap_icone(nom, TRES_DISCRET, taille), QIcon.Mode.Disabled)
    return ic


# ---------------------------------------------------------------------------
# Texture du fond : une trame de Bayer à peine visible (le motif qui a fait le tramage)
# ---------------------------------------------------------------------------

_BAYER_4 = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))


@lru_cache(maxsize=None)
def texture_trame(couleur=SURFACE):
    """Carreau de 16 × 16 px : quelques points clairs placés selon une matrice de Bayer."""
    pix = QPixmap(16, 16)
    pix.fill(QColor(couleur))
    p = QPainter(pix)
    point = QColor(255, 255, 255, 9)
    for y in range(4):
        for x in range(4):
            if _BAYER_4[y][x] < 3:
                p.fillRect(QRectF(x * 4 + 1, y * 4 + 1, 1, 1), point)
    p.end()
    return pix


def point_lumineux(p, centre, rayon, couleur, allume=True):
    """Petit voyant rond, avec un halo quand il est allumé."""
    c = QColor(couleur)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    if allume:
        halo = QColor(c)
        halo.setAlpha(60)
        p.setBrush(halo)
        p.drawEllipse(QPointF(centre), rayon * 2.2, rayon * 2.2)
    else:
        c = QColor(BORD_FORT)
    p.setBrush(c)
    p.drawEllipse(QPointF(centre), rayon, rayon)
    p.restore()

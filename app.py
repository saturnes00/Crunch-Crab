"""
Crunch Crab — interface graphique.

Organisation :
  - Vue          : la grande zone d'aperçu (zoom, déplacement, comparaison, glisser-déposer)
  - Curseur, ... : les petits composants de réglage du panneau de droite
  - Rendu        : calcule l'aperçu en arrière-plan pour ne jamais figer l'interface
  - Lecture      : lit la vidéo en temps réel
  - Export       : écrit le fichier final avec une barre de progression
  - Fenetre      : assemble le tout
"""

import json
import os
import random
import sys
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image, ImageOps
from PySide6.QtCore import QPointF, QRectF, QSettings, Qt, QThread, QTimer, Signal
from PySide6.QtGui import (QAction, QColor, QFont, QIcon, QImage, QKeySequence, QPainter,
                           QPen, QPixmap, QShortcut)
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QFileDialog,
                               QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QProgressDialog, QPushButton, QScrollArea,
                               QSizePolicy, QSlider, QVBoxLayout, QWidget)

import moteur
import video

# Dans l'app empaquetée (PyInstaller), les fichiers sont dans sys._MEIPASS
DOSSIER = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
NOM = "Crunch Crab"
MAC = sys.platform == "darwin"
WINDOWS = sys.platform.startswith("win")

# Les raccourcis s'affichent à la façon de chaque système
CMD = "⌘" if MAC else "Ctrl+"
MAJ_CMD = "⇧⌘" if MAC else "Ctrl+Maj+"
GESTIONNAIRE = "le Finder" if MAC else ("l'Explorateur" if WINDOWS else "le dossier")

# ---------------------------------------------------------------------------
# Thème : très sombre, chaud, avec un accent corail
# ---------------------------------------------------------------------------

ACCENT = "#ff5b3a"
ACCENT_CLAIR = "#ff7d61"
FOND = "#060607"
PANNEAU = "#0b0b0d"
CHAMP = "#121215"
CHAMP_SURVOL = "#18181c"
BORD = "#1b1b20"
TEXTE = "#ece7e1"
DISCRET = "#77716b"
TRES_DISCRET = "#46423e"
TITRES = "Avenir Next" if MAC else ("Segoe UI" if WINDOWS else "Noto Sans")
MONO = "Menlo" if MAC else ("Consolas" if WINDOWS else "DejaVu Sans Mono")

STYLE = f"""
* {{ color: {TEXTE}; font-size: 12px; }}
QMainWindow, QWidget#racine {{ background: {FOND}; }}
QWidget#panneau, QWidget#panneauInterieur, QScrollArea#defile {{ background: {PANNEAU}; border: none; }}
QWidget#barre, QWidget#transport {{ background: {PANNEAU}; }}
QFrame#separateur {{ background: {BORD}; max-height: 1px; min-height: 1px; }}
QFrame#separateurV {{ background: {BORD}; max-width: 1px; min-width: 1px; }}

QLabel#marque {{ font-family: "{TITRES}"; font-size: 16px; font-weight: 700; }}
QLabel#sousTitre {{ color: {DISCRET}; font-size: 11px; font-style: italic; padding: 0 16px 6px 16px; }}
QLabel#valeur {{ color: {DISCRET}; font-family: {MONO}; font-size: 11px; }}
QLabel#info {{ color: {DISCRET}; font-family: {MONO}; font-size: 11px; }}

QPushButton {{
    background: {CHAMP}; border: 1px solid {BORD}; border-radius: 8px; padding: 6px 12px;
}}
QPushButton:hover {{ background: {CHAMP_SURVOL}; border-color: #2a2a30; }}
QPushButton:pressed {{ background: #1f1f24; }}
QPushButton:disabled {{ color: {TRES_DISCRET}; }}
QPushButton#principal {{ background: {ACCENT}; color: #1a0904; border: none; font-weight: 700;
                         padding: 7px 16px; }}
QPushButton#principal:hover {{ background: {ACCENT_CLAIR}; }}
QPushButton#principal:disabled {{ background: #2b1510; color: #6e3a2d; }}
QPushButton#icone {{ padding: 5px 9px; font-size: 14px; }}
QPushButton#segment {{ padding: 4px 9px; border-radius: 6px; font-family: {MONO}; font-size: 11px; }}
QPushButton#segment:checked {{ background: {ACCENT}; color: #1a0904; border: none; }}
QPushButton#bascule:checked {{ background: #2a120c; border-color: {ACCENT}; color: {ACCENT_CLAIR}; }}
QPushButton#section {{
    background: transparent; border: none; text-align: left; padding: 13px 0 4px 16px;
    font-family: "{TITRES}"; font-size: 13px; font-weight: 600; color: {TEXTE};
}}
QPushButton#section:hover {{ color: {ACCENT_CLAIR}; }}
QPushButton#reinit {{ background: transparent; border: none; color: {TRES_DISCRET};
                      padding: 13px 14px 4px 6px; font-size: 13px; }}
QPushButton#reinit:hover {{ color: {ACCENT_CLAIR}; }}
QPushButton#de {{ background: transparent; border: none; padding: 0 2px; font-size: 13px; }}
QPushButton#lecture {{ border-radius: 15px; min-width: 30px; max-width: 30px;
                       min-height: 30px; max-height: 30px; padding: 0; font-size: 12px; }}

QComboBox {{
    background: {CHAMP}; border: 1px solid {BORD}; border-radius: 8px; padding: 5px 10px;
}}
QComboBox:hover {{ border-color: #2c2c33; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: #101013; border: 1px solid {BORD}; selection-background-color: {ACCENT};
    selection-color: #1a0904; padding: 4px; outline: none;
}}

QSlider::groove:horizontal {{ height: 3px; background: #1e1e23; border-radius: 1px; }}
QSlider::sub-page:horizontal {{ background: #b8442c; border-radius: 1px; }}
QSlider::handle:horizontal {{
    background: {TEXTE}; width: 12px; height: 12px; margin: -5px 0; border-radius: 6px;
}}
QSlider::handle:horizontal:hover {{ background: #ffffff; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 26px; height: 14px; border-radius: 7px; background: #1e1e23; border: 1px solid {BORD};
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QScrollBar:vertical {{ background: transparent; width: 7px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #222227; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QProgressDialog, QMessageBox {{ background: {PANNEAU}; }}
QProgressBar {{ background: #1a1a1e; border: none; border-radius: 4px; height: 8px;
                text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
QToolTip {{ background: #151518; color: {TEXTE}; border: 1px solid {BORD}; padding: 5px; }}
"""

# La mascotte, en pixel art (X = carapace, O = œil)
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

ASTUCES = [
    "double-clique sur un réglage pour le remettre à zéro.",
    f"{CMD}Z pour annuler, {MAJ_CMD}Z pour rétablir. Tu peux tout tester, rien n'est grave.",
    "le bouton 🎲 tire un look au hasard. Des fois, ça tombe super bien.",
    "appuie sur C pour comparer avant et après.",
    "pince le trackpad pour zoomer sur les pixels." if MAC else
    "Ctrl + molette pour zoomer sur les pixels.",
    "« Répartir sur la palette » fait des bichromies super facilement.",
    "le tri de pixels rend bien autour de 40 %.",
    f"garde tes looks préférés avec {CMD}S, comme ça tu les retrouves quand tu veux.",
]

# Styles prêts à l'emploi (seuls les réglages listés changent, le reste revient par défaut)
STYLES = {
    "Game Boy": {"palette_nom": "Game Boy", "algorithme": "Bayer 4×4", "taille_pixel": 3,
                 "contraste": 15},
    "Macintosh 1984": {"palette_nom": "Noir & blanc", "algorithme": "Atkinson (Mac classique)",
                       "taille_pixel": 2},
    "Journal imprimé": {"palette_nom": "Encre & papier",
                        "algorithme": "Demi-teinte (points ronds)", "taille_pixel": 1,
                        "taille_motif": 7, "angle": 45, "grain": 8},
    "Bande dessinée": {"palette_nom": "Encre & papier", "algorithme": "Trame en points",
                       "taille_pixel": 1, "taille_motif": 5, "encrage": 75, "contraste": 25},
    "PICO-8": {"palette_nom": "PICO-8", "algorithme": "Bayer 8×8", "taille_pixel": 4,
               "saturation": 130},
    "Néon CRT": {"palette_nom": "Néon", "algorithme": "Floyd-Steinberg", "taille_pixel": 3,
                 "scanlines": 50, "lueur": 45, "decalage_rvb": 2, "contraste": 20,
                 "vignette": 45, "courbure": 30, "grille": 25},
    "Cassette VHS": {"palette_nom": "Coucher de soleil", "algorithme": "Bruit bleu",
                     "taille_pixel": 2, "bavure": 60, "bande_vhs": 45, "decalage_rvb": 3,
                     "grain": 20, "scanlines": 25},
    "Datamosh": {"palette_nom": "Télétexte", "algorithme": "Bayer 4×4", "taille_pixel": 2,
                 "blocs": 55, "glitch": 40, "etirement": 30, "tri_pixels": 35},
    "Tri de pixels": {"palette_nom": "Néon", "algorithme": "Sierra Lite", "taille_pixel": 2,
                      "tri_pixels": 55, "lueur": 20},
    "Abysses": {"palette_nom": "Abysses", "algorithme": "Atkinson (Mac classique)",
                "taille_pixel": 2, "aberration": 40, "lueur": 30, "vignette": 55},
    "Rêve fiévreux": {"palette_nom": "Coucher de soleil", "carte_degrade": True,
                      "algorithme": "Trame en vagues", "taille_motif": 5, "taille_pixel": 2,
                      "ondulation": 35, "aberration": 50, "lueur": 30},
    "Risographie": {"palette_nom": "Risographie", "algorithme": "Trame en points",
                    "taille_pixel": 1, "taille_motif": 5, "grain": 12},
    "Écran ambre": {"palette_nom": "Écran ambre", "algorithme": "Stucki", "taille_pixel": 2,
                    "scanlines": 60, "lueur": 35, "vignette": 30, "courbure": 40},
    "Terminal vert": {"palette_nom": "Phosphore vert", "algorithme": "Trame en lignes",
                      "taille_pixel": 2, "taille_motif": 3, "lueur": 40, "scanlines": 40},
    "Commodore 64": {"palette_nom": "Commodore 64", "algorithme": "Bayer 4×4",
                     "taille_pixel": 4, "saturation": 120},
}

# Ce que le dé a le droit de toucher, et jusqu'où
HASARD_EFFETS = {"glitch": 50, "blocs": 45, "etirement": 30, "aberration": 60,
                 "decalage_rvb": 6, "bavure": 70, "lueur": 50, "fuite_lumiere": 60,
                 "scanlines": 60, "grille": 40, "courbure": 40, "vignette": 60, "grain": 30,
                 "ondulation": 40, "tri_pixels": 50, "encrage": 70, "bande_vhs": 50,
                 "jpeg": 60}

PALETTE_GRIS = "Niveaux de gris"
PALETTE_AUTO = "Auto (depuis l'image)"
PALETTE_PERSO = "Personnalisée"


def vers_qimage(arr):
    arr = np.ascontiguousarray(arr)
    h, w, _ = arr.shape
    return QImage(arr.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()


def charger_image(chemin):
    img = Image.open(chemin)
    img = ImageOps.exif_transpose(img)  # respecte l'orientation des photos de téléphone
    if img.mode in ("RGBA", "LA", "P"):
        fond = Image.new("RGB", img.size, (255, 255, 255))
        img = img.convert("RGBA")
        fond.paste(img, mask=img.split()[-1])
        img = fond
    return np.asarray(img.convert("RGB"))


def format_temps(s):
    return f"{int(s // 60):02d}:{s % 60:05.2f}"


def dessiner_crabe(p, x, y, taille, couleur, oeil=QColor(TEXTE)):
    for j, ligne in enumerate(CRABE):
        for i, c in enumerate(ligne):
            if c != ".":
                p.fillRect(QRectF(x + i * taille, y + j * taille, taille - 0.5, taille - 0.5),
                           oeil if c == "O" else couleur)


def pixmap_crabe(taille):
    pix = QPixmap(len(CRABE[0]) * taille, len(CRABE) * taille)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    dessiner_crabe(p, 0, 0, taille, QColor(ACCENT))
    p.end()
    return pix


# ---------------------------------------------------------------------------
# Zone d'aperçu
# ---------------------------------------------------------------------------

class Vue(QWidget):
    fichierDepose = Signal(str)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)
        self.setMinimumSize(420, 320)
        self.image = None
        self.originale = None
        self.comparer = False
        self.coupe = 0.5          # position du séparateur avant/après (0..1)
        self.zoom = None          # None = ajuster à la fenêtre
        self.decalage = QPointF(0, 0)
        self._souris = None
        self._survol = False
        self.zoomChange = None    # rappel pour mettre à jour les boutons de zoom
        self.astuce = random.choice(ASTUCES)
        self._message = ""
        self._fin_message = 0
        self._minuteur_message = QTimer(self, interval=40)
        self._minuteur_message.timeout.connect(self._tic_message)

    def definir(self, image, originale=None):
        self.image = QPixmap.fromImage(vers_qimage(image)) if image is not None else None
        if originale is not None:
            self.originale = QPixmap.fromImage(vers_qimage(originale))
        self.update()

    def dire(self, message, duree=2.4):
        """Petite bulle de message en bas de l'aperçu."""
        self._message = message
        self._fin_message = time.time() + duree
        self._minuteur_message.start()
        self.update()

    def _tic_message(self):
        if time.time() > self._fin_message + 0.4:
            self._message = ""
            self._minuteur_message.stop()
        self.update()

    def echelle(self):
        if self.image is None:
            return 1
        if self.zoom is None:
            m = 28
            return min((self.width() - m * 2) / self.image.width(),
                       (self.height() - m * 2) / self.image.height())
        return self.zoom

    def definir_zoom(self, z):
        self.zoom = z
        self.decalage = QPointF(0, 0)
        self.update()
        if self.zoomChange:
            self.zoomChange()

    def _cible(self):
        e = self.echelle()
        w, h = self.image.width() * e, self.image.height() * e
        return QRectF((self.width() - w) / 2 + self.decalage.x(),
                      (self.height() - h) / 2 + self.decalage.y(), w, h)

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(FOND))
        if self.image is None:
            self._etat_vide(p)
        else:
            cible = self._cible()
            # Pixels nets quand on agrandit, lissage quand on réduit
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self.echelle() < 1)
            p.drawPixmap(cible, self.image, QRectF(self.image.rect()))
            if self.comparer and self.originale is not None:
                self._comparaison(p, cible)
        if self._survol:
            self._cadre_depot(p)
        if self._message:
            self._bulle(p)

    def _comparaison(self, p, cible):
        x = cible.left() + cible.width() * self.coupe
        p.save()
        p.setClipRect(QRectF(cible.left(), cible.top(), x - cible.left(), cible.height()))
        p.drawPixmap(cible, self.originale, QRectF(self.originale.rect()))
        p.restore()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(TEXTE), 1.5))
        p.drawLine(QPointF(x, max(0, cible.top())), QPointF(x, min(self.height(), cible.bottom())))
        cy = self.height() / 2
        p.setBrush(QColor(ACCENT))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(x, cy), 13, 13)
        p.setPen(QColor("#1a0904"))
        p.drawText(QRectF(x - 13, cy - 13, 26, 26), Qt.AlignmentFlag.AlignCenter, "‹ ›")
        for texte, gauche in (("AVANT", True), ("APRÈS", False)):
            r = QRectF(0, max(12, cible.top() + 12), 62, 22)
            r.moveLeft(max(12, cible.left() + 12) if gauche
                       else min(self.width(), cible.right()) - 74)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(6, 6, 7, 200))
            p.drawRoundedRect(r, 6, 6)
            p.setPen(QColor(TEXTE))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, texte)

    def _bulle(self, p):
        reste = self._fin_message - time.time()
        alpha = max(0.0, min(1.0, (reste + 0.4) / 0.4))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        f = QFont(p.font())
        f.setPointSize(12)
        p.setFont(f)
        largeur = p.fontMetrics().horizontalAdvance(self._message) + 36
        r = QRectF((self.width() - largeur) / 2, self.height() - 58, largeur, 34)
        p.setOpacity(alpha)
        p.setPen(QPen(QColor(BORD), 1))
        p.setBrush(QColor(18, 18, 21, 240))
        p.drawRoundedRect(r, 17, 17)
        p.setPen(QColor(TEXTE))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self._message)
        p.setOpacity(1)

    def _cadre_depot(self, p):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(ACCENT), 2, Qt.PenStyle.DashLine))
        p.setBrush(QColor(255, 91, 58, 16))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(16, 16, -16, -16), 18, 18)

    def _etat_vide(self, p):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QRectF(self.rect()).center()
        taille = 9
        lw, lh = len(CRABE[0]) * taille, len(CRABE) * taille
        dessiner_crabe(p, c.x() - lw / 2, c.y() - lh - 40, taille,
                       QColor(ACCENT) if self._survol else QColor("#7a2b1c"))
        heure = time.localtime().tm_hour
        salut = "Bonjour" if 5 <= heure < 18 else "Bonsoir"
        p.setPen(QColor(TEXTE))
        f = QFont(TITRES)
        f.setPointSize(22)
        f.setWeight(QFont.Weight.DemiBold)
        p.setFont(f)
        p.drawText(QRectF(0, c.y() - 22, self.width(), 34), Qt.AlignmentFlag.AlignCenter,
                   f"{salut} !")
        f.setPointSize(13)
        f.setWeight(QFont.Weight.Normal)
        p.setFont(f)
        p.setPen(QColor(DISCRET))
        p.drawText(QRectF(0, c.y() + 16, self.width(), 24), Qt.AlignmentFlag.AlignCenter,
                   f"Balance une image ou une vidéo ici, ou fais {CMD}O.")
        f.setPointSize(11)
        f.setItalic(True)
        p.setFont(f)
        p.setPen(QColor(TRES_DISCRET))
        p.drawText(QRectF(0, self.height() - 54, self.width(), 20), Qt.AlignmentFlag.AlignCenter,
                   "Petite astuce : " + self.astuce)

    # --- Navigation : glisser pour déplacer (ou bouger le séparateur), pincer pour zoomer
    def mousePressEvent(self, e):
        self._souris = e.position()
        if self.comparer and self.image is not None:
            self._bouger_coupe(e.position().x())

    def mouseMoveEvent(self, e):
        if self._souris is None or self.image is None:
            return
        if self.comparer:
            self._bouger_coupe(e.position().x())
        elif self.zoom is not None:
            self.decalage += e.position() - self._souris
            self._souris = e.position()
            self.update()

    def _bouger_coupe(self, x):
        cible = self._cible()
        self.coupe = min(1.0, max(0.0, (x - cible.left()) / max(1, cible.width())))
        self.update()

    def mouseReleaseEvent(self, _):
        self._souris = None

    def mouseDoubleClickEvent(self, _):
        if not self.comparer:
            self.definir_zoom(None if self.zoom is not None else 1.0)

    def wheelEvent(self, e):
        if self.image is None:
            return
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:  # Qt traduit Ctrl en ⌘ sur Mac
            self._zoomer(1.0015 ** e.angleDelta().y())
        elif self.zoom is not None:
            self.decalage += QPointF(e.pixelDelta()) if not e.pixelDelta().isNull() \
                else QPointF(e.angleDelta()) / 4
            self.update()

    def event(self, e):
        if e.type() == e.Type.NativeGesture and \
                e.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
            self._zoomer(1 + e.value())
            return True
        return super().event(e)

    def _zoomer(self, facteur):
        self.zoom = min(32.0, max(0.05, self.echelle() * facteur))
        self.update()
        if self.zoomChange:
            self.zoomChange()

    # --- Glisser-déposer
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._survol = True
            self.update()

    def dragLeaveEvent(self, _):
        self._survol = False
        self.update()

    def dropEvent(self, e):
        self._survol = False
        self.update()
        urls = e.mimeData().urls()
        if urls:
            self.fichierDepose.emit(urls[0].toLocalFile())


# ---------------------------------------------------------------------------
# Composants du panneau de réglages
# ---------------------------------------------------------------------------

class Curseur(QWidget):
    change = Signal()

    def __init__(self, nom, mini, maxi, defaut, suffixe="", aide=""):
        super().__init__()
        self.defaut = defaut
        self.suffixe = suffixe
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 3, 16, 3)
        lay.setSpacing(3)
        self.haut = QHBoxLayout()
        self.etiquette = QLabel(nom)
        self.etiquette.setToolTip((aide + "\n\n" if aide else "") + "Double-clic pour revenir à la valeur de départ")
        self.val = QLabel()
        self.val.setObjectName("valeur")
        self.haut.addWidget(self.etiquette)
        self.haut.addStretch()
        self.haut.addWidget(self.val)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(mini, maxi)
        self.slider.setValue(defaut)
        self.slider.valueChanged.connect(self._maj)
        lay.addLayout(self.haut)
        lay.addWidget(self.slider)
        self._maj()

    def _maj(self):
        v = self.slider.value()
        self.val.setText(f"{v}{self.suffixe}")
        # Les valeurs modifiées sont légèrement mises en avant
        self.val.setStyleSheet(f"color: {ACCENT_CLAIR if v != self.defaut else DISCRET};")
        self.change.emit()

    def mouseDoubleClickEvent(self, _):
        self.slider.setValue(self.defaut)

    def valeur(self):
        return self.slider.value()

    def definir(self, v):
        self.slider.setValue(int(v))


class Interrupteur(QWidget):
    change = Signal()

    def __init__(self, nom, defaut, aide=""):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 5, 16, 5)
        self.case = QCheckBox()
        self.case.setChecked(defaut)
        self.case.toggled.connect(lambda _: self.change.emit())
        etiquette = QLabel(nom)
        etiquette.setToolTip(aide)
        lay.addWidget(etiquette)
        lay.addStretch()
        lay.addWidget(self.case)

    def valeur(self):
        return self.case.isChecked()

    def definir(self, v):
        self.case.setChecked(bool(v))


class Liste(QWidget):
    change = Signal()

    def __init__(self, nom, choix, aide=""):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 4, 16, 5)
        lay.setSpacing(5)
        if nom:
            e = QLabel(nom)
            e.setToolTip(aide)
            lay.addWidget(e)
        self.combo = QComboBox()
        self.combo.addItems(choix)
        self.combo.setMaxVisibleItems(25)
        self.combo.currentTextChanged.connect(lambda _: self.change.emit())
        lay.addWidget(self.combo)

    def valeur(self):
        return self.combo.currentText()

    def definir(self, v):
        self.combo.setCurrentText(v)


class Section(QWidget):
    """Bloc repliable : un titre, une phrase d'explication, et un bouton pour tout remettre à zéro."""

    def __init__(self, titre, sous_titre, ouvert=False, reinit=None):
        super().__init__()
        self.titre = titre
        self.cles = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 6)
        lay.setSpacing(0)
        sep = QFrame()
        sep.setObjectName("separateur")
        lay.addWidget(sep)
        tete = QHBoxLayout()
        tete.setSpacing(0)
        self.bouton = QPushButton()
        self.bouton.setObjectName("section")
        self.bouton.setCursor(Qt.CursorShape.PointingHandCursor)
        self.bouton.clicked.connect(self.basculer)
        tete.addWidget(self.bouton, 1)
        if reinit:
            b = QPushButton("↺")
            b.setObjectName("reinit")
            b.setToolTip("Remettre cette section à zéro")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda: reinit(self))
            tete.addWidget(b)
        lay.addLayout(tete)
        self.corps = QWidget()
        self.corps_lay = QVBoxLayout(self.corps)
        self.corps_lay.setContentsMargins(0, 0, 0, 4)
        self.corps_lay.setSpacing(1)
        st = QLabel(sous_titre)
        st.setObjectName("sousTitre")
        self.corps_lay.addWidget(st)
        lay.addWidget(self.corps)
        self.corps.setVisible(ouvert)
        self.modifiee = False
        self._titre()

    def _titre(self):
        fleche = "▾" if self.corps.isVisible() else "▸"
        point = "  •" if self.modifiee else ""
        self.bouton.setText(f"{fleche}  {self.titre}{point}")
        self.bouton.setStyleSheet(f"color: {ACCENT_CLAIR};" if self.modifiee and
                                  not self.corps.isVisible() else "")

    def marquer(self, modifiee):
        if modifiee != self.modifiee:
            self.modifiee = modifiee
            self._titre()

    def basculer(self):
        self.corps.setVisible(not self.corps.isVisible())
        self._titre()

    def ajouter(self, w, cle=None):
        self.corps_lay.addWidget(w)
        if cle:
            self.cles.append(cle)
        return w


class Nuancier(QWidget):
    """Affiche les couleurs de la palette ; clic = modifier, clic droit = supprimer."""
    modifie = Signal(list)

    def __init__(self):
        super().__init__()
        self.couleurs = []
        self.grille = QGridLayout(self)
        self.grille.setContentsMargins(16, 6, 16, 6)
        self.grille.setSpacing(6)

    def definir(self, couleurs):
        self.couleurs = list(couleurs)
        while self.grille.count():
            w = self.grille.takeAt(0).widget()
            w.hide()
            w.deleteLater()
        par_ligne = 8
        for i, c in enumerate(self.couleurs + ["+"]):
            b = QPushButton("+" if c == "+" else "")
            b.setFixedSize(28, 28)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            if c == "+":
                b.setToolTip("Ajouter une couleur")
                b.setStyleSheet(f"border-radius: 14px; border: 1px dashed #3a3530; padding: 0;"
                                f"background: transparent; color: {DISCRET}; font-size: 16px;")
                b.clicked.connect(self._ajouter)
                b.setEnabled(len(self.couleurs) < 64)
            else:
                b.setToolTip(f"{c}\nClic : modifier · Clic droit : supprimer")
                b.setStyleSheet(f"background: {c}; border-radius: 14px;"
                                "border: 1px solid rgba(255,255,255,30);")
                b.clicked.connect(lambda _=False, i=i: self._editer(i))
                b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                b.customContextMenuRequested.connect(lambda _p, i=i: self._supprimer(i))
            self.grille.addWidget(b, i // par_ligne, i % par_ligne)
        self.grille.setColumnStretch(par_ligne, 1)

    def _editer(self, i):
        c = QColorDialog.getColor(QColor(self.couleurs[i]), self, "Couleur")
        if c.isValid():
            self.couleurs[i] = c.name()
            self.modifie.emit(self.couleurs)

    def _ajouter(self):
        c = QColorDialog.getColor(QColor("#ffffff"), self, "Nouvelle couleur")
        if c.isValid():
            self.modifie.emit(self.couleurs + [c.name()])

    def _supprimer(self, i):
        if len(self.couleurs) > 2:
            self.modifie.emit(self.couleurs[:i] + self.couleurs[i + 1:])


# ---------------------------------------------------------------------------
# Travail en arrière-plan
# ---------------------------------------------------------------------------

class Rendu(QThread):
    """Calcule toujours la demande la plus récente ; les demandes dépassées sont ignorées."""
    pret = Signal(object, object, float, int)   # résultat, source, durée (ms), n° de frame

    def __init__(self):
        super().__init__()
        self._cond = threading.Condition()
        self._travail = None
        self._stop = False
        self._cache = (None, None)  # (clé, image source)

    def demander(self, reglages, src=None, video_info=None, frame=0):
        with self._cond:
            self._travail = (dict(reglages), src, video_info, frame)
            self._cond.notify()

    def arreter(self):
        with self._cond:
            self._stop = True
            self._cond.notify()
        self.wait(3000)

    def run(self):
        while True:
            with self._cond:
                while self._travail is None and not self._stop:
                    self._cond.wait()
                if self._stop:
                    return
                reglages, src, vinfo, frame = self._travail
                self._travail = None
            try:
                if src is None and vinfo is not None:
                    cle = (vinfo["chemin"], frame)
                    if self._cache[0] != cle:
                        img = video.lire_frame(vinfo["chemin"], vinfo, frame / vinfo["fps"])
                        if img is None:
                            continue
                        self._cache = (cle, img)
                    src = self._cache[1]
                t = time.perf_counter()
                out = moteur.traiter(src, reglages, frame)
                self.pret.emit(out, src, (time.perf_counter() - t) * 1000, frame)
            except Exception as ex:  # ne jamais tuer le fil de rendu
                print("Erreur de rendu :", ex, file=sys.stderr)


class Lecture(QThread):
    image = Signal(object, object, int)

    def __init__(self, vinfo, debut, reglages_fn):
        super().__init__()
        self.vinfo = vinfo
        self.debut = debut
        self.reglages_fn = reglages_fn
        self.actif = True
        self.affichee = threading.Event()
        self.affichee.set()

    def run(self):
        fps = self.vinfo["fps"]
        frame = self.debut
        while self.actif:
            lecteur = video.Lecteur(self.vinfo["chemin"], self.vinfo, frame / fps)
            t0 = time.perf_counter() - frame / fps
            try:
                while self.actif:
                    src = lecteur.lire()
                    if src is None:
                        break
                    out = moteur.traiter(src, self.reglages_fn(), frame)
                    attente = t0 + frame / fps - time.perf_counter()
                    if attente > 0:
                        time.sleep(attente)
                    self.affichee.wait(0.5)  # on n'inonde pas l'interface
                    self.affichee.clear()
                    if self.actif:
                        self.image.emit(out, src, frame)
                    frame += 1
            finally:
                lecteur.fermer()
            frame = 0  # lecture en boucle


class Export(QThread):
    progression = Signal(int, int)
    fini = Signal(str)
    erreur = Signal(str)

    def __init__(self, chemin, reglages, src=None, vinfo=None, frame=0):
        super().__init__()
        self.chemin, self.reglages, self.src, self.vinfo = chemin, reglages, src, vinfo
        self.frame = frame  # pour un PNG : même graine aléatoire que l'aperçu
        self.annule = False

    def run(self):
        ecrivain = lecteur = None
        try:
            if self.vinfo is None:
                out = moteur.traiter(self.src, self.reglages, self.frame, avec_echelle=True)
                Image.fromarray(out).save(self.chemin, optimize=True)
                self.fini.emit(self.chemin)
                return
            total = self.vinfo["frames"]
            lecteur = video.Lecteur(self.vinfo["chemin"], self.vinfo)
            # Plusieurs images sont calculées en même temps, sur tous les cœurs du processeur,
            # puis écrites dans l'ordre.
            travailleurs = max(2, min(8, (os.cpu_count() or 4) - 1))
            en_cours = deque()
            lues = ecrites = 0
            fin_lecture = False
            with ThreadPoolExecutor(travailleurs) as pool:
                while not self.annule:
                    while not fin_lecture and len(en_cours) < travailleurs * 2:
                        src = lecteur.lire()
                        if src is None:
                            fin_lecture = True
                            break
                        en_cours.append(pool.submit(moteur.traiter, src, self.reglages, lues, True))
                        lues += 1
                    if not en_cours:
                        break
                    out = en_cours.popleft().result()
                    if ecrivain is None:
                        son = self.vinfo["chemin"] if self.vinfo["audio"] else None
                        ecrivain = video.Ecrivain(self.chemin, out.shape[1], out.shape[0],
                                                  self.vinfo["fps"], son)
                    ecrivain.ecrire(out)
                    ecrites += 1
                    self.progression.emit(ecrites, max(total, ecrites))
                for f in en_cours:
                    f.cancel()
            if self.annule:
                if ecrivain:
                    ecrivain.annuler()
                return
            if ecrivain is None:
                raise RuntimeError("Aucune image n'a pu être lue dans la vidéo.")
            ecrivain.terminer()
            self.fini.emit(self.chemin)
        except Exception as ex:
            if ecrivain:
                ecrivain.annuler()
            self.erreur.emit(str(ex))
        finally:
            if lecteur:
                lecteur.fermer()


# ---------------------------------------------------------------------------
# Fenêtre principale
# ---------------------------------------------------------------------------

class Fenetre(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(NOM)
        self.resize(1400, 880)
        self.setMinimumSize(1000, 640)
        self.prefs = QSettings("CrunchCrab", "CrunchCrab")

        self.src = None          # image source affichée (ou frame courante)
        self.vinfo = None        # infos de la vidéo ouverte
        self.chemin = None
        self.frame = 0
        self.palette_perso = list(moteur.PALETTES["Noir & blanc"])
        self.palette_auto = list(moteur.PALETTES["Noir & blanc"])
        self.lecture = None
        self._reglages_courants = {}
        self._bloquer = False
        self.historique = []
        self.pos_historique = -1

        self.rendu = Rendu()
        self.rendu.pret.connect(self._rendu_pret)
        self.rendu.start()
        self.minuteur = QTimer(singleShot=True, interval=25)
        self.minuteur.timeout.connect(self._lancer_rendu)
        self.minuteur_histo = QTimer(singleShot=True, interval=450)
        self.minuteur_histo.timeout.connect(self._memoriser)

        self._construire()
        self._menus()
        # On reprend là où on s'était arrêté
        try:
            self._appliquer_reglages(json.loads(self.prefs.value("derniers_reglages", "{}")))
        except Exception:
            self._appliquer_reglages({})
        self._memoriser()
        QTimer.singleShot(0, lambda: threading.Thread(target=moteur.prechauffer,
                                                      daemon=True).start())

    # ----- Construction de l'interface
    def _construire(self):
        racine = QWidget()
        racine.setObjectName("racine")
        self.setCentralWidget(racine)
        h = QHBoxLayout(racine)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        gauche = QVBoxLayout()
        gauche.setSpacing(0)
        barre = QWidget()
        barre.setObjectName("barre")
        bl = QHBoxLayout(barre)
        bl.setContentsMargins(18, 10, 14, 10)
        bl.setSpacing(8)
        logo = QLabel()
        logo.setPixmap(pixmap_crabe(2))
        bl.addWidget(logo)
        marque = QLabel(NOM)
        marque.setObjectName("marque")
        bl.addWidget(marque)
        bl.addSpacing(16)
        b_ouvrir = QPushButton("Ouvrir…")
        b_ouvrir.clicked.connect(self.ouvrir)
        bl.addWidget(b_ouvrir)
        self.b_annuler = QPushButton("↩")
        self.b_annuler.setObjectName("icone")
        self.b_annuler.setToolTip(f"Annuler ({CMD}Z)")
        self.b_annuler.clicked.connect(self.annuler)
        self.b_retablir = QPushButton("↪")
        self.b_retablir.setObjectName("icone")
        self.b_retablir.setToolTip(f"Rétablir ({MAJ_CMD}Z)")
        self.b_retablir.clicked.connect(self.retablir)
        bl.addWidget(self.b_annuler)
        bl.addWidget(self.b_retablir)
        bl.addStretch()
        b_hasard = QPushButton("🎲  Surprends-moi")
        b_hasard.setToolTip("Je te propose un look au pif (R)")
        b_hasard.clicked.connect(self.surprendre)
        bl.addWidget(b_hasard)
        self.styles = QComboBox()
        self.styles.addItems(["Styles tout prêts"] + list(STYLES))
        self.styles.setMinimumWidth(190)
        self.styles.activated.connect(self._appliquer_style)
        bl.addWidget(self.styles)
        self.b_exporter = QPushButton("Exporter")
        self.b_exporter.setObjectName("principal")
        self.b_exporter.setEnabled(False)
        self.b_exporter.clicked.connect(self.exporter)
        bl.addWidget(self.b_exporter)
        gauche.addWidget(barre)
        sep = QFrame()
        sep.setObjectName("separateur")
        gauche.addWidget(sep)

        self.vue = Vue()
        self.vue.fichierDepose.connect(self.charger)
        self.vue.zoomChange = self._maj_boutons_zoom
        gauche.addWidget(self.vue, 1)

        sep2 = QFrame()
        sep2.setObjectName("separateur")
        gauche.addWidget(sep2)
        transport = QWidget()
        transport.setObjectName("transport")
        tl = QHBoxLayout(transport)
        tl.setContentsMargins(14, 8, 14, 8)
        tl.setSpacing(10)
        self.b_lecture = QPushButton("▶")
        self.b_lecture.setObjectName("lecture")
        self.b_lecture.setToolTip("Lecture / pause (Espace)")
        self.b_lecture.clicked.connect(self.basculer_lecture)
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.valueChanged.connect(self._timeline_bouge)
        self.temps = QLabel("00:00.00")
        self.temps.setObjectName("info")
        self.zone_video = [self.b_lecture, self.timeline, self.temps]
        for w in self.zone_video:
            tl.addWidget(w, 1 if w is self.timeline else 0)
            w.setVisible(False)
        self.ressort = QWidget()  # pousse les infos à droite quand il n'y a pas de vidéo
        self.ressort.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tl.addWidget(self.ressort)
        self.info = QLabel("")
        self.info.setObjectName("info")
        tl.addWidget(self.info)
        tl.addSpacing(8)
        self.boutons_zoom = {}
        for nom, z in (("Ajuster", None), ("1×", 1.0), ("2×", 2.0), ("4×", 4.0)):
            b = QPushButton(nom)
            b.setObjectName("segment")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, z=z: self.vue.definir_zoom(z))
            self.boutons_zoom[z] = b
            tl.addWidget(b)
        self.b_comparer = QPushButton("Avant / après")
        self.b_comparer.setObjectName("bascule")
        self.b_comparer.setCheckable(True)
        self.b_comparer.setToolTip("Glisse le séparateur pour comparer (C)")
        self.b_comparer.toggled.connect(self._comparer)
        tl.addSpacing(6)
        tl.addWidget(self.b_comparer)
        gauche.addWidget(transport)
        self._maj_boutons_zoom()

        h.addLayout(gauche, 1)
        sepv = QFrame()
        sepv.setObjectName("separateurV")
        h.addWidget(sepv)
        h.addWidget(self._panneau())

    def _panneau(self):
        defile = QScrollArea()
        defile.setObjectName("defile")
        defile.setWidgetResizable(True)
        defile.setFixedWidth(340)
        defile.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        interieur = QWidget()
        interieur.setObjectName("panneauInterieur")
        lay = QVBoxLayout(interieur)
        lay.setContentsMargins(0, 0, 0, 16)
        lay.setSpacing(0)
        self.c = {}         # tous les contrôles, par nom de réglage
        self.sections = []

        def section(titre, sous_titre, ouvert=False):
            s = Section(titre, sous_titre, ouvert, self._reinit_section)
            self.sections.append(s)
            lay.addWidget(s)
            return s

        def ajout(s, cle, widget):
            self.c[cle] = s.ajouter(widget, cle)
            widget.change.connect(self._modifie)
            return widget

        s = section("Tramage", "La base : la façon dont les points sont posés.", ouvert=True)
        ajout(s, "algorithme", Liste("Méthode", moteur.ALGORITHMES,
                                     "Chaque méthode répartit les points à sa façon"))
        self.c["algorithme"].change.connect(self._algo_change)
        ajout(s, "taille_pixel", Curseur("Taille des pixels", 1, 32, 2, " px",
                                         "Plus c'est gros, plus ça pixelise"))
        ajout(s, "force", Curseur("Intensité", 0, 200, 100, " %",
                                  "À 0 % : aplats de couleur. Au-delà de 100 % : plus de grain"))
        ajout(s, "taille_motif", Curseur("Taille du motif", 2, 32, 6, " px"))
        ajout(s, "angle", Curseur("Angle de la trame", 0, 90, 45, "°"))
        ajout(s, "zigzag", Interrupteur("Balayage en zigzag", True,
                                        "Alterne le sens de chaque ligne : moins d'artefacts"))
        ajout(s, "bruit_avant", Curseur("Bruit avant tramage", 0, 100, 0, " %",
                                        "Casse les motifs trop réguliers, ça fait plus naturel"))

        s = section("Couleurs", "Choisis ta palette, c'est elle qui fait l'ambiance.", ouvert=True)
        self.liste_palette = s.ajouter(Liste(None, list(moteur.PALETTES)
                                             + [PALETTE_GRIS, PALETTE_AUTO, PALETTE_PERSO]))
        self.liste_palette.change.connect(self._palette_changee)
        self.nb_couleurs = s.ajouter(Curseur("Nombre de couleurs", 2, 32, 4))
        self.nb_couleurs.change.connect(self._palette_changee)
        self.b_recalc = QPushButton("Recalculer depuis l'image")
        self.b_recalc.clicked.connect(self._recalculer_auto)
        conteneur = QWidget()
        cl = QHBoxLayout(conteneur)
        cl.setContentsMargins(16, 2, 16, 2)
        cl.addWidget(self.b_recalc)
        self.recalc_conteneur = s.ajouter(conteneur)
        self.nuancier = s.ajouter(Nuancier())
        self.nuancier.modifie.connect(self._nuancier_modifie)
        ajout(s, "carte_degrade", Interrupteur(
            "Répartir sur la palette", False,
            "Associe les zones sombres à la couleur la plus sombre, les claires à la plus claire.\n"
            "Idéal pour les bichromies et les dégradés."))
        ajout(s, "perceptuel", Interrupteur("Couleurs perceptuelles", True,
                                            "Compare les couleurs comme le fait l'œil humain"))

        s = section("Retouche", "Un petit coup de propre avant de tramer.")
        ajout(s, "luminosite", Curseur("Luminosité", -100, 100, 0))
        ajout(s, "contraste", Curseur("Contraste", -100, 100, 0))
        ajout(s, "gamma", Curseur("Gamma", 10, 300, 100, "", "Éclaircit ou assombrit les tons moyens"))
        ajout(s, "saturation", Curseur("Saturation", 0, 200, 100, " %"))
        ajout(s, "teinte", Curseur("Teinte", -180, 180, 0, "°", "Fait tourner toutes les couleurs"))
        ajout(s, "temperature", Curseur("Température", -100, 100, 0, "",
                                        "Négatif : plus froid · Positif : plus chaud"))
        ajout(s, "flou", Curseur("Flou", 0, 100, 0, " %"))
        ajout(s, "nettete", Curseur("Netteté", 0, 300, 0, " %"))
        ajout(s, "encrage", Curseur("Encrage des contours", 0, 100, 0, " %",
                                    "Souligne les bords en noir, façon bande dessinée"))
        ajout(s, "inverser", Interrupteur("Inverser (négatif)", False))

        s = section("Déformations", "Pour tordre un peu tout ça.")
        ajout(s, "miroir", Liste("Miroir", moteur.MIROIRS))
        ajout(s, "ondulation", Curseur("Ondulation", 0, 100, 0, " %",
                                       "Fait onduler l'image comme un signal perturbé"))
        ajout(s, "frequence_onde", Curseur("Fréquence des vagues", 1, 50, 6))
        ajout(s, "tri_pixels", Curseur("Tri de pixels", 0, 100, 0, " %",
                                       "Range les pixels clairs par luminosité : longues traînées"))
        ajout(s, "tri_direction", Liste("Direction du tri", moteur.DIRECTIONS))
        ajout(s, "tri_inverse", Interrupteur("Tri inversé", False))

        s = section("Glitch", "Pour tout casser… gentiment.")
        ajout(s, "glitch", Curseur("Tranches décalées", 0, 100, 0, " %"))
        ajout(s, "blocs", Curseur("Blocs corrompus", 0, 100, 0, " %",
                                  "Des morceaux d'image déplacés, comme une vidéo abîmée"))
        ajout(s, "etirement", Curseur("Lignes étirées", 0, 100, 0, " %"))
        graine = ajout(s, "graine", Curseur("Variation", 0, 999, 1, "",
                                            "Change la disposition du glitch"))
        de = QPushButton("🎲")
        de.setObjectName("de")
        de.setToolTip("Nouvelle variation")
        de.setCursor(Qt.CursorShape.PointingHandCursor)
        de.clicked.connect(lambda: graine.definir(random.randint(0, 999)))
        graine.haut.insertWidget(2, de)
        ajout(s, "glitch_anime", Interrupteur("Glitch animé (vidéo)", True,
                                              "Le glitch change à chaque image de la vidéo"))

        s = section("Optique", "Des petits défauts d'objectif, ça a du charme.")
        ajout(s, "aberration", Curseur("Aberration chromatique", 0, 100, 0, " %",
                                       "Les couleurs se séparent vers les bords de l'image"))
        ajout(s, "decalage_rvb", Curseur("Décalage RVB", 0, 30, 0, " px"))
        ajout(s, "angle_rvb", Curseur("Direction du décalage", 0, 360, 0, "°"))
        ajout(s, "bavure", Curseur("Bavure des couleurs", 0, 100, 0, " %",
                                   "La couleur déborde, comme sur une cassette VHS"))
        ajout(s, "lueur", Curseur("Lueur", 0, 100, 0, " %"))
        ajout(s, "fuite_lumiere", Curseur("Fuite de lumière", 0, 100, 0, " %",
                                          "Un halo chaud, comme une pellicule voilée"))

        s = section("Écran && texture", "Le côté vieille télé et cassette VHS.")
        ajout(s, "jpeg", Curseur("Artefacts JPEG", 0, 100, 0, " %",
                                 "Comme une image envoyée et renvoyée 50 fois sur WhatsApp"))
        ajout(s, "posterisation", Curseur("Postérisation", 0, 100, 0, " %"))
        ajout(s, "bande_vhs", Curseur("Bande VHS", 0, 100, 0, " %",
                                      "Une bande qui grésille et qui défile, comme sur une vieille cassette"))
        ajout(s, "scanlines", Curseur("Lignes CRT", 0, 100, 0, " %"))
        ajout(s, "grille", Curseur("Grille de phosphore", 0, 100, 0, " %",
                                   "Les petites bandes rouge, vert, bleu d'un vieil écran"))
        ajout(s, "courbure", Curseur("Courbure d'écran", 0, 100, 0, " %"))
        ajout(s, "vignette", Curseur("Vignette", 0, 100, 0, " %"))
        ajout(s, "grain", Curseur("Grain", 0, 100, 0, " %"))

        s = section("Export", "Dernière ligne droite.")
        ajout(s, "echelle_export", Curseur("Agrandissement", 1, 8, 1, "×",
                                           "Multiplie la taille du fichier final, pixels nets"))
        conteneur = QWidget()
        cl = QHBoxLayout(conteneur)
        cl.setContentsMargins(16, 6, 16, 2)
        b = QPushButton("Tout remettre à zéro")
        b.clicked.connect(lambda: (self._appliquer_reglages({}),
                                   self.vue.dire("Et voilà, tout est remis à zéro")))
        cl.addWidget(b)
        s.ajouter(conteneur)
        lay.addStretch()
        defile.setWidget(interieur)
        return defile

    def _menus(self):
        m = self.menuBar().addMenu("Fichier")
        for nom, raccourci, fn in (("Ouvrir…", QKeySequence.StandardKey.Open, self.ouvrir),
                                   ("Exporter…", "Ctrl+E", self.exporter),
                                   (None, None, None),
                                   ("Enregistrer le style…", "Ctrl+S", self.enregistrer_style),
                                   ("Charger un style…", "Ctrl+L", self.charger_style)):
            if nom is None:
                m.addSeparator()
                continue
            a = QAction(nom, self)
            a.setShortcut(QKeySequence(raccourci))
            a.triggered.connect(fn)
            m.addAction(a)
        e = self.menuBar().addMenu("Édition")
        for nom, raccourci, fn in (("Annuler", QKeySequence.StandardKey.Undo, self.annuler),
                                   ("Rétablir", QKeySequence.StandardKey.Redo, self.retablir),
                                   ("Surprends-moi", "R", self.surprendre)):
            a = QAction(nom, self)
            a.setShortcut(QKeySequence(raccourci))
            a.triggered.connect(fn)
            e.addAction(a)
        v = self.menuBar().addMenu("Affichage")
        for nom, raccourci, z in (("Ajuster à la fenêtre", "Ctrl+0", None),
                                  ("Taille réelle", "Ctrl+1", 1.0), ("Zoom 2×", "Ctrl+2", 2.0)):
            a = QAction(nom, self)
            a.setShortcut(QKeySequence(raccourci))
            a.triggered.connect(lambda _=False, z=z: self.vue.definir_zoom(z))
            v.addAction(a)
        a = QAction("Comparer avant / après", self)
        a.setShortcut(QKeySequence("C"))
        a.triggered.connect(self.b_comparer.toggle)
        v.addAction(a)
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self.basculer_lecture)

    # ----- Réglages
    def couleurs(self):
        nom = self.liste_palette.valeur()
        if nom == PALETTE_GRIS:
            return moteur.palette_niveaux_de_gris(self.nb_couleurs.valeur())
        if nom == PALETTE_AUTO:
            return self.palette_auto
        if nom == PALETTE_PERSO:
            return self.palette_perso
        return moteur.PALETTES[nom]

    def reglages(self):
        r = {cle: w.valeur() for cle, w in self.c.items()}
        r["palette"] = list(self.couleurs())
        return r

    def _modifie(self):
        if self._bloquer:
            return
        self._reglages_courants = self.reglages()
        self.minuteur.start()
        self.minuteur_histo.start()
        for s in self.sections:  # un petit point signale les sections modifiées
            s.marquer(any(self.c[k].valeur() != moteur.REGLAGES_DEFAUT[k] for k in s.cles))

    def _algo_change(self):
        algo = self.c["algorithme"].valeur()
        self.c["zigzag"].setVisible(algo in moteur.NOYAUX)
        self.c["taille_motif"].setVisible(algo in moteur.AVEC_MOTIF)
        self.c["angle"].setVisible(algo == "Demi-teinte (points ronds)")
        self.c["force"].setVisible(algo not in ("Aucun (seuil)", "Demi-teinte (points ronds)"))

    def _palette_changee(self):
        nom = self.liste_palette.valeur()
        self.nb_couleurs.setVisible(nom in (PALETTE_GRIS, PALETTE_AUTO))
        self.recalc_conteneur.setVisible(nom == PALETTE_AUTO)
        if nom == PALETTE_AUTO and self.sender() is not None:
            self._recalculer_auto(rendre=False)
        self.nuancier.definir(self.couleurs())
        self._modifie()

    def _recalculer_auto(self, rendre=True):
        if self.src is not None:
            self.palette_auto = moteur.palette_depuis_image(self.src, self.nb_couleurs.valeur())
        if rendre:
            self.nuancier.definir(self.couleurs())
            self._modifie()

    def _nuancier_modifie(self, couleurs):
        self.palette_perso = list(couleurs)
        self.liste_palette.definir(PALETTE_PERSO)
        self.nuancier.definir(self.palette_perso)
        self._modifie()

    def _appliquer_reglages(self, r):
        self._bloquer = True
        try:
            complet = {**moteur.REGLAGES_DEFAUT, **r}
            for cle, w in self.c.items():
                w.definir(complet[cle])
            if "palette_perso" in r:
                self.palette_perso = list(r["palette_perso"])
            self.nb_couleurs.definir(r.get("nb_couleurs", 4))
            nom = r.get("palette_nom", "Noir & blanc")
            if nom == PALETTE_AUTO or (nom not in moteur.PALETTES and
                                       nom not in (PALETTE_GRIS, PALETTE_PERSO)):
                nom = "Noir & blanc"
            self.liste_palette.definir(nom)
        finally:
            self._bloquer = False
        self._algo_change()
        self._palette_changee()

    def _reinit_section(self, section):
        r = self._etat_style()
        for cle in section.cles:
            r[cle] = moteur.REGLAGES_DEFAUT[cle]
        self._appliquer_reglages(r)
        self.vue.dire(f"Hop, {section.titre.replace('&&', '&')} remis à zéro")

    def _appliquer_style(self, index):
        if index > 0:
            nom = self.styles.itemText(index)
            self._appliquer_reglages(STYLES[nom])
            self.vue.dire(f"Hop, style « {nom} »")
        self.styles.setCurrentIndex(0)

    def surprendre(self):
        r = {"algorithme": random.choice(moteur.ALGORITHMES),
             "palette_nom": random.choice(list(moteur.PALETTES)),
             "taille_pixel": random.choice([1, 2, 2, 3, 3, 4, 6]),
             "contraste": random.randint(0, 35),
             "taille_motif": random.randint(3, 9),
             "carte_degrade": random.random() < 0.35,
             "graine": random.randint(0, 999)}
        for cle in random.sample(list(HASARD_EFFETS), random.randint(1, 4)):
            maxi = HASARD_EFFETS[cle]
            r[cle] = random.randint(max(1, maxi // 4), maxi)
        self._appliquer_reglages(r)
        phrases = ["Tiens, essaie ça", "Pas mal, non ?", "Allez, on tente", "Et pourquoi pas ?",
                   "Celui-là, il est cool", "Bon, on verra bien"]
        self.vue.dire(f"🎲  {random.choice(phrases)}  ({r['palette_nom']}, {r['algorithme']})")

    def _etat_style(self):
        r = {cle: w.valeur() for cle, w in self.c.items()}
        r.update(palette_nom=self.liste_palette.valeur(), palette_perso=self.palette_perso,
                 nb_couleurs=self.nb_couleurs.valeur())
        if r["palette_nom"] == PALETTE_AUTO:  # on fige la palette calculée
            r.update(palette_nom=PALETTE_PERSO, palette_perso=list(self.palette_auto))
        return r

    # ----- Historique (annuler / rétablir)
    def _memoriser(self):
        etat = self._etat_style()
        if 0 <= self.pos_historique < len(self.historique) and \
                self.historique[self.pos_historique] == etat:
            return
        self.historique = self.historique[:self.pos_historique + 1] + [etat]
        self.historique = self.historique[-200:]
        self.pos_historique = len(self.historique) - 1
        self._maj_boutons_historique()

    def _maj_boutons_historique(self):
        self.b_annuler.setEnabled(self.pos_historique > 0)
        self.b_retablir.setEnabled(self.pos_historique < len(self.historique) - 1)

    def annuler(self):
        self.minuteur_histo.stop()
        self._memoriser()
        if self.pos_historique > 0:
            self.pos_historique -= 1
            self._appliquer_reglages(self.historique[self.pos_historique])
            self.minuteur_histo.stop()
            self._maj_boutons_historique()
            self.vue.dire("Ok, annulé")

    def retablir(self):
        if self.pos_historique < len(self.historique) - 1:
            self.pos_historique += 1
            self._appliquer_reglages(self.historique[self.pos_historique])
            self.minuteur_histo.stop()
            self._maj_boutons_historique()
            self.vue.dire("Ok, c'est revenu")

    # ----- Styles enregistrés
    def enregistrer_style(self):
        chemin, _ = QFileDialog.getSaveFileName(self, "Enregistrer le style",
                                                os.path.join(self._dossier(), "mon-style.json"),
                                                "Style Crunch Crab (*.json)")
        if chemin:
            with open(chemin, "w", encoding="utf-8") as f:
                json.dump(self._etat_style(), f, ensure_ascii=False, indent=2)
            self.vue.dire("Nickel, ton style est enregistré")

    def charger_style(self):
        chemin, _ = QFileDialog.getOpenFileName(self, "Charger un style", self._dossier(),
                                                "Style Crunch Crab (*.json)")
        if chemin:
            try:
                with open(chemin, encoding="utf-8") as f:
                    self._appliquer_reglages(json.load(f))
                self.vue.dire(f"C'est bon, « {os.path.splitext(os.path.basename(chemin))[0]} » est chargé")
            except Exception as ex:
                QMessageBox.warning(self, "Style illisible",
                                    f"Hmm, ce fichier n'a pas l'air d'être un style Crunch Crab.\n\n{ex}")

    # ----- Fichiers
    def _dossier(self):
        return self.prefs.value("dossier", os.path.expanduser("~/Desktop"))

    def ouvrir(self):
        exts = " ".join("*" + e for e in sorted(video.EXTENSIONS_IMAGE | video.EXTENSIONS_VIDEO))
        chemin, _ = QFileDialog.getOpenFileName(self, "Ouvrir", self._dossier(),
                                                f"Images et vidéos ({exts})")
        if chemin:
            self.charger(chemin)

    def charger(self, chemin):
        self.arreter_lecture()
        try:
            if video.est_video(chemin):
                info = video.infos(chemin)
                info["chemin"] = chemin
                src = video.lire_frame(chemin, info, 0)
                if src is None:
                    raise RuntimeError("Impossible de lire la première image.")
                self.vinfo = info
            else:
                src = charger_image(chemin)
                self.vinfo = None
        except Exception as ex:
            QMessageBox.warning(self, "Oups",
                                "Impossible d'ouvrir ce fichier. Il est peut-être abîmé, "
                                f"ou dans un format que je ne connais pas.\n\n{ex}")
            return
        self.prefs.setValue("dossier", os.path.dirname(chemin))
        self.chemin = chemin
        self.src = src
        self.frame = 0
        self.setWindowTitle(f"{NOM} — {os.path.basename(chemin)}")
        anime = self.vinfo is not None and self.vinfo["frames"] > 1
        for w in self.zone_video:
            w.setVisible(anime)
        self.ressort.setVisible(not anime)
        if anime:
            self.timeline.blockSignals(True)
            self.timeline.setRange(0, self.vinfo["frames"] - 1)
            self.timeline.setValue(0)
            self.timeline.blockSignals(False)
            self._maj_temps()
        self.b_exporter.setEnabled(True)
        if self.liste_palette.valeur() == PALETTE_AUTO:
            self._recalculer_auto(rendre=False)
            self.nuancier.definir(self.couleurs())
        self.vue.originale = None
        self.vue.definir_zoom(None)
        self._modifie()
        nom = os.path.basename(chemin)
        self.vue.dire(f"C'est bon, « {nom} » est chargé" if not anime
                      else "Vidéo chargée, appuie sur Espace pour lancer")

    def _lancer_rendu(self):
        if self.src is None or self.lecture is not None:
            return
        self.rendu.demander(self._reglages_courants, src=self.src if self.vinfo is None else None,
                            video_info=self.vinfo, frame=self.frame)

    def _rendu_pret(self, out, src, ms, frame):
        if self.lecture is not None:
            return
        if self.vinfo is not None and frame != self.frame:
            return  # image dépassée
        self.src = src
        self.vue.definir(out, src)
        self._maj_info(out, f"{ms:.0f} ms")

    def _maj_info(self, out, fin):
        n = len(self._reglages_courants.get("palette", []))
        self.info.setText(f"{out.shape[1]}×{out.shape[0]}   {n} couleurs   {fin}")

    # ----- Vidéo
    def _timeline_bouge(self, v):
        self.frame = v
        self._maj_temps()
        if self.lecture is None:
            self.minuteur.start()

    def _maj_temps(self):
        if self.vinfo:
            self.temps.setText(f"{format_temps(self.frame / self.vinfo['fps'])} / "
                               f"{format_temps(self.vinfo['frames'] / self.vinfo['fps'])}")

    def basculer_lecture(self):
        if not self.vinfo or self.vinfo["frames"] <= 1:
            return
        if self.lecture is not None:
            self.arreter_lecture()
            return
        self.lecture = Lecture(self.vinfo, self.frame, lambda: self._reglages_courants)
        self.lecture.image.connect(self._image_lue)
        self.lecture.start()
        self.b_lecture.setText("❚❚")

    def _image_lue(self, out, src, frame):
        if self.lecture is None:
            return
        self.vue.definir(out, src)
        self.src = src
        self.frame = frame
        self.timeline.blockSignals(True)
        self.timeline.setValue(frame)
        self.timeline.blockSignals(False)
        self._maj_temps()
        self._maj_info(out, "lecture")
        self.lecture.affichee.set()

    def arreter_lecture(self):
        if self.lecture is not None:
            l = self.lecture
            self.lecture = None
            l.actif = False
            l.affichee.set()
            l.wait(3000)
            self.b_lecture.setText("▶")
            self.minuteur.start()

    # ----- Affichage
    def _maj_boutons_zoom(self):
        for z, b in self.boutons_zoom.items():
            b.setChecked(z == self.vue.zoom)

    def _comparer(self, actif):
        self.vue.comparer = actif
        self.vue.update()

    # ----- Export
    def exporter(self):
        if self.src is None:
            return
        self.arreter_lecture()
        base = os.path.splitext(os.path.basename(self.chemin))[0] + "-crunch"
        if self.vinfo and self.vinfo["frames"] > 1:
            filtres = ("Vidéo MP4 (*.mp4);;GIF animé (*.gif);;Vidéo MOV ProRes, qualité max (*.mov)"
                       ";;Image PNG de la frame actuelle (*.png)")
            defaut = base + (".gif" if self.chemin.lower().endswith(".gif") else ".mp4")
        else:
            filtres = "Image PNG (*.png)"
            defaut = base + ".png"
        chemin, filtre = QFileDialog.getSaveFileName(self, "Exporter",
                                                     os.path.join(self._dossier(), defaut), filtres)
        if not chemin:
            return
        ext = filtre.split("*")[-1].rstrip(")")
        if not chemin.lower().endswith(ext):
            chemin = os.path.splitext(chemin)[0] + ext
        png = chemin.lower().endswith(".png")
        self.export = Export(chemin, self.reglages(), src=self.src,
                             vinfo=None if png else self.vinfo, frame=self.frame)

        self.progres = QProgressDialog("C'est parti…", "Annuler", 0, 100, self)
        self.progres.setWindowTitle("Export")
        self.progres.setWindowModality(Qt.WindowModality.WindowModal)
        self.progres.setMinimumDuration(0)
        self.progres.setMinimumWidth(400)
        self.progres.canceled.connect(lambda: setattr(self.export, "annule", True))
        self.t_export = time.perf_counter()
        self.export.progression.connect(self._progression)
        self.export.fini.connect(self._export_fini)
        self.export.erreur.connect(self._export_erreur)
        self.export.start()

    def _progression(self, i, total):
        self.progres.setMaximum(total)
        self.progres.setValue(min(i, total - 1))
        ecoule = time.perf_counter() - self.t_export
        reste = ecoule / i * (total - i)
        attente = "presque fini !" if reste < 3 else f"encore {reste:.0f} s environ"
        self.progres.setLabelText(f"Image {i} sur {total}  ·  {attente}")

    def _export_fini(self, chemin):
        self.progres.reset()
        duree = time.perf_counter() - self.t_export
        self.vue.dire(f"Et voilà ! Fini en {duree:.1f} s 🦀", 3.5)
        boite = QMessageBox(self)
        boite.setWindowTitle("C'est fini")
        boite.setText(f"Et voilà ! 🦀\n\n« {os.path.basename(chemin)} » est prêt.")
        voir = boite.addButton(f"Voir dans {GESTIONNAIRE}", QMessageBox.ButtonRole.ActionRole)
        boite.addButton("Cool", QMessageBox.ButtonRole.AcceptRole)
        boite.exec()
        if boite.clickedButton() is voir:
            reveler(chemin)

    def _export_erreur(self, message):
        self.progres.reset()
        QMessageBox.critical(self, "Mince",
                             f"L'export a planté en route. Désolé !\n\n{message}")

    def closeEvent(self, e):
        self.prefs.setValue("derniers_reglages", json.dumps(self._etat_style(), ensure_ascii=False))
        self.arreter_lecture()
        self.rendu.arreter()
        super().closeEvent(e)


def reveler(chemin):
    """Montre le fichier dans le gestionnaire de fichiers du système."""
    import subprocess
    try:
        if MAC:
            subprocess.Popen(["open", "-R", chemin])
        elif WINDOWS:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(chemin)])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(chemin)])
    except Exception:
        pass


def auto_test(dossier):
    """Vérifie que tout marche (utilisé par GitHub Actions sur les 3 systèmes) : code 0 = ok."""
    import traceback
    os.makedirs(dossier, exist_ok=True)
    journal = open(os.path.join(dossier, "resultat.txt"), "w", encoding="utf-8")

    def noter(m):
        print(m, flush=True)
        journal.write(m + "\n")
        journal.flush()

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    try:
        def attendre(cond, delai=60):
            t = time.time()
            while not cond() and time.time() - t < delai:
                app.processEvents()
                time.sleep(0.01)
            if not cond():
                raise TimeoutError("trop long")

        # Une petite vidéo de test fabriquée par ffmpeg (image + son)
        mp4 = os.path.join(dossier, "source.mp4")
        res = video._executer(["-y", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=12:duration=1",
                               "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", mp4])
        assert res.returncode == 0, res.stderr.decode(errors="replace")[-500:]
        noter(f"ffmpeg : {video.ffmpeg()}")
        png = os.path.join(dossier, "source.png")
        Image.fromarray((np.random.default_rng(1).random((200, 300, 3)) * 255)
                        .astype(np.uint8)).save(png)

        f = Fenetre()
        f.show()
        for chemin in (png, mp4):
            f.charger(chemin)
            for nom in STYLES:
                f._appliquer_reglages(STYLES[nom])
                f.vue.image = None
                attendre(lambda: f.vue.image is not None)
            noter(f"aperçu ok : {os.path.basename(chemin)} ({len(STYLES)} styles)")
        f.surprendre()
        f.annuler()
        for ext in (".mp4", ".gif", ".mov", ".png"):
            sortie = os.path.join(dossier, "export" + ext)
            e = Export(sortie, f.reglages(), src=f.src, vinfo=None if ext == ".png" else f.vinfo)
            erreurs = []
            e.erreur.connect(erreurs.append)
            e.start()
            attendre(lambda: e.isFinished(), 180)
            assert not erreurs, erreurs[0]
            assert os.path.getsize(sortie) > 0
            noter(f"export ok : {ext} ({os.path.getsize(sortie) // 1024} Ko)")
        f.rendu.arreter()
        noter("TOUT EST OK")
        return 0
    except Exception:
        noter("ÉCHEC\n" + traceback.format_exc())
        return 1


def main():
    if "--auto-test" in sys.argv:
        dossier = sys.argv[sys.argv.index("--auto-test") + 1]
        sys.exit(auto_test(dossier))
    if MAC:
        # Affiche « Crunch Crab » dans la barre de menu au lieu de « Python » (mode développement)
        try:
            from Foundation import NSBundle
            info = NSBundle.mainBundle().localizedInfoDictionary() or \
                NSBundle.mainBundle().infoDictionary()
            info["CFBundleName"] = NOM
        except Exception:
            pass
    if WINDOWS:
        # Pour que Windows affiche notre icône dans la barre des tâches, pas celle de Python
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CrunchCrab.App")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(NOM)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    icone = os.path.join(DOSSIER, "icone.png")
    if os.path.exists(icone):
        app.setWindowIcon(QIcon(icone))
    f = Fenetre()
    f.show()
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        f.charger(sys.argv[1])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

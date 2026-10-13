"""
Crunch Crab — interface graphique.

Organisation :
  - theme.py      : couleurs, polices, feuille de style, icônes
  - composants.py : les éléments du panneau de réglages (curseurs, sections, galerie…)
  - Vue           : la grande zone d'aperçu (zoom, déplacement, comparaison, glisser-déposer)
  - Rendu         : calcule l'aperçu en arrière-plan pour ne jamais figer l'interface
  - Miniatures    : calcule les vignettes de la galerie de styles, en arrière-plan aussi
  - Lecture       : lit la vidéo en temps réel
  - Export        : écrit le fichier final avec une barre de progression
  - Fenetre       : assemble le tout
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
from PySide6.QtCore import QObject, QPointF, QRectF, QSettings, Qt, QThread, QTimer, Signal
from PySide6.QtGui import (QAction, QColor, QFont, QFontMetricsF, QIcon, QImage, QKeySequence,
                           QPainter, QPainterPath, QPen, QPixmap, QShortcut)
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QProgressDialog, QPushButton, QScrollArea,
                               QSizePolicy, QSlider, QVBoxLayout, QWidget)

import moteur
import theme as t
import video
from composants import Curseur, Galerie, Interrupteur, Liste, Nuancier, Section, Vignette

DOSSIER = t.DOSSIER
NOM = "Crunch Crab"
VERSION = "1.2.0"
MAC = t.MAC
WINDOWS = t.WINDOWS

# Les raccourcis s'affichent à la façon de chaque système
CMD = "⌘" if MAC else "Ctrl+"
MAJ_CMD = "⇧⌘" if MAC else "Ctrl+Maj+"
GESTIONNAIRE = "le Finder" if MAC else ("l'Explorateur" if WINDOWS else "le dossier")

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
    "le bouton « Surprends-moi » tire un look au hasard. Des fois, ça tombe super bien.",
    "appuie sur C pour comparer avant et après.",
    "pince le trackpad pour zoomer sur les pixels." if MAC else
    "Ctrl + molette pour zoomer sur les pixels.",
    "« Répartir sur la palette » fait des bichromies super facilement.",
    "le tri de pixels rend bien autour de 40 %.",
    f"garde tes looks préférés avec {CMD}S, comme ça tu les retrouves quand tu veux.",
    "les flèches à côté de la méthode et de la palette les font défiler une à une.",
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
    "Macintosh II": {"palette_nom": "Macintosh II", "algorithme": "Shiau-Fan",
                     "taille_pixel": 2, "lineaire": True},
    "ZX Spectrum": {"palette_nom": "ZX Spectrum", "algorithme": "Bayer 2×2",
                    "taille_pixel": 4, "saturation": 140, "contraste": 15},
    "Fraise lait": {"palette_nom": "Fraise lait", "carte_degrade": True, "algorithme": "Fan",
                    "taille_pixel": 2, "lueur": 25, "grain": 10},
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


def scene_exemple(w=360, h=240):
    """Petit paysage de synthèse (ciel, soleil, montagnes, mer) : il sert aux miniatures
    de la galerie tant qu'aucune image n'est ouverte."""
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    v = y / h
    ciel = np.stack([40 + 215 * v ** 1.4, 22 + 110 * v ** 1.8, 70 + 30 * (1 - v)], -1)
    img = ciel.copy()
    # Soleil avec un léger halo
    d = np.hypot(x - w * 0.62, y - h * 0.5)
    halo = np.clip(1 - d / (h * 0.45), 0, 1)[..., None] ** 2
    img = img + halo * np.array([90, 50, 10])
    img = np.where((d < h * 0.15)[..., None], np.array([255, 214, 150]), img)
    # Deux chaînes de montagnes
    for hauteur, amp, freq, teinte in ((0.58, 0.10, 0.021, (70, 34, 82)), (0.66, 0.07, 0.035, (32, 18, 48))):
        crete = h * (hauteur - amp * (np.sin(x[0] * freq) * 0.6 + np.sin(x[0] * freq * 2.7 + 1) * 0.4))
        img = np.where((y > crete)[..., None], np.array(teinte), img)
    # La mer, qui reflète le ciel en bandes
    mer = y > h * 0.74
    reflet = (np.sin(y * 0.9) > 0.2) & (np.abs(x - w * 0.62) < h * 0.12 * (1 + (y - h * 0.74) / h))
    img = np.where(mer[..., None], np.array([20, 24, 60]) + v[..., None] * 30, img)
    img = np.where((mer & reflet)[..., None], np.array([255, 170, 120]), img)
    return np.clip(img, 0, 255).astype(np.uint8)


def dessiner_crabe(p, x, y, taille, couleur=None, oeil=QColor(t.TEXTE)):
    """Dessine la mascotte. Sans couleur précise, la carapace prend le dégradé signature."""
    largeur = len(CRABE[0])
    for j, ligne in enumerate(CRABE):
        for i, c in enumerate(ligne):
            if c != ".":
                teinte = couleur if couleur is not None else t.couleur_degrade(i / (largeur - 1))
                p.fillRect(QRectF(x + i * taille, y + j * taille, taille - 0.5, taille - 0.5),
                           oeil if c == "O" else teinte)


def pixmap_crabe(taille, couleur=None):
    echelle = 2
    pix = QPixmap(len(CRABE[0]) * taille * echelle, len(CRABE) * taille * echelle)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    dessiner_crabe(p, 0, 0, taille * echelle, couleur)
    p.end()
    pix.setDevicePixelRatio(echelle)
    return pix


def reglages_vignette(style, largeur_source):
    """Réglages d'un style pour une miniature : les tailles de pixels et de motifs sont
    réduites dans la même proportion que l'image, pour que la vignette ressemble au résultat."""
    r = {**moteur.REGLAGES_DEFAUT, **style}
    r["palette"] = list(moteur.PALETTES.get(style.get("palette_nom"), moteur.PALETTES["Noir & blanc"]))
    k = Vignette.LARGEUR * 2 / max(1, min(largeur_source, 900))
    r["taille_pixel"] = max(1, round(r["taille_pixel"] * k))
    r["taille_motif"] = max(2, round(r["taille_motif"] * k))
    return r


def recadrer(src, w, h):
    """Recadre au centre au format w:h puis réduit : la miniature est toujours pleine."""
    sh, sw, _ = src.shape
    if sw / sh > w / h:
        nw = int(sh * w / h)
        x0 = (sw - nw) // 2
        src = src[:, x0:x0 + nw]
    else:
        nh = int(sw * h / w)
        y0 = (sh - nh) // 2
        src = src[y0:y0 + nh]
    return np.asarray(Image.fromarray(np.ascontiguousarray(src)).resize((w, h), Image.Resampling.BOX))


# ---------------------------------------------------------------------------
# Zone d'aperçu
# ---------------------------------------------------------------------------

class Vue(QWidget):
    fichierDepose = Signal(str)
    RAYON = 18

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
        self._zone_message = QRectF()
        self._minuteur_message = QTimer(self, interval=40)
        self._minuteur_message.timeout.connect(self._tic_message)
        self._reduites = {}       # images déjà réduites à la taille d'affichage (voir _a_afficher)

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
            return
        # Seule la bulle est redessinée pendant son fondu, pas toute l'image
        self.update(self._zone_message.toAlignedRect().adjusted(-2, -2, 2, 2))

    def echelle(self):
        if self.image is None:
            return 1
        if self.zoom is None:
            m = 40
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

    def _a_afficher(self, role, pix, cible):
        """En réduction, l'image lissée est calculée une seule fois par taille puis gardée :
        déplacer le séparateur ou afficher une bulle ne relance pas un redimensionnement."""
        if self.echelle() >= 1:
            return pix
        dpr = self.devicePixelRatioF()
        w, h = max(1, round(cible.width() * dpr)), max(1, round(cible.height() * dpr))
        cle = (pix.cacheKey(), w, h)
        deja = self._reduites.get(role)
        if deja is None or deja[0] != cle:
            reduite = pix.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            deja = (cle, reduite)
            self._reduites[role] = deja
        return deja[1]

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        carte = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        contour = QPainterPath()
        contour.addRoundedRect(carte, self.RAYON, self.RAYON)
        p.fillRect(self.rect(), QColor(t.FOND))
        p.fillPath(contour, t.texture_trame())
        p.save()
        p.setClipPath(contour)
        if self.image is None:
            self._etat_vide(p)
        else:
            cible = self._cible()
            img = self._a_afficher("image", self.image, cible)
            p.drawPixmap(cible, img, QRectF(img.rect()))
            self._reperes(p, cible)
            if self.comparer and self.originale is not None:
                self._comparaison(p, cible)
        if self._survol:
            self._cadre_depot(p)
        if self._message:
            self._bulle(p)
        p.restore()
        p.setPen(QPen(QColor(t.BORD), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(contour)

    def _reperes(self, p, cible):
        """Traits de coupe aux quatre coins, comme sur une épreuve d'imprimerie."""
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setPen(QPen(QColor(t.TRES_DISCRET), 1))
        ecart, long_ = 6, 12
        for x, sx in ((cible.left(), -1), (cible.right(), 1)):
            for y, sy in ((cible.top(), -1), (cible.bottom(), 1)):
                p.drawLine(QPointF(x + sx * ecart, y), QPointF(x + sx * (ecart + long_), y))
                p.drawLine(QPointF(x, y + sy * ecart), QPointF(x, y + sy * (ecart + long_)))
        p.restore()

    def _pastille(self, p, rect, texte):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(6, 5, 8, 215))
        p.drawRoundedRect(rect, 6, 6)
        p.setFont(t.police_pixel(8))
        p.setPen(QColor(t.TEXTE))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, texte)

    def _comparaison(self, p, cible):
        x = cible.left() + cible.width() * self.coupe
        p.save()
        p.setClipRect(QRectF(cible.left(), cible.top(), x - cible.left(), cible.height()), Qt.ClipOperation.IntersectClip)
        img = self._a_afficher("originale", self.originale, cible)
        p.drawPixmap(cible, img, QRectF(img.rect()))
        p.restore()
        p.setPen(QPen(QColor(t.TEXTE), 1.5))
        p.drawLine(QPointF(x, max(0, cible.top())), QPointF(x, min(self.height(), cible.bottom())))
        cy = self.height() / 2
        poignee = QRectF(x - 13, cy - 22, 26, 44)
        p.setPen(QPen(QColor(255, 255, 255, 90), 1))
        p.setBrush(t.degrade(poignee))
        p.drawRoundedRect(poignee, 13, 13)
        for sens in (-1, 1):
            pix = t.pixmap_icone("gauche" if sens < 0 else "droite", t.ENCRE, 12, 2.4)
            p.drawPixmap(QPointF(x + sens * 4 - 6, cy - 6), pix)
        haut = max(14, cible.top() + 14)
        self._pastille(p, QRectF(max(14, cible.left() + 14), haut, 64, 22), "AVANT")
        self._pastille(p, QRectF(min(self.width(), cible.right()) - 78, haut, 64, 22), "APRÈS")

    def _bulle(self, p):
        reste = self._fin_message - time.time()
        alpha = max(0.0, min(1.0, (reste + 0.4) / 0.4))
        f = QFont()
        f.setPixelSize(13)
        p.setFont(f)
        largeur = p.fontMetrics().horizontalAdvance(self._message) + 66
        r = QRectF((self.width() - largeur) / 2, self.height() - 64, largeur, 38)
        self._zone_message = r
        p.setOpacity(alpha)
        p.setPen(QPen(QColor(t.BORD_FORT), 1))
        p.setBrush(QColor(14, 12, 18, 240))
        p.drawRoundedRect(r, 19, 19)
        crabe = pixmap_crabe(1)
        p.drawPixmap(QPointF(r.left() + 16, r.center().y() - crabe.height() / crabe.devicePixelRatio() / 2), crabe)
        p.setPen(QColor(t.TEXTE))
        p.drawText(r.adjusted(40, 0, -16, 0), Qt.AlignmentFlag.AlignVCenter, self._message)
        p.setOpacity(1)

    def _cadre_depot(self, p):
        r = QRectF(self.rect()).adjusted(18, 18, -18, -18)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 79, 98, 22))
        p.drawRoundedRect(r, 14, 14)
        stylo = QPen(t.degrade(r), 2, Qt.PenStyle.DashLine)
        p.setPen(stylo)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, 14, 14)
        p.setFont(t.police_pixel(24))
        p.setPen(QColor(t.TEXTE))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, "DÉPOSE ICI")

    def _touche(self, p, x, y, texte, legende, dessiner=True):
        """Petite touche de clavier dessinée, suivie de sa légende. Renvoie la largeur totale."""
        p.setFont(t.police_mono(11, gras=True))
        lt = p.fontMetrics().horizontalAdvance(texte) + 14
        legende_police = QFont()
        legende_police.setPixelSize(12)
        ll = QFontMetricsF(legende_police).horizontalAdvance(legende)
        if not dessiner:
            return lt + 8 + ll
        r = QRectF(x, y, lt, 22)
        p.setPen(QPen(QColor(t.BORD_FORT), 1))
        p.setBrush(QColor(t.CHAMP))
        p.drawRoundedRect(r, 6, 6)
        p.setPen(QColor(t.TEXTE))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, texte)
        p.setFont(legende_police)
        p.setPen(QColor(t.DISCRET))
        p.drawText(QRectF(x + lt + 8, y, ll + 2, 22), Qt.AlignmentFlag.AlignVCenter, legende)
        return lt + 8 + ll

    def _etat_vide(self, p):
        c = QRectF(self.rect()).center()
        taille = 10
        lw, lh = len(CRABE[0]) * taille, len(CRABE) * taille
        # Le crabe, posé sur une petite ombre portée tramée
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(9):
            p.setBrush(QColor(255, 79, 98, 10 + i * 3))
            p.drawEllipse(QPointF(c.x(), c.y() - 42), lw * 0.55 - i * 5, 9 - i)
        dessiner_crabe(p, c.x() - lw / 2, c.y() - lh - 56, taille,
                       QColor(t.ACCENT) if self._survol else None)
        heure = time.localtime().tm_hour
        salut = "BONJOUR !" if 5 <= heure < 18 else "BONSOIR !"
        p.setFont(t.police_pixel(32))
        p.setPen(QColor(t.TEXTE))
        p.drawText(QRectF(0, c.y() - 22, self.width(), 40), Qt.AlignmentFlag.AlignCenter, salut)
        f = QFont()
        f.setPixelSize(14)
        p.setFont(f)
        p.setPen(QColor(t.DISCRET))
        p.drawText(QRectF(0, c.y() + 22, self.width(), 24), Qt.AlignmentFlag.AlignCenter,
                   "Balance une image, un GIF ou une vidéo dans cette zone.")
        # Les deux gestes possibles, sous forme de touches
        essai = [(f"{CMD}O", "ouvrir un fichier"), ("C", "comparer avant / après")]
        largeur = sum(self._touche(p, 0, 0, a, b, dessiner=False) for a, b in essai) + 28
        x = c.x() - largeur / 2
        for a, b in essai:
            x += self._touche(p, x, c.y() + 62, a, b) + 28
        p.setFont(t.police_pixel(8))
        p.setPen(QColor(t.TRES_DISCRET))
        p.drawText(QRectF(0, self.height() - 46, self.width(), 14), Qt.AlignmentFlag.AlignCenter,
                   "ASTUCE")
        f.setPixelSize(12)
        p.setFont(f)
        p.drawText(QRectF(0, self.height() - 30, self.width(), 18), Qt.AlignmentFlag.AlignCenter,
                   self.astuce[0].upper() + self.astuce[1:])

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


class BarreEtat(QWidget):
    """Bandeau d'état sous l'aperçu : voyant (prêt / calcul), dimensions, palette, temps de rendu."""

    def __init__(self):
        super().__init__()
        self.texte = ""
        self.couleurs = []
        self.calcul = False
        self.setMinimumWidth(120)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

    def definir(self, texte=None, couleurs=None, calcul=None):
        if texte is not None:
            self.texte = texte
        if couleurs is not None:
            self.couleurs = list(couleurs)[:32]
        if calcul is not None:
            self.calcul = calcul
        self.update()

    def paintEvent(self, _):
        if not self.texte:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cy = self.height() / 2
        x = self.width()
        # La palette, en petits carrés, collée à droite
        cote, ecart = 8, 2
        for c in reversed(self.couleurs):
            x -= cote
            p.fillRect(QRectF(x, cy - cote / 2, cote, cote), QColor(c))
            x -= ecart
        x -= 12
        p.setFont(t.police_mono(11))
        largeur = p.fontMetrics().horizontalAdvance(self.texte)
        x -= largeur
        p.setPen(QColor(t.DISCRET))
        p.drawText(QRectF(x, 0, largeur + 2, self.height()), Qt.AlignmentFlag.AlignVCenter, self.texte)
        t.point_lumineux(p, QPointF(x - 12, cy), 3, t.AMBRE if self.calcul else t.VERT)


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
                        # Une image par cœur : pas de découpage en bandes en plus
                        en_cours.append(pool.submit(moteur.traiter, src, self.reglages, lues,
                                                    True, False))
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



class Miniatures(QObject):
    """Calcule les vignettes de la galerie sur un fil à part, une à une.

    Chaque nouvelle demande (nouvelle image) invalide la précédente : les vignettes
    d'une image qu'on vient de remplacer ne sont jamais affichées.
    """
    prete = Signal(int, str, QImage)

    def __init__(self):
        super().__init__()
        self._pool = ThreadPoolExecutor(1, thread_name_prefix="miniatures")
        self._generation = 0

    def calculer(self, src):
        self._generation += 1
        self._pool.submit(self._travail, self._generation, src)

    def _travail(self, generation, src):
        try:
            petite = recadrer(src, Vignette.LARGEUR * 2, Vignette.HAUTEUR * 2)
            for nom, style in STYLES.items():
                if generation != self._generation:
                    return  # une image plus récente est arrivée
                out = moteur.traiter(petite, reglages_vignette(style, src.shape[1]), 0,
                                     parallele=False)
                self.prete.emit(generation, nom, vers_qimage(out))
        except Exception as ex:  # une vignette ratée ne doit jamais gêner l'app
            print("Erreur de miniature :", ex, file=sys.stderr)

    def generation(self):
        return self._generation

    def arreter(self):
        self._generation += 1
        self._pool.shutdown(wait=False, cancel_futures=True)


# ---------------------------------------------------------------------------
# Fenêtre principale
# ---------------------------------------------------------------------------

class Fenetre(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(NOM)
        self.resize(1440, 900)
        self.setMinimumSize(1080, 680)
        self.prefs = QSettings("CrunchCrab", "CrunchCrab")

        self.src = None          # image source affichée (ou frame courante)
        self.vinfo = None        # infos de la vidéo ouverte
        self.chemin = None
        self.frame = 0
        self.palette_perso = list(moteur.PALETTES["Noir & blanc"])
        self.palette_auto = list(moteur.PALETTES["Noir & blanc"])
        self.lecture = None
        self._reglages_courants = {}
        self._derniere_demande = None
        self._bloquer = False
        self._style_actif = None  # (nom, état) du dernier style de la galerie appliqué
        self.historique = []
        self.pos_historique = -1

        self.rendu = Rendu()
        self.rendu.pret.connect(self._rendu_pret)
        self.rendu.start()
        self.minuteur = QTimer(singleShot=True, interval=25)
        self.minuteur.timeout.connect(self._lancer_rendu)
        self.minuteur_histo = QTimer(singleShot=True, interval=450)
        self.minuteur_histo.timeout.connect(self._memoriser)
        self.miniatures = Miniatures()
        self.miniatures.prete.connect(self._miniature_prete)

        self._construire()
        self._menus()
        # On reprend là où on s'était arrêté
        try:
            self._appliquer_reglages(json.loads(self.prefs.value("derniers_reglages", "{}")))
        except Exception:
            self._appliquer_reglages({})
        self._memoriser()
        self.miniatures.calculer(scene_exemple())
        QTimer.singleShot(0, lambda: threading.Thread(target=moteur.prechauffer,
                                                      daemon=True).start())

    # ----- Construction de l'interface
    def _bouton(self, texte, nom_icone=None, objet=None, bulle=None, couleur=t.TEXTE):
        b = QPushButton(texte)
        if nom_icone:
            b.setIcon(t.icone(nom_icone, couleur, 16))
        if objet:
            b.setObjectName(objet)
        if bulle:
            b.setToolTip(bulle)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

    def _construire(self):
        racine = QWidget()
        racine.setObjectName("racine")
        self.setCentralWidget(racine)
        h = QHBoxLayout(racine)
        h.setContentsMargins(12, 10, 12, 12)
        h.setSpacing(12)

        gauche = QVBoxLayout()
        gauche.setSpacing(10)

        # Barre du haut : marque, fichier, historique… et les deux gros boutons
        barre = QHBoxLayout()
        barre.setContentsMargins(6, 0, 0, 0)
        barre.setSpacing(8)
        logo = QLabel()
        logo.setPixmap(pixmap_crabe(2))
        barre.addWidget(logo)
        barre.addSpacing(4)
        marque = QLabel(NOM.upper())
        marque.setObjectName("marque")
        barre.addWidget(marque)
        version = QLabel(f"V{VERSION}")
        version.setObjectName("version")
        barre.addWidget(version)
        barre.addSpacing(18)
        b_ouvrir = self._bouton("Ouvrir", "ouvrir", bulle=f"Ouvrir une image ou une vidéo ({CMD}O)")
        b_ouvrir.clicked.connect(self.ouvrir)
        barre.addWidget(b_ouvrir)
        self.b_annuler = self._bouton("", "annuler", "icone", f"Annuler ({CMD}Z)")
        self.b_annuler.clicked.connect(self.annuler)
        self.b_retablir = self._bouton("", "retablir", "icone", f"Rétablir ({MAJ_CMD}Z)")
        self.b_retablir.clicked.connect(self.retablir)
        barre.addWidget(self.b_annuler)
        barre.addWidget(self.b_retablir)
        barre.addStretch()
        b_hasard = self._bouton("Surprends-moi", "de", bulle="Un look tiré au hasard (R)")
        b_hasard.clicked.connect(self.surprendre)
        barre.addWidget(b_hasard)
        self.b_exporter = self._bouton("Exporter", "exporter", "principal", f"Exporter ({CMD}E)",
                                       couleur=t.ENCRE)
        self.b_exporter.setEnabled(False)
        self.b_exporter.clicked.connect(self.exporter)
        barre.addWidget(self.b_exporter)
        gauche.addLayout(barre)

        self.vue = Vue()
        self.vue.fichierDepose.connect(self.charger)
        self.vue.zoomChange = self._maj_boutons_zoom
        gauche.addWidget(self.vue, 1)

        # Barre du bas : lecture vidéo, état, zoom, comparaison
        transport = QWidget()
        transport.setObjectName("carte")
        transport.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        tl = QHBoxLayout(transport)
        tl.setContentsMargins(10, 8, 10, 8)
        tl.setSpacing(10)
        self.b_lecture = self._bouton("", "lecture", "lecture", "Lecture / pause (Espace)", t.ENCRE)
        self.b_lecture.clicked.connect(self.basculer_lecture)
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.valueChanged.connect(self._timeline_bouge)
        self.temps = QLabel("00:00.00")
        self.temps.setObjectName("info")
        self.zone_video = [self.b_lecture, self.timeline, self.temps]
        for w in self.zone_video:
            tl.addWidget(w, 1 if w is self.timeline else 0)
            w.setVisible(False)
        self.etat = BarreEtat()
        tl.addWidget(self.etat, 1)
        tl.addSpacing(6)
        groupe = QWidget()
        groupe.setObjectName("groupe")
        groupe.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        gl = QHBoxLayout(groupe)
        gl.setContentsMargins(3, 3, 3, 3)
        gl.setSpacing(2)
        self.boutons_zoom = {}
        for nom, z in (("Ajuster", None), ("1×", 1.0), ("2×", 2.0), ("4×", 4.0)):
            b = self._bouton(nom, objet="segment")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, z=z: self.vue.definir_zoom(z))
            self.boutons_zoom[z] = b
            gl.addWidget(b)
        tl.addWidget(groupe)
        self.b_comparer = self._bouton("Avant / après", "comparer", "bascule",
                                       "Glisse le séparateur pour comparer (C)")
        self.b_comparer.setCheckable(True)
        self.b_comparer.toggled.connect(self._comparer)
        tl.addWidget(self.b_comparer)
        gauche.addWidget(transport)
        self._maj_boutons_zoom()

        h.addLayout(gauche, 1)
        h.addWidget(self._panneau())

    def _panneau(self):
        carte = QWidget()
        carte.setObjectName("carte")
        carte.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        carte.setFixedWidth(356)
        cl = QVBoxLayout(carte)
        cl.setContentsMargins(0, 6, 0, 6)
        defile = QScrollArea()
        defile.setObjectName("defile")
        defile.setWidgetResizable(True)
        defile.setFrameShape(QScrollArea.Shape.NoFrame)
        defile.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        cl.addWidget(defile)
        interieur = QWidget()
        interieur.setObjectName("panneauInterieur")
        lay = QVBoxLayout(interieur)
        lay.setContentsMargins(0, 0, 0, 16)
        lay.setSpacing(0)
        self.c = {}         # tous les contrôles, par nom de réglage
        self.sections = []
        Section._compteur = 0

        def section(titre, sous_titre, ouvert=False, reinit=True):
            s = Section(titre, sous_titre, ouvert, self._reinit_section if reinit else None)
            if reinit:
                self.sections.append(s)
            lay.addWidget(s)
            return s

        def ajout(s, cle, widget):
            self.c[cle] = s.ajouter(widget, cle)
            widget.change.connect(self._modifie)
            return widget

        s = section("Styles", "Un clic pour essayer un look complet. Les miniatures sont "
                    "calculées sur ton image.", ouvert=True, reinit=False)
        self.galerie = s.ajouter(Galerie(list(STYLES)))
        self.galerie.choisi.connect(self._appliquer_style)

        s = section("Tramage", "La base : la façon dont les points sont posés.", ouvert=True)
        ajout(s, "algorithme", Liste(
            "Méthode", moteur.ALGORITHMES,
            "Diffusion (Floyd, Atkinson…) : organique. Bayer : quadrillé. Trames : imprimé.",
            fleches=True))
        self.c["algorithme"].change.connect(self._algo_change)
        ajout(s, "taille_pixel", Curseur("Taille des pixels", 1, 32, 2, " px",
                                         "Plus c'est gros, plus ça pixelise. 1 px garde toute la finesse."))
        ajout(s, "force", Curseur("Intensité", 0, 200, 100, " %",
                                  "À 0 % : des aplats de couleur. Au-delà de 100 % : encore plus de grain.",
                                  neutre=100))
        ajout(s, "taille_motif", Curseur("Taille du motif", 2, 32, 6, " px",
                                         "La taille des points ou des lignes de la trame."))
        ajout(s, "angle", Curseur("Angle de la trame", 0, 90, 45, "°",
                                  "L'inclinaison de la trame, comme sur une rotative de journal."))
        ajout(s, "zigzag", Interrupteur("Balayage en zigzag", True,
                                        "Alterne le sens de chaque ligne : moins de traînées."))
        ajout(s, "bruit_avant", Curseur("Bruit avant tramage", 0, 100, 0, " %",
                                        "Casse les motifs trop réguliers, ça fait plus naturel."))

        s = section("Couleurs", "Choisis ta palette : c'est elle qui fait l'ambiance.", ouvert=True)
        self.liste_palette = s.ajouter(Liste(None, list(moteur.PALETTES)
                                             + [PALETTE_GRIS, PALETTE_AUTO, PALETTE_PERSO],
                                             "Les flèches font défiler les palettes une à une.",
                                             fleches=True))
        self.liste_palette.change.connect(self._palette_changee)
        self.nb_couleurs = s.ajouter(Curseur("Nombre de couleurs", 2, 32, 4, "",
                                             "Combien de teintes garder dans la palette."))
        self.nb_couleurs.change.connect(self._palette_changee)
        self.b_recalc = self._bouton("Recalculer depuis l'image", "reinit")
        self.b_recalc.clicked.connect(self._recalculer_auto)
        conteneur = QWidget()
        rl = QHBoxLayout(conteneur)
        rl.setContentsMargins(18, 2, 18, 2)
        rl.addWidget(self.b_recalc)
        self.recalc_conteneur = s.ajouter(conteneur)
        self.nuancier = s.ajouter(Nuancier())
        self.nuancier.modifie.connect(self._nuancier_modifie)
        ajout(s, "carte_degrade", Interrupteur(
            "Répartir sur la palette", False,
            "Les zones sombres prennent la couleur la plus sombre, les claires la plus claire. "
            "Parfait pour les bichromies."))
        ajout(s, "perceptuel", Interrupteur("Couleurs perceptuelles", True,
                                            "Compare les couleurs comme le fait l'œil humain."))
        ajout(s, "lineaire", Interrupteur(
            "Lumière linéaire", False,
            "Mélange la lumière comme en vrai : de loin, les demi-tons sont plus fidèles."))

        s = section("Retouche", "Un petit coup de propre avant de tramer.")
        ajout(s, "luminosite", Curseur("Luminosité", -100, 100, 0, "",
                                       "Éclaircit ou assombrit toute l'image."))
        ajout(s, "contraste", Curseur("Contraste", -100, 100, 0, "",
                                      "Écarte les clairs et les sombres : le tramage en ressort plus net."))
        ajout(s, "gamma", Curseur("Gamma", 10, 300, 100, "",
                                  "Joue sur les tons moyens sans toucher au noir ni au blanc.", neutre=100))
        ajout(s, "saturation", Curseur("Saturation", 0, 200, 100, " %",
                                       "0 % : noir et blanc. 200 % : couleurs à fond.", neutre=100))
        ajout(s, "teinte", Curseur("Teinte", -180, 180, 0, "°",
                                   "Fait tourner toutes les couleurs sur le cercle chromatique."))
        ajout(s, "temperature", Curseur("Température", -100, 100, 0, "",
                                        "Vers le bleu à gauche, vers l'orange à droite."))
        ajout(s, "flou", Curseur("Flou", 0, 100, 0, " %",
                                 "Adoucit l'image avant le tramage : moins de bruit, plus d'aplats."))
        ajout(s, "nettete", Curseur("Netteté", 0, 300, 0, " %",
                                    "Renforce les détails fins avant le tramage."))
        ajout(s, "encrage", Curseur("Encrage des contours", 0, 100, 0, " %",
                                    "Souligne les bords en noir, façon bande dessinée."))
        ajout(s, "inverser", Interrupteur("Inverser (négatif)", False, "Passe l'image en négatif."))

        s = section("Déformations", "Pour tordre un peu tout ça.")
        ajout(s, "miroir", Liste("Miroir", moteur.MIROIRS,
                                 "Recopie une moitié de l'image sur l'autre, ou en kaléidoscope."))
        ajout(s, "ondulation", Curseur("Ondulation", 0, 100, 0, " %",
                                       "Fait onduler l'image comme un signal perturbé."))
        ajout(s, "frequence_onde", Curseur("Fréquence des vagues", 1, 50, 6, "",
                                           "Le nombre de vagues dans l'image."))
        ajout(s, "tri_pixels", Curseur("Tri de pixels", 0, 100, 0, " %",
                                       "Range les pixels par luminosité : longues traînées lumineuses."))
        ajout(s, "tri_direction", Liste("Direction du tri", moteur.DIRECTIONS,
                                        "Dans quel sens les pixels glissent."))
        ajout(s, "tri_inverse", Interrupteur("Tri inversé", False,
                                             "Fait glisser les pixels sombres plutôt que les clairs."))

        s = section("Glitch", "Pour tout casser… gentiment.")
        ajout(s, "glitch", Curseur("Tranches décalées", 0, 100, 0, " %",
                                   "Des bandes horizontales qui glissent de côté."))
        ajout(s, "blocs", Curseur("Blocs corrompus", 0, 100, 0, " %",
                                  "Des morceaux d'image déplacés, comme une vidéo abîmée."))
        ajout(s, "etirement", Curseur("Lignes étirées", 0, 100, 0, " %",
                                      "Une ligne de pixels étirée vers le bas, façon bug d'écran."))
        graine = ajout(s, "graine", Curseur("Variation", 0, 999, 1, "",
                                            "Change la disposition du glitch. Le dé en tire une au hasard."))
        de = self._bouton("", "de", "de", "Nouvelle variation", t.DISCRET)
        de.clicked.connect(lambda: graine.definir(random.randint(0, 999)))
        graine.haut.insertWidget(2, de)
        ajout(s, "glitch_anime", Interrupteur("Glitch animé (vidéo)", True,
                                              "En vidéo, le glitch change à chaque image."))

        s = section("Optique", "Des petits défauts d'objectif, ça a du charme.")
        ajout(s, "aberration", Curseur("Aberration chromatique", 0, 100, 0, " %",
                                       "Les couleurs se séparent vers les bords, comme un vieil objectif."))
        ajout(s, "decalage_rvb", Curseur("Décalage RVB", 0, 30, 0, " px",
                                         "Décale les canaux rouge, vert et bleu."))
        ajout(s, "angle_rvb", Curseur("Direction du décalage", 0, 360, 0, "°",
                                      "Dans quel sens partent les couleurs."))
        ajout(s, "bavure", Curseur("Bavure des couleurs", 0, 100, 0, " %",
                                   "La couleur déborde, comme sur une cassette VHS."))
        ajout(s, "lueur", Curseur("Lueur", 0, 100, 0, " %", "Les zones claires rayonnent un peu."))
        ajout(s, "fuite_lumiere", Curseur("Fuite de lumière", 0, 100, 0, " %",
                                          "Un halo chaud, comme une pellicule voilée."))

        s = section("Écran & texture", "Le côté vieille télé et cassette VHS.")
        ajout(s, "jpeg", Curseur("Artefacts JPEG", 0, 100, 0, " %",
                                 "Comme une image envoyée et renvoyée 50 fois sur WhatsApp."))
        ajout(s, "posterisation", Curseur("Postérisation", 0, 100, 0, " %",
                                          "Réduit les nuances en paliers bien nets."))
        ajout(s, "bande_vhs", Curseur("Bande VHS", 0, 100, 0, " %",
                                      "Une bande qui grésille et qui défile, comme sur une vieille cassette."))
        ajout(s, "scanlines", Curseur("Lignes CRT", 0, 100, 0, " %",
                                      "Les lignes horizontales d'un écran cathodique."))
        ajout(s, "grille", Curseur("Grille de phosphore", 0, 100, 0, " %",
                                   "Les petites bandes rouge, vert, bleu d'un vieil écran."))
        ajout(s, "courbure", Curseur("Courbure d'écran", 0, 100, 0, " %",
                                     "Bombe l'image comme un écran de télé."))
        ajout(s, "vignette", Curseur("Vignette", 0, 100, 0, " %",
                                     "Assombrit les coins pour centrer le regard."))
        ajout(s, "grain", Curseur("Grain", 0, 100, 0, " %", "Un grain de pellicule par-dessus tout."))

        s = section("Export", "Dernière ligne droite.")
        ajout(s, "echelle_export", Curseur("Agrandissement", 1, 8, 1, "×",
                                           "Multiplie la taille du fichier final, avec des pixels bien nets."))
        conteneur = QWidget()
        rl = QHBoxLayout(conteneur)
        rl.setContentsMargins(18, 8, 18, 2)
        b = self._bouton("Tout remettre à zéro", "reinit")
        b.clicked.connect(lambda: (self._appliquer_reglages({}),
                                   self.vue.dire("Et voilà, tout est remis à zéro")))
        rl.addWidget(b)
        s.ajouter(conteneur)
        lay.addStretch()
        defile.setWidget(interieur)
        return carte

    def _miniature_prete(self, generation, nom, image):
        if generation == self.miniatures.generation():
            self.galerie.definir_image(nom, image)


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
        for s in self.sections:  # le voyant d'une section s'allume quand elle est modifiée
            s.marquer(any(self.c[k].valeur() != moteur.REGLAGES_DEFAUT[k] for k in s.cles))
        # Le style de la galerie reste surligné tant qu'on n'y a pas touché
        actif = self._style_actif
        self.galerie.marquer_actif(actif[0] if actif and actif[1] == self._etat_style() else None)

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
        self.vue.dire(f"Hop, {section.titre} remis à zéro")

    def _appliquer_style(self, nom):
        self._appliquer_reglages(STYLES[nom])
        self._style_actif = (nom, self._etat_style())
        self.galerie.marquer_actif(nom)
        self.vue.dire(f"Hop, style « {nom} »")

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
        self.vue.dire(f"{random.choice(phrases)}  ·  {r['palette_nom']}, {r['algorithme']}")

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
        if anime:
            self.timeline.blockSignals(True)
            self.timeline.setRange(0, self.vinfo["frames"] - 1)
            self.timeline.setValue(0)
            self.timeline.blockSignals(False)
            self._maj_temps()
        self.b_exporter.setEnabled(True)
        self.miniatures.calculer(src)
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
        # Même image, mêmes réglages, même frame : l'aperçu affiché est déjà le bon
        demande = (self._reglages_courants, id(self.src) if self.vinfo is None else self.vinfo["chemin"],
                   self.frame)
        if demande == self._derniere_demande:
            return
        self._derniere_demande = demande
        self.etat.definir(calcul=True)
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
        palette = self._reglages_courants.get("palette", [])
        self.etat.definir(f"{out.shape[1]}×{out.shape[0]}  ·  {len(palette)} couleurs  ·  {fin}",
                          palette, calcul=False)

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
        self.b_lecture.setIcon(t.icone("pause", t.ENCRE))

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
            self.b_lecture.setIcon(t.icone("lecture", t.ENCRE))
            self._derniere_demande = None  # la lecture a remplacé l'aperçu : on le recalcule
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
        self.vue.dire(f"Et voilà ! Fini en {duree:.1f} s", 3.5)
        boite = QMessageBox(self)
        boite.setWindowTitle("C'est fini")
        boite.setIconPixmap(pixmap_crabe(3))
        boite.setText(f"Et voilà !\n\n« {os.path.basename(chemin)} » est prêt.")
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
        self.miniatures.arreter()
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
    t.charger_polices()
    app.setStyleSheet(t.feuille_de_style())
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
        f.miniatures.arreter()
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
    t.charger_polices()
    app.setStyleSheet(t.feuille_de_style())
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

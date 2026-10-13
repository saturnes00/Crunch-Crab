"""
Crunch Crab — composants du panneau de réglages.

  - Glissiere   : curseur dessiné comme un bargraphe (VU-mètre de table de mixage)
  - Curseur     : nom + valeur + glissière + petite phrase d'explication
  - Interrupteur, Liste : idem pour un oui/non et une liste de choix
  - Section     : bloc repliable numéroté, avec un voyant quand il est modifié
  - Nuancier    : les couleurs de la palette
  - Galerie     : les styles tout prêts, en miniatures calculées sur ton image
"""

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractButton, QColorDialog, QComboBox, QGridLayout, QHBoxLayout,
                               QLabel, QPushButton, QSlider, QSizePolicy, QVBoxLayout, QWidget)

import theme as t

MARGE = 18  # marge intérieure gauche/droite du panneau


def _etiquette_aide(texte):
    aide = QLabel(texte)
    aide.setObjectName("aide")
    aide.setWordWrap(True)
    return aide


# ---------------------------------------------------------------------------
# Glissière en bargraphe
# ---------------------------------------------------------------------------

class Glissiere(QSlider):
    """Un QSlider (clavier, accessibilité, signaux) redessiné en rangée de petites barres.

    - Les réglages à deux sens (ex. -100 → 100) se remplissent depuis le centre.
    - Un clic place directement la valeur ; double-clic : valeur de départ.
    - La molette fait défiler le panneau au lieu de changer la valeur par accident
      (sauf si le curseur a été cliqué juste avant).
    """
    doubleClic = Signal()

    LARGEUR_BARRE = 3
    ECART = 2

    def __init__(self, mini, maxi, defaut, neutre=None):
        super().__init__(Qt.Orientation.Horizontal)
        self.setRange(mini, maxi)
        self.setValue(defaut)
        self.defaut = defaut
        # Point d'où part le remplissage : la valeur « sans effet » (0, ou 100 % pour un gamma…)
        self.origine = neutre if neutre is not None else (0 if mini < 0 < maxi else mini)
        self.setFixedHeight(20)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._survol = False

    def _ratio(self, v):
        etendue = max(1, self.maximum() - self.minimum())
        return (v - self.minimum()) / etendue

    def _zone(self):
        return QRectF(6, 0, self.width() - 12, self.height())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        zone = self._zone()
        pas = self.LARGEUR_BARRE + self.ECART
        n = max(2, int((zone.width() + self.ECART) // pas))
        debut = zone.left() + (zone.width() - (n * pas - self.ECART)) / 2
        r_val, r_orig = self._ratio(self.value()), self._ratio(self.origine)
        bas, haut = sorted((r_orig, r_val))
        actif = self.isEnabled()
        eteinte = QColor(t.BORD_FORT)
        # À sa valeur de départ, le réglage reste gris : seul ce qu'on a touché s'allume
        au_repos = self.value() == self.defaut
        grise = QColor(t.TRES_DISCRET)
        cy = zone.center().y()
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(n):
            pos = i / (n - 1)
            allumee = actif and bas - 1e-9 <= pos <= haut + 1e-9 and r_val != r_orig
            # Les barres grandissent un peu vers la valeur, comme un VU-mètre
            h = 10 if allumee else 6
            p.setBrush((grise if au_repos else t.couleur_degrade(pos)) if allumee else eteinte)
            p.drawRoundedRect(QRectF(debut + i * pas, cy - h / 2, self.LARGEUR_BARRE, h), 1, 1)
        # Repère de la valeur de départ (petit point sous la rangée)
        x0 = zone.left() + self._ratio(self.defaut) * zone.width()
        p.setBrush(QColor(t.TRES_DISCRET))
        p.drawEllipse(QPointF(x0, cy + 8), 1.2, 1.2)
        # Poignée : un trait vertical clair, souligné d'accent au survol
        x = zone.left() + r_val * zone.width()
        if self._survol or self.isSliderDown():
            p.setBrush(QColor(255, 91, 58, 70))
            p.drawRoundedRect(QRectF(x - 5, cy - 10, 10, 20), 4, 4)
        p.setBrush(QColor(t.TEXTE) if actif else QColor(t.TRES_DISCRET))
        p.drawRoundedRect(QRectF(x - 2, cy - 8, 4, 16), 2, 2)

    def _valeur_en(self, x):
        zone = self._zone()
        r = min(1.0, max(0.0, (x - zone.left()) / max(1.0, zone.width())))
        return round(self.minimum() + r * (self.maximum() - self.minimum()))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.setSliderDown(True)
            self.setValue(self._valeur_en(e.position().x()))
            e.accept()

    def mouseMoveEvent(self, e):
        if self.isSliderDown():
            self.setValue(self._valeur_en(e.position().x()))

    def mouseReleaseEvent(self, _):
        self.setSliderDown(False)
        self.update()

    def mouseDoubleClickEvent(self, _):
        self.setValue(self.defaut)
        self.doubleClic.emit()

    def wheelEvent(self, e):
        if self.hasFocus():
            super().wheelEvent(e)
        else:
            e.ignore()

    def enterEvent(self, _):
        self._survol = True
        self.update()

    def leaveEvent(self, _):
        self._survol = False
        self.update()


# ---------------------------------------------------------------------------
# Lignes de réglage
# ---------------------------------------------------------------------------

class Curseur(QWidget):
    change = Signal()

    def __init__(self, nom, mini, maxi, defaut, suffixe="", aide="", neutre=None):
        super().__init__()
        self.defaut = defaut
        self.suffixe = suffixe
        lay = QVBoxLayout(self)
        lay.setContentsMargins(MARGE, 6, MARGE, 6)
        lay.setSpacing(4)
        self.haut = QHBoxLayout()
        self.haut.setSpacing(6)
        self.etiquette = QLabel(nom)
        self.etiquette.setObjectName("etiquette")
        self.etiquette.setToolTip("Double-clic pour revenir à la valeur de départ")
        self.val = QLabel()
        self.val.setObjectName("valeur")
        self.haut.addWidget(self.etiquette)
        self.haut.addStretch()
        self.haut.addWidget(self.val)
        self.slider = Glissiere(mini, maxi, defaut, neutre)
        self.slider.valueChanged.connect(self._maj)
        lay.addLayout(self.haut)
        lay.addWidget(self.slider)
        if aide:
            lay.addWidget(_etiquette_aide(aide))
        self._modifie = None
        self._maj()

    def _maj(self):
        v = self.slider.value()
        self.val.setText(f"{v}{self.suffixe}")
        modifie = v != self.defaut
        if modifie != self._modifie:  # on ne repolit le style que si l'état change
            self._modifie = modifie
            self.val.setProperty("modifie", modifie)
            self.val.style().unpolish(self.val)
            self.val.style().polish(self.val)
        self.change.emit()

    def mouseDoubleClickEvent(self, _):
        self.slider.setValue(self.defaut)

    def valeur(self):
        return self.slider.value()

    def definir(self, v):
        self.slider.setValue(int(v))


class Bascule(QAbstractButton):
    """Interrupteur dessiné : pastille qui glisse, fond en dégradé quand c'est activé."""

    def __init__(self):
        super().__init__()
        self.setCheckable(True)
        self.setFixedSize(34, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pos = 0.0
        self._anim = QVariantAnimation(self, duration=140)
        self._anim.valueChanged.connect(self._bouger)
        self.toggled.connect(self._animer)

    def _bouger(self, v):
        self._pos = float(v)
        self.update()

    def _animer(self, coche):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if coche else 0.0)
        self._anim.start()

    def placer(self, coche):
        """Change l'état sans animation (chargement d'un style)."""
        self.blockSignals(True)
        self.setChecked(coche)
        self.blockSignals(False)
        self._anim.stop()
        self._pos = 1.0 if coche else 0.0
        self.update()

    def sizeHint(self):
        return QSize(34, 20)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(QPen(QColor(t.BORD_FORT), 1))
        p.setBrush(QColor(t.CHAMP))
        p.drawRoundedRect(r, 10, 10)
        if self._pos > 0:
            p.setOpacity(self._pos)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(t.degrade(r))
            p.drawRoundedRect(r, 10, 10)
            p.setOpacity(1)
        x = 3 + self._pos * (self.width() - 20)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.TEXTE) if self._pos > 0.5 else QColor(t.DISCRET))
        p.drawEllipse(QRectF(x, 3, 14, 14))


class Interrupteur(QWidget):
    change = Signal()

    def __init__(self, nom, defaut, aide=""):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(MARGE, 7, MARGE, 7)
        lay.setSpacing(3)
        ligne = QHBoxLayout()
        etiquette = QLabel(nom)
        etiquette.setObjectName("etiquette")
        self.case = Bascule()
        self.case.placer(defaut)
        self.case.toggled.connect(lambda _: self.change.emit())
        ligne.addWidget(etiquette)
        ligne.addStretch()
        ligne.addWidget(self.case)
        lay.addLayout(ligne)
        if aide:
            lay.addWidget(_etiquette_aide(aide))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e):
        # Toute la ligne est cliquable, pas seulement l'interrupteur
        if e.button() == Qt.MouseButton.LeftButton:
            self.case.toggle()

    def valeur(self):
        return self.case.isChecked()

    def definir(self, v):
        if bool(v) != self.case.isChecked():
            self.case.placer(bool(v))
            self.change.emit()


class Liste(QWidget):
    """Liste de choix, avec des flèches ‹ › pour passer d'un choix à l'autre."""
    change = Signal()

    def __init__(self, nom, choix, aide="", fleches=False):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(MARGE, 6, MARGE, 6)
        lay.setSpacing(5)
        if nom:
            e = QLabel(nom)
            e.setObjectName("etiquette")
            lay.addWidget(e)
        ligne = QHBoxLayout()
        ligne.setSpacing(6)
        self.combo = QComboBox()
        self.combo.addItems(choix)
        self.combo.setMaxVisibleItems(25)
        self.combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo.currentTextChanged.connect(lambda _: self.change.emit())
        ligne.addWidget(self.combo, 1)
        if fleches:
            for nom_icone, pas, bulle in (("gauche", -1, "Choix précédent"), ("droite", 1, "Choix suivant")):
                b = QPushButton()
                b.setObjectName("fleche")
                b.setIcon(t.icone(nom_icone, t.DISCRET, 14))
                b.setToolTip(bulle)
                b.setFixedHeight(30)
                b.setCursor(Qt.CursorShape.PointingHandCursor)
                b.clicked.connect(lambda _=False, pas=pas: self.decaler(pas))
                ligne.addWidget(b)
        lay.addLayout(ligne)
        if aide:
            lay.addWidget(_etiquette_aide(aide))

    def decaler(self, pas):
        n = self.combo.count()
        self.combo.setCurrentIndex((self.combo.currentIndex() + pas) % n)

    def valeur(self):
        return self.combo.currentText()

    def definir(self, v):
        self.combo.setCurrentText(v)


# ---------------------------------------------------------------------------
# Section repliable
# ---------------------------------------------------------------------------

class _EnTete(QWidget):
    """Ligne de titre d'une section : numéro, titre en police pixel, voyant, chevron."""
    clic = Signal()

    def __init__(self, numero, titre):
        super().__init__()
        self.numero = f"{numero:02d}"
        self.titre = titre.upper()
        self.ouvert = False
        self.modifiee = False
        self._survol = False
        self.setFixedHeight(44)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cy = self.height() / 2
        p.setFont(t.police_pixel(8))
        p.setPen(QColor(t.TRES_DISCRET))
        p.drawText(QRectF(MARGE, 0, 30, self.height()), Qt.AlignmentFlag.AlignVCenter, self.numero)
        p.setFont(t.police_pixel(16))
        p.setPen(QColor(t.ACCENT_CLAIR if self._survol else t.TEXTE))
        largeur = p.fontMetrics().horizontalAdvance(self.titre)
        p.drawText(QRectF(MARGE + 24, 0, largeur + 4, self.height()), Qt.AlignmentFlag.AlignVCenter,
                   self.titre)
        t.point_lumineux(p, QPointF(MARGE + 24 + largeur + 12, cy), 3, t.ACCENT, self.modifiee)
        pix = t.pixmap_icone("bas" if self.ouvert else "droite", t.DISCRET, 14)
        p.drawPixmap(QPointF(self.width() - 22, cy - 7), pix)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clic.emit()

    def enterEvent(self, _):
        self._survol = True
        self.update()

    def leaveEvent(self, _):
        self._survol = False
        self.update()


class Section(QWidget):
    """Bloc repliable : un titre numéroté, une phrase d'explication, un bouton de remise à zéro."""
    _compteur = 0

    def __init__(self, titre, sous_titre, ouvert=False, reinit=None):
        super().__init__()
        Section._compteur += 1
        self.titre = titre
        self.cles = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        trait = QWidget()
        trait.setFixedHeight(1)
        trait.setStyleSheet(f"background: {t.BORD};")
        lay.addWidget(trait)
        tete = QHBoxLayout()
        tete.setContentsMargins(0, 0, MARGE - 8 if reinit else 0, 0)
        tete.setSpacing(2)
        self.entete = _EnTete(Section._compteur, titre)
        self.entete.clic.connect(self.basculer)
        tete.addWidget(self.entete, 1)
        if reinit:
            b = QPushButton()
            b.setObjectName("reinit")
            b.setIcon(t.icone("reinit", t.TRES_DISCRET, 14))
            b.setToolTip("Remettre cette section à zéro")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda: reinit(self))
            tete.addWidget(b)
        lay.addLayout(tete)
        self.corps = QWidget()
        self.corps_lay = QVBoxLayout(self.corps)
        self.corps_lay.setContentsMargins(0, 0, 0, 10)
        self.corps_lay.setSpacing(0)
        st = QLabel(sous_titre)
        st.setObjectName("sousTitre")
        st.setWordWrap(True)
        self.corps_lay.addWidget(st)
        lay.addWidget(self.corps)
        self.corps.setVisible(ouvert)
        self.entete.ouvert = ouvert
        self.modifiee = False

    def marquer(self, modifiee):
        if modifiee != self.modifiee:
            self.modifiee = modifiee
            self.entete.modifiee = modifiee
            self.entete.update()

    def basculer(self):
        self.corps.setVisible(not self.corps.isVisible())
        self.entete.ouvert = self.corps.isVisible()
        self.entete.update()

    def ajouter(self, w, cle=None):
        self.corps_lay.addWidget(w)
        if cle:
            self.cles.append(cle)
        return w


# ---------------------------------------------------------------------------
# Nuancier
# ---------------------------------------------------------------------------

class Nuancier(QWidget):
    """Affiche les couleurs de la palette ; clic = modifier, clic droit = supprimer."""
    modifie = Signal(list)

    def __init__(self):
        super().__init__()
        self.couleurs = []
        self.grille = QGridLayout(self)
        self.grille.setContentsMargins(MARGE, 6, MARGE, 6)
        self.grille.setSpacing(6)

    def definir(self, couleurs):
        if list(couleurs) == self.couleurs and self.grille.count():
            return  # rien n'a changé : on évite de reconstruire les boutons
        self.couleurs = list(couleurs)
        while self.grille.count():
            w = self.grille.takeAt(0).widget()
            w.hide()
            w.deleteLater()
        par_ligne = 9
        for i, c in enumerate(self.couleurs + ["+"]):
            b = QPushButton()
            b.setFixedSize(26, 26)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            if c == "+":
                b.setIcon(t.icone("plus", t.DISCRET, 12))
                b.setToolTip("Ajouter une couleur")
                b.setStyleSheet(f"border-radius: 7px; border: 1px dashed {t.BORD_FORT};"
                                "background: transparent; padding: 0;")
                b.clicked.connect(self._ajouter)
                b.setEnabled(len(self.couleurs) < 64)
            else:
                b.setToolTip(f"{c}\nClic : modifier · Clic droit : supprimer")
                b.setStyleSheet(f"background: {c}; border-radius: 7px; padding: 0;"
                                "border: 1px solid rgba(255,255,255,40);")
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
# Galerie de styles
# ---------------------------------------------------------------------------

class Vignette(QAbstractButton):
    LARGEUR, HAUTEUR = 92, 64

    def __init__(self, nom):
        super().__init__()
        self.nom = nom
        self.image = None
        self.actif = False
        self._survol = False
        self.setFixedSize(self.LARGEUR, self.HAUTEUR + 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(f"Appliquer le style « {nom} »")

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cadre = QRectF(1, 1, self.width() - 2, self.HAUTEUR - 2)
        chemin = QPainterPath()
        chemin.addRoundedRect(cadre, 9, 9)
        p.save()
        p.setClipPath(chemin)
        if self.image is not None:
            p.drawImage(cadre, self.image)
        else:
            p.fillRect(cadre, QColor(t.CHAMP))
        p.restore()
        if self.actif:
            p.setPen(QPen(t.degrade(cadre), 2))
        else:
            p.setPen(QPen(QColor(t.BORD_FORT if self._survol else t.BORD), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(chemin)
        p.setFont(t.police_pixel(8))
        p.setPen(QColor(t.TEXTE if (self._survol or self.actif) else t.DISCRET))
        nom = p.fontMetrics().elidedText(self.nom.upper(), Qt.TextElideMode.ElideRight, self.width())
        p.drawText(QRectF(0, self.HAUTEUR + 4, self.width(), 14), Qt.AlignmentFlag.AlignLeft, nom)

    def enterEvent(self, _):
        self._survol = True
        self.update()

    def leaveEvent(self, _):
        self._survol = False
        self.update()


class Galerie(QWidget):
    """Grille des styles tout prêts. Les miniatures sont fournies par la fenêtre (calcul en arrière-plan)."""
    choisi = Signal(str)

    def __init__(self, noms):
        super().__init__()
        grille = QGridLayout(self)
        grille.setContentsMargins(MARGE, 4, MARGE, 8)
        grille.setHorizontalSpacing(8)
        grille.setVerticalSpacing(6)
        self.vignettes = {}
        for i, nom in enumerate(noms):
            v = Vignette(nom)
            v.clicked.connect(lambda _=False, nom=nom: self.choisi.emit(nom))
            grille.addWidget(v, i // 3, i % 3)
            self.vignettes[nom] = v

    def definir_image(self, nom, image):
        v = self.vignettes.get(nom)
        if v is not None:
            v.image = image
            v.update()

    def marquer_actif(self, nom):
        for n, v in self.vignettes.items():
            if v.actif != (n == nom):
                v.actif = n == nom
                v.update()

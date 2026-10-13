# 🦀 Crunch Crab

**Crunch Crab** est une application macOS open source, elle permet de transformer vos images, GIF et vidéos en pixels tramés. Tramage, glitch, aberration chromatique, effets d'écran CRT ou de cassette VHS : tout se règle en direct, et l'export garde le son de vos vidéos.

Inspirée de DitherBoy, elle se veut gratuite, ouverte et facile à bidouiller.

---

## Installation MAC OS

### Prérequis
- macOS
- [Homebrew](https://brew.sh)
- Python 3.13 et ffmpeg (installés à l'étape suivante)

### Étapes
```bash
# 1. Installer les dépendances système
brew install ffmpeg python@3.13

# 2. Créer un environnement Python isolé
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3. Générer l'application
./creer_app.sh
```

L'application **Crunch Crab** apparaît ensuite dans `~/Applications`. Il suffit de relancer `creer_app.sh` pour la mettre à jour après une modification du code.

---

## Fonctionnalités

### 🎨 Tramage et couleurs
- **23 méthodes de tramage** : Floyd-Steinberg, Atkinson, Bayer, bruit bleu, trames (points, lignes, croix, vagues), demi-teinte…
- **17 palettes** prédéfinies, plus les niveaux de gris, une palette extraite automatiquement de l'image et une palette entièrement personnalisable

### 🛠️ Retouche
Luminosité, contraste, gamma, saturation, teinte, température, flou, netteté et encrage des contours.

### 🌀 Déformations
Miroir et kaléidoscope, ondulation, tri de pixels (*pixel sorting*).

### ⚡ Glitch
Tranches décalées, blocs corrompus et lignes étirées, en version fixe ou animée.

### 🔦 Optique
Aberration chromatique, décalage RVB orientable, bavure VHS, lueur et fuite de lumière.

### 📺 Effets d'écran
Artefacts JPEG, postérisation, bande VHS, lignes de balayage CRT, grille de phosphore, courbure d'écran, vignettage et grain.

### ✨ Confort d'utilisation
- **15 styles prêts à l'emploi** pour démarrer vite
- Bouton 🎲 **« Surprends-moi »** pour des combinaisons aléatoires
- Annuler / rétablir illimité
- Comparaison avant / après avec séparateur glissant
- Sauvegarde et chargement de vos propres styles

### 💾 Export
| Format | Usage |
|---|---|
| PNG | Image fixe |
| GIF | Animation légère |
| MP4 | Vidéo avec le son |
| MOV ProRes | Qualité maximale, idéal pour le montage |

---

## Raccourcis clavier

| Raccourci | Action |
|---|---|
| `⌘O` / `⌘E` | Ouvrir / exporter |
| `⌘S` / `⌘L` | Enregistrer / charger un style |
| `⌘Z` / `⇧⌘Z` | Annuler / rétablir |
| `R` | Surprends-moi |
| `C` | Comparer avant / après (glisser le séparateur) |
| `Espace` | Lecture / pause |
| `⌘0` / `⌘1` / `⌘2` | Ajuster à la fenêtre / taille réelle / zoom 2× |
| Pincement trackpad | Zoomer |
| Double-clic sur un réglage | Revenir à la valeur par défaut |

---

## Structure du projet

| Fichier | Rôle |
|---|---|
| `moteur.py` | Le cœur de l'app : tramage, palettes et effets |
| `video.py` | Lecture et écriture des vidéos et GIF via ffmpeg |
| `app.py` | L'interface utilisateur (les couleurs du thème sont définies en haut du fichier) |
| `creer_app.sh` | Crée ou met à jour l'application dans `~/Applications` |

---

## Contribuer

Les contributions sont les bienvenues ! Nouvelle méthode de tramage, palette, effet ou simple correction : ouvrez une *issue* ou proposez une *pull request*.

## Licence

Je sais pas comment sa marche ca par contre

#!/bin/bash
# Ajoute Crunch Crab au menu des applications (à lancer une fois, depuis ce dossier).
set -e
ICI="$(cd "$(dirname "$0")" && pwd)"
mkdir -p ~/.local/share/applications ~/.local/share/icons
cp "$ICI/icone.png" ~/.local/share/icons/crunchcrab.png
cat > ~/.local/share/applications/crunchcrab.desktop <<FIN
[Desktop Entry]
Type=Application
Name=Crunch Crab
Comment=Tramage, glitch et effets rétro pour images et vidéos
Exec="$ICI/CrunchCrab" %f
Icon=crunchcrab
Terminal=false
Categories=Graphics;Video;
FIN
echo "🦀 C'est bon, Crunch Crab est dans ton menu d'applications."

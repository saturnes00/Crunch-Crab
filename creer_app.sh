#!/bin/bash
# Mode développement (macOS) : crée « Crunch Crab.app » dans ~/Applications, qui lance
# directement le code de ce dossier (tes modifications sont prises en compte tout de suite).
# À relancer si tu déplaces le dossier CrunchCrab.
# Pour une app autonome à partager : pyinstaller crunchcrab.spec (voir README).
set -e
cd "$(dirname "$0")"
DOSSIER="$(pwd)"
APP="$HOME/Applications/Crunch Crab.app"

# 1. Icônes (png, ico, icns) dessinées par le moteur lui-même
.venv/bin/python outils/icones.py

# 2. Le paquet .app : un simple dossier avec une structure précise
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp icone.icns "$APP/Contents/Resources/icone.icns"
cat > "$APP/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Crunch Crab</string>
  <key>CFBundleDisplayName</key><string>Crunch Crab</string>
  <key>CFBundleIdentifier</key><string>local.crunchcrab</string>
  <key>CFBundleVersion</key><string>1.1</string>
  <key>CFBundleShortVersionString</key><string>1.1</string>
  <key>CFBundleExecutable</key><string>CrunchCrab</string>
  <key>CFBundleIconFile</key><string>icone</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
EOF
cat > "$APP/Contents/MacOS/CrunchCrab" <<EOF
#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:\$PATH"
exec "$DOSSIER/.venv/bin/python" "$DOSSIER/app.py" "\$@" 2>>"$DOSSIER/erreurs.log"
EOF
chmod +x "$APP/Contents/MacOS/CrunchCrab"
touch "$APP"
echo "🦀 Application créée : $APP"

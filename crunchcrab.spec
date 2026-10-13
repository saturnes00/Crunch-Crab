# Recette PyInstaller : transforme le code Python en application autonome.
#   pyinstaller crunchcrab.spec
# Résultat dans dist/ : « Crunch Crab.app » (macOS), dossier CrunchCrab avec CrunchCrab.exe
# (Windows) ou l'exécutable CrunchCrab (Linux). Python, Qt et ffmpeg sont inclus.
import sys

MAC = sys.platform == "darwin"
WINDOWS = sys.platform.startswith("win")
VERSION = "1.2.0"

a = Analysis(
    ["app.py"],
    # La police pixel des titres (Silkscreen, licence OFL) voyage avec sa licence
    datas=[("icone.png", "."), ("polices/*.ttf", "polices"), ("polices/OFL-Silkscreen.txt", "polices")],
    # ffmpeg (fourni par imageio-ffmpeg) est inclus automatiquement par son hook PyInstaller
    hiddenimports=["imageio_ffmpeg", "PySide6.QtSvg"],
    excludes=["tkinter", "matplotlib", "scipy", "pandas", "IPython", "PySide6.QtNetwork",
              "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtPdf", "PySide6.QtWebEngineCore"],
    # Garde moteur.py en source : Numba en a besoin pour mettre ses compilations en cache
    module_collection_mode={"moteur": "py"},
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CrunchCrab",
    console=False,          # pas de fenêtre de terminal
    icon="icone.icns" if MAC else ("icone.ico" if WINDOWS else None),
    target_arch=None,
)

coll = COLLECT(exe, a.binaries, a.datas, name="CrunchCrab")

if MAC:
    app = BUNDLE(
        coll,
        name="Crunch Crab.app",
        icon="icone.icns",
        bundle_identifier="io.github.saturnes00.crunchcrab",
        version=VERSION,
        info_plist={
            "CFBundleName": "Crunch Crab",
            "CFBundleDisplayName": "Crunch Crab",
            "CFBundleShortVersionString": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )

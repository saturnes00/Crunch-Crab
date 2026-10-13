"""
Lecture et écriture de vidéos / GIF via ffmpeg.

ffmpeg est un programme en ligne de commande. On lui demande d'envoyer les
images brutes (octets RVB) dans un « tuyau » (pipe) que Python lit, puis on
fait l'inverse pour l'export.

Marche sur macOS, Windows et Linux : on utilise le ffmpeg fourni avec
imageio-ffmpeg (rien à installer), sinon celui du système.
"""

import io
import os
import re
import shutil
import subprocess
from functools import lru_cache

import numpy as np
from PIL import Image

EXTENSIONS_VIDEO = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".gif"}
EXTENSIONS_IMAGE = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}

# Sous Windows, évite qu'une fenêtre noire s'ouvre à chaque appel de ffmpeg
SANS_FENETRE = {"creationflags": 0x08000000} if os.name == "nt" else {}


@lru_cache(maxsize=1)
def ffmpeg():
    chemin = os.environ.get("CRUNCHCRAB_FFMPEG")
    if chemin and os.path.exists(chemin):
        return chemin
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    # Une app lancée depuis le Finder ne connaît pas le PATH du Terminal
    for chemin in (shutil.which("ffmpeg"), "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        if chemin and os.path.exists(chemin):
            return chemin
    raise RuntimeError("ffmpeg est introuvable. Installe le paquet imageio-ffmpeg "
                       "(pip install imageio-ffmpeg) ou ffmpeg lui-même.")


def est_video(chemin):
    return os.path.splitext(chemin)[1].lower() in EXTENSIONS_VIDEO


def _executer(args, **kw):
    return subprocess.run([ffmpeg(), "-hide_banner", *args], capture_output=True,
                          **SANS_FENETRE, **kw)


def infos(chemin):
    """Taille, cadence, nombre d'images et présence d'audio d'une vidéo."""
    # On décode la 1re image en PNG : sa taille tient compte de la rotation des vidéos de téléphone
    res = _executer(["-i", chemin, "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"])
    texte = res.stderr.decode(errors="replace")
    if not res.stdout:
        raise RuntimeError("Aucune image lisible dans ce fichier.\n" + texte[-600:])
    w, h = Image.open(io.BytesIO(res.stdout)).size

    flux_video = next((l for l in texte.splitlines() if re.search(r"Stream #.*Video:", l)), "")
    m = re.search(r"([\d.]+) fps", flux_video) or re.search(r"([\d.]+)k? tbr", flux_video)
    fps = float(m.group(1)) if m else 25.0
    if not 0 < fps <= 240:
        fps = 25.0
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", texte)
    duree = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    n = round(duree * fps) if duree else _compter_images(chemin)
    audio = bool(re.search(r"Stream #.*Audio:", texte))
    return {"largeur": w, "hauteur": h, "fps": fps, "frames": max(1, n), "duree": duree,
            "audio": audio}


def _compter_images(chemin):
    res = _executer(["-i", chemin, "-map", "0:v:0", "-f", "null", "-"])
    trouve = re.findall(r"frame=\s*(\d+)", res.stderr.decode(errors="replace"))
    return int(trouve[-1]) if trouve else 1


class Lecteur:
    """Lit les images d'une vidéo une par une à partir d'un instant donné."""

    def __init__(self, chemin, info, debut=0.0):
        self.w, self.h = info["largeur"], info["hauteur"]
        cmd = [ffmpeg(), "-v", "error"]
        if debut > 0:
            cmd += ["-ss", f"{debut:.3f}"]
        cmd += ["-i", chemin, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     bufsize=self.w * self.h * 3, **SANS_FENETRE)

    def lire(self):
        n = self.w * self.h * 3
        octets = self.proc.stdout.read(n)
        if len(octets) < n:
            return None
        return np.frombuffer(octets, np.uint8).reshape(self.h, self.w, 3)

    def fermer(self):
        try:
            self.proc.kill()
            self.proc.wait(timeout=2)
        except Exception:
            pass


def lire_frame(chemin, info, t):
    lecteur = Lecteur(chemin, info, t)
    try:
        return lecteur.lire()
    finally:
        lecteur.fermer()


class Ecrivain:
    """Envoie des images à ffmpeg pour créer un MP4, un MOV (ProRes) ou un GIF."""

    def __init__(self, chemin, w, h, fps, source=None):
        ext = os.path.splitext(chemin)[1].lower()
        cmd = [ffmpeg(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{w}x{h}", "-r", f"{fps:.5f}", "-i", "-"]
        if ext == ".gif":
            cmd += ["-vf", "split[a][b];[a]palettegen=stats_mode=full:reserve_transparent=0[p];"
                           "[b][p]paletteuse=dither=none:diff_mode=rectangle", "-loop", "0", chemin]
        else:
            if source:  # récupère le son de la vidéo d'origine s'il existe
                cmd += ["-i", source, "-map", "0:v", "-map", "1:a?", "-shortest"]
            pad = ["-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2"]
            if ext == ".mov":
                cmd += pad + ["-c:v", "prores_ks", "-profile:v", "3",
                              "-pix_fmt", "yuv422p10le", "-c:a", "pcm_s16le", chemin]
            else:
                cmd += pad + ["-c:v", "libx264", "-preset", "medium", "-crf", "14",
                              "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                              "-movflags", "+faststart", chemin]
        self.chemin = chemin
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE,
                                     **SANS_FENETRE)

    def ecrire(self, img):
        self.proc.stdin.write(np.ascontiguousarray(img).tobytes())

    def terminer(self):
        self.proc.stdin.close()
        erreur = self.proc.stderr.read().decode(errors="replace")
        if self.proc.wait() != 0:
            raise RuntimeError("ffmpeg a échoué :\n" + erreur[-1500:])

    def annuler(self):
        try:
            self.proc.kill()
            self.proc.wait(timeout=2)
        except Exception:
            pass
        if os.path.exists(self.chemin):
            os.remove(self.chemin)

"""Logo y pista que sube el comercio: se revisan y se normalizan antes de guardarlos."""

from __future__ import annotations

import io
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 40_000_000
MAX_LOGO = 5 * 1024 * 1024
MAX_PISTA = 20 * 1024 * 1024
SEGUNDOS_PISTA = 60


def color_de_logo(imagen: Image.Image) -> str | None:
    """El color más presente en el logo, sin contar transparencias, blancos ni negros."""
    p = np.asarray(imagen.convert("RGBA").resize((96, 96))).reshape(-1, 4)
    p = p[p[:, 3] > 128][:, :3].astype(int)
    p = p[(p.max(1) - p.min(1)) > 40]  # solo lo que tiene color
    if not len(p):
        return None
    grupos, cuantos = np.unique(p // 32, axis=0, return_counts=True)
    r, g, b = (grupos[cuantos.argmax()] * 32 + 16).tolist()
    return f"#{r:02X}{g:02X}{b:02X}"


def guardar_logo(contenido: bytes, destino: Path) -> str | None:
    """Guarda el logo como PNG y devuelve el color sugerido. ValueError si no es una imagen."""
    if len(contenido) > MAX_LOGO:
        raise ValueError("Use a logo under 5 MB")
    try:
        imagen = Image.open(io.BytesIO(contenido))
        imagen.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValueError("Use a PNG or JPG logo")
    imagen = imagen.convert("RGBA")
    imagen.thumbnail((800, 800), Image.LANCZOS)
    imagen.save(destino)
    return color_de_logo(imagen)


def guardar_pista(contenido: bytes, destino: Path) -> None:
    """Deja la pista en AAC y corta a 60 s. ValueError si ffmpeg no la reconoce."""
    if len(contenido) > MAX_PISTA:
        raise ValueError("Use a track under 20 MB")
    nueva = destino.with_name(destino.stem + "_nueva.m4a")
    with tempfile.NamedTemporaryFile() as original:
        original.write(contenido)
        original.flush()
        try:
            r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-protocol_whitelist", "file,pipe", "-i", original.name,
                                "-vn", "-t", str(SEGUNDOS_PISTA), "-c:a", "aac", "-b:a", "160k", "-f", "ipod", str(nueva)],
                               capture_output=True, timeout=60)
        except subprocess.TimeoutExpired:
            r = None
    if r is None or r.returncode != 0:
        nueva.unlink(missing_ok=True)
        raise ValueError("Use an MP3 or M4A track")
    nueva.replace(destino)  # la pista anterior solo se reemplaza si la nueva sirve

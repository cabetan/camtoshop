"""Efectos visuales del Reel: texto detrás del sujeto, imágenes con movimiento y portada."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ANCHO, ALTO, FPS = 1080, 1920, 30
FUENTES = Path(__file__).resolve().parents[1] / "assets" / "fonts"
NEGRA = FUENTES / "BarlowCondensed-Black.ttf"
AMARILLO = "#FFD23F"


def fuente_que_cabe(texto: str, ruta: Path, maximo: int, ancho: float) -> ImageFont.FreeTypeFont:
    tamano = maximo
    fuente = ImageFont.truetype(str(ruta), tamano)
    while fuente.getlength(texto) > ancho and tamano > 40:
        tamano -= 8
        fuente = ImageFont.truetype(str(ruta), tamano)
    return fuente


def capa_de_texto(lineas: list[str], y: float, escala: float = 1.0) -> Image.Image:
    capa = Image.new("RGBA", (ANCHO, ALTO))
    dibujar_lineas(ImageDraw.Draw(capa), lineas, y, escala)
    return capa


def ubicar_texto(lineas: list[str], sujeto: np.ndarray, maximo_tapado: float = 0.12) -> tuple[float, float]:
    """(altura, escala) más grande donde el sujeto tapa como mucho el 12 % del texto.

    Que el sujeto tape un poco es el efecto; que tape el precio lo arruina. Si no cabe
    grande, se achica hasta caber en el espacio libre, normalmente encima de la cabeza.
    """
    mejor, menor = (120.0, 0.5), 1.0
    for escala in (1.0, 0.85, 0.72, 0.62, 0.52):
        for y in range(60, 1300, 30):
            texto = np.asarray(capa_de_texto(lineas, y, escala).getchannel("A")) > 0
            if not texto.any():
                continue
            tapado = (texto & (sujeto > 0)).sum() / texto.sum()
            if tapado <= maximo_tapado:
                return float(y), escala
            if tapado < menor:
                mejor, menor = (float(y), escala), tapado
    return mejor


def dibujar_lineas(lienzo: ImageDraw.ImageDraw, lineas: list[str], y: float, escala: float = 1.0,
                   colores: tuple[str, ...] = ("white", AMARILLO, "white"), sombra: bool = False) -> None:
    for linea, color in zip(lineas, colores):
        fuente = fuente_que_cabe(linea, NEGRA, int(380 * escala), ANCHO * 0.92 * escala)
        x = (ANCHO - fuente.getlength(linea)) / 2
        if sombra:
            lienzo.text((x + 6, y + 8), linea, font=fuente, fill=(0, 0, 0, 140))
        lienzo.text((x, y), linea, font=fuente, fill=color)
        y += fuente.size * 0.9


def texto_detras(cuadros: list[Path], sujetos: dict[int, np.ndarray], lineas: list[str], destino: Path) -> Path:
    """Compone cada cuadro: fondo apagado, texto gigante y el sujeto (persona + producto) encima.

    El texto entra creciendo en los primeros 6 cuadros. Si SAM no devolvió máscara para un
    cuadro se usa la del cuadro más cercano.
    """
    carpeta = destino.parent / (destino.stem + "_cuadros")
    carpeta.mkdir(exist_ok=True)
    disponibles = sorted(sujetos)
    union = np.zeros((ALTO, ANCHO), np.uint8)
    for m in sujetos.values():
        union |= m
    altura, tamano = ubicar_texto(lineas, union)
    for n, ruta in enumerate(cuadros):
        foto = Image.open(ruta).convert("RGB")
        cercano = min(disponibles, key=lambda k: abs(k - n)) if disponibles else None
        mascara = sujetos[cercano] if cercano is not None else np.zeros((ALTO, ANCHO), np.uint8)
        alfa = Image.fromarray(mascara * 255).filter(ImageFilter.GaussianBlur(2))
        fondo = ImageEnhance.Brightness(ImageEnhance.Color(foto).enhance(0.55)).enhance(0.5)
        progreso = min(1.0, (n + 1) / 6)
        capa = capa_de_texto(lineas, altura + (1 - progreso) * 40, escala=tamano * (0.9 + 0.1 * progreso))
        if progreso < 1:
            capa.putalpha(capa.getchannel("A").point(lambda a: int(a * progreso)))
        fondo.paste(capa, (0, 0), capa)
        fondo.paste(foto, (0, 0), alfa)
        fondo.save(carpeta / f"{n:04d}.png")
    _codificar(carpeta / "%04d.png", destino)
    return destino


def ajustar_sin_recortar(imagen: Path, destino: Path) -> Path:
    """Lleva la imagen al ancho del Reel y rellena arriba y abajo con el color de sus bordes.

    Sirve para tarjetas con texto, que no se pueden recortar por los lados.
    """
    foto = Image.open(imagen).convert("RGB")
    foto = foto.resize((ANCHO, round(foto.height * ANCHO / foto.width)), Image.LANCZOS)
    arriba = tuple(np.asarray(foto)[:8].reshape(-1, 3).mean(0).astype(int))
    abajo = tuple(np.asarray(foto)[-8:].reshape(-1, 3).mean(0).astype(int))
    lienzo = Image.new("RGB", (ANCHO, ALTO), arriba)
    y = (ALTO - foto.height) // 2
    lienzo.paste(Image.new("RGB", (ANCHO, ALTO - y - foto.height), abajo), (0, y + foto.height))
    lienzo.paste(foto, (0, y))
    lienzo.save(destino)
    return destino


def imagen_en_movimiento(imagen: Path, segundos: float, destino: Path, acercar: float = 0.08) -> Path:
    """Ken Burns: la imagen llena el cuadro vertical y se acerca despacio."""
    cuadros = max(1, round(segundos * FPS))
    filtro = (f"scale={ANCHO * 2}:{ALTO * 2}:force_original_aspect_ratio=increase,crop={ANCHO * 2}:{ALTO * 2},"
              f"zoompan=z='1+{acercar}*on/{cuadros}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
              f"d={cuadros}:s={ANCHO}x{ALTO}:fps={FPS},format=yuv420p")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(imagen), "-vf", filtro,
                    "-frames:v", str(cuadros), "-c:v", "libx264", "-preset", "fast", "-crf", "18", str(destino)],
                   check=True)
    return destino


def portada(imagen: Path, texto: str, destino: Path) -> Path:
    """Foto de estudio con el gancho arriba."""
    foto = Image.open(imagen).convert("RGB")
    escala = max(ANCHO / foto.width, ALTO / foto.height)
    foto = foto.resize((round(foto.width * escala), round(foto.height * escala)), Image.LANCZOS)
    foto = foto.crop(((foto.width - ANCHO) // 2, (foto.height - ALTO) // 2,
                      (foto.width - ANCHO) // 2 + ANCHO, (foto.height - ALTO) // 2 + ALTO))
    capa = Image.new("RGBA", (ANCHO, ALTO))
    palabras = texto.split()
    if len(palabras) <= 3:
        lineas = palabras
    else:
        mitad = (len(palabras) + 1) // 2
        lineas = [" ".join(palabras[:mitad]), " ".join(palabras[mitad:])]
    dibujar_lineas(ImageDraw.Draw(capa), lineas, 160, escala=0.8, sombra=True)
    foto.paste(capa, (0, 0), capa)
    foto.save(destino)
    return destino


def _codificar(patron: Path, destino: Path) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(patron),
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p", str(destino)],
                   check=True)

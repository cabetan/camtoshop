"""Prueba del efecto 'texto detrás del sujeto' sobre un cuadro (exploración)."""

import asyncio
import json
import sys
from pathlib import Path

import meta_sam_parser as P
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from camtoshop.adaptadores import meta_api as M  # noqa: E402

FUENTE = Path(__file__).resolve().parents[1] / "camtoshop" / "assets" / "fonts" / "BarlowCondensed-Black.ttf"


def mascara(cliente, concepto, imagen: Path) -> np.ndarray:
    """Máscara de imagen completa (unión de todas las coincidencias)."""
    cuerpo = {"model": "sam-3.1", "stream": True, "metadata": {"mask_encoding": "one_bit"},
              "input": [{"type": "message", "role": "user", "content": [
                  {"type": "input_text", "text": concepto},
                  {"type": "input_image", "image_url": M._data_url(imagen)}]}]}
    r = cliente._sesion.post(f"{M.URL_BASE}/responses", json=cuerpo, stream=True)
    eventos = [json.loads(l[6:]) for l in r.iter_lines() if l.startswith(b"data: {")]

    async def fuente():
        for e in eventos:
            yield e

    async def leer():
        return await P.parse_responses_stream(fuente(), P.image_segmentation_format()).final_result()

    resultado = asyncio.run(leer())
    ancho, alto = Image.open(imagen).size
    total = np.zeros((alto, ancho), dtype=np.uint8)
    for rec in resultado.records:
        if rec.kind == "mask":
            b = rec.bounds
            raster = np.frombuffer(P.decode_mask_to_raster(rec.mask), dtype=np.uint8).reshape(rec.mask.height, rec.mask.width)
            # En objetos grandes el raster viene reducido: se lleva al tamaño de la caja.
            escalado = Image.fromarray(raster * 255).resize((b.right - b.left, b.bottom - b.top), Image.BILINEAR)
            total[b.top:b.bottom, b.left:b.right] |= (np.asarray(escalado) > 127).astype(np.uint8)
    return total


def main(cuadro: Path, concepto: str, palabras: list[str], destino: Path):
    cliente = M.ClienteMeta()
    foto = Image.open(cuadro).convert("RGB")
    sujeto = mascara(cliente, "person", cuadro) | mascara(cliente, concepto, cuadro)
    alfa = Image.fromarray(sujeto * 255).filter(ImageFilter.GaussianBlur(1.5))

    # Fondo: más oscuro y apagado para que el sujeto resalte.
    fondo = ImageEnhance.Brightness(ImageEnhance.Color(foto).enhance(0.6)).enhance(0.55)
    lienzo = ImageDraw.Draw(fondo)
    y = 150
    for palabra, color in zip(palabras, ["white", "#FFD23F", "white"]):
        tamano = 400
        fuente = ImageFont.truetype(str(FUENTE), tamano)
        while fuente.getlength(palabra) > foto.width * 0.94:
            tamano -= 10
            fuente = ImageFont.truetype(str(FUENTE), tamano)
        x = (foto.width - fuente.getlength(palabra)) / 2
        lienzo.text((x, y), palabra, font=fuente, fill=color)
        y += int(tamano * 0.92)

    # Sujeto con un poco más de contraste y color, encima del texto.
    realce = ImageEnhance.Contrast(ImageEnhance.Color(foto).enhance(1.15)).enhance(1.08)
    fondo.paste(realce, (0, 0), alfa)
    fondo.save(destino, quality=92)


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2], sys.argv[3].split("|"), Path(sys.argv[4]))

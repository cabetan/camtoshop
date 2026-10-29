"""Máscaras de SAM 3.1 cuadro a cuadro, decodificadas con el parser oficial de Meta (meta_sam_parser)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import meta_sam_parser as sam
import numpy as np
from PIL import Image

from camtoshop.adaptadores import meta_api


def _leer(eventos: list[dict], formato):
    async def fuente():
        for e in eventos:
            yield e

    async def leer():
        return await sam.parse_responses_stream(fuente(), formato).final_result()

    return asyncio.run(leer())


def mascaras(cliente: meta_api.ClienteMeta, concepto: str, medio: Path, fuente: tuple[int, int],
             salida_px: tuple[int, int]) -> dict[int, np.ndarray]:
    """{cuadro: máscara uint8 (alto, ancho)} con 1 donde está el concepto; une todas las coincidencias.

    `fuente` es el (ancho, alto) del medio enviado; `salida_px`, el tamaño de las máscaras devueltas.
    """
    ancho, alto = salida_px
    es_video = medio.suffix.lower() in {".mp4", ".mov"}
    parte = ({"type": "input_video", "video_url": meta_api._data_url(medio)} if es_video
             else {"type": "input_image", "image_url": meta_api._data_url(medio)})
    cuerpo = {"model": "sam-3.1", "stream": True, "metadata": {"mask_encoding": "one_bit"},
              "input": [{"type": "message", "role": "user",
                         "content": [{"type": "input_text", "text": concepto}, parte]}]}
    r = cliente._sesion.post(f"{meta_api.URL_BASE}/responses", json=cuerpo, stream=True, timeout=600)
    if not r.ok:
        raise RuntimeError(f"SAM respondió {r.status_code}: {r.text[:300]}")
    eventos = [json.loads(l[6:]) for l in r.iter_lines() if l.startswith(b"data: {")]
    formato = sam.video_segmentation_format() if es_video else sam.image_segmentation_format()
    resultado = _leer(eventos, formato)

    salida: dict[int, np.ndarray] = {}
    for rec in resultado.records:
        if rec.kind != "mask":
            continue
        cuadro = rec.frame.frame_index if es_video and rec.frame is not None else 0
        b = rec.bounds
        raster = np.frombuffer(sam.decode_mask_to_raster(rec.mask), dtype=np.uint8)
        raster = raster.reshape(rec.mask.height, rec.mask.width)
        # El raster cubre la caja, a veces reducido: se lleva al tamaño de la caja y luego al cuadro pedido.
        caja = Image.fromarray(raster * 255).resize((b.right - b.left, b.bottom - b.top), Image.BILINEAR)
        lienzo = Image.new("L", fuente)
        lienzo.paste(caja, (b.left, b.top))
        final = np.asarray(lienzo.resize((ancho, alto), Image.BILINEAR)) > 127
        salida[cuadro] = salida.get(cuadro, np.zeros((alto, ancho), bool)) | final
    return {k: v.astype(np.uint8) for k, v in salida.items()}

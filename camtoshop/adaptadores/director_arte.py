"""Director de arte: Muse Wonder dirige los planos según el estilo y Muse Image los fotografía.

Las referencias son la foto y el recorte reales, para que el producto no cambie. Los planos se
guardan por estilo: volver a un estilo o cambiar el texto no gasta IA otra vez.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from camtoshop.adaptadores.meta_api import ClienteMeta
from camtoshop.dominio.estilos import Estilo
from camtoshop.dominio.marca import Marca
from camtoshop.dominio.producto import Analisis
from camtoshop.dominio.reel_fotos import Guion

MODELO = "muse-wonder-1.0"
ESPACIO = {"pie": "the lower third", "gigante": "the upper half", "portada": "the lower third",
           "historia": "the middle band", "polaroid": "the lower quarter", "palabra": "the center",
           "cinemascope": "the lower third"}


def _plan_de(respuesta: str) -> list[str]:
    limpio = respuesta[respuesta.find("{"):respuesta.rfind("}") + 1]
    planos = [str(p).strip() for p in json.loads(limpio)["planos"]]
    if not planos or not all(planos):
        raise ValueError("Muse Wonder no devolvió planos")
    return planos


class DirectorMuse:
    def __init__(self, cliente: ClienteMeta, carpeta: Path, estilo: Estilo, marca: Marca, comercio: str = ""):
        self._cliente = cliente
        self._carpeta = carpeta / estilo.id
        self._estilo = estilo
        self._marca = marca
        self._comercio = comercio

    def _dirigir(self, analisis: Analisis, guion: Guion, foto: Path) -> list[str]:
        ruta = self._carpeta / "plan.json"
        if ruta.exists():
            return json.loads(ruta.read_text())
        textos = [guion.gancho, *guion.beneficios]
        hechos = {k: getattr(analisis, k) for k in ("nombre", "marca", "categoria", "atributos")}
        pedido = (
            "You are the creative director of an award-winning campaign studio. Direct a vertical Instagram Reel "
            f"for this real product, shown in the reference photo. It has {len(textos)} shots. It must feel like a "
            "real campaign, never a slideshow or a template, and the shots must tell one idea from start to end.\n\n"
            f"ART DIRECTION: {self._estilo.arte}\n"
            f"BRAND: {self._comercio or analisis.marca or 'a small merchant'}. Brand colors "
            f"{self._marca.primario} and {self._marca.secundario}; use them as light, set or props when it fits.\n"
            f"PRODUCT FACTS (never invent others): {json.dumps(hechos, ensure_ascii=False)}\n"
            f"ON-SCREEN TEXT OF EACH SHOT, in order, for you to match the image to the idea: "
            f"{json.dumps(textos, ensure_ascii=False)}\n\n"
            "Return JSON only: {\"planos\": [\"prompt\", ...]}, one English prompt per shot for a photographic image "
            "model: subject, framing, lens, light, set, materials, palette. Every shot shows this exact product or a "
            "tight detail of it, unchanged in shape, color and label. Vary the framing strongly between shots; shot "
            f"1 must stop the scroll. Keep {ESPACIO[self._estilo.texto]} calm for on-screen text. Vertical 2:3. "
            "No text, no letters, no logos other than those on the product, no people's faces.")
        planos = _plan_de(self._cliente.preguntar(MODELO, [ClienteMeta.parte_texto(pedido), ClienteMeta.parte_imagen(foto)],
                                                  max_tokens=16000))[:len(textos)]
        self._carpeta.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(planos, ensure_ascii=False, indent=1))
        return planos

    def planos(self, analisis: Analisis, guion: Guion, foto: Path, recorte: Path | None) -> list[Path]:
        planos = self._dirigir(analisis, guion, foto)
        referencias = [foto] + ([recorte] if recorte else [])

        def fotografiar(n_prompt: tuple[int, str]) -> Path:
            n, prompt = n_prompt
            destino = self._carpeta / f"plano_{n}.png"
            if not destino.exists():
                self._cliente.editar_imagen(
                    f"{prompt} Keep the product exactly as in the reference: same shape, colors, materials and label. "
                    "Photorealistic, high-end campaign photography.", referencias, destino, "1024x1536")
            return destino

        with ThreadPoolExecutor(max_workers=3) as hilos:
            return list(hilos.map(fotografiar, enumerate(planos)))

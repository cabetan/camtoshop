"""Adaptadores del Reel desde fotos con Meta Model API: entender las fotos, escribir el guion,
pintar escenas de uso desde el recorte real y revisar el Reel terminado."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from camtoshop.adaptadores.meta_api import ClienteMeta
from camtoshop.adaptadores.producto_meta import ESQUEMA_ANALISIS, NOMBRES_IDIOMA
from camtoshop.dominio.producto import Analisis
from camtoshop.dominio.reel_fotos import Guion

MODELO = "muse-spark-1.3"

ESQUEMA_ANALISIS_FOTOS = json.loads(json.dumps(ESQUEMA_ANALISIS))
ESQUEMA_ANALISIS_FOTOS["properties"]["idioma"]["description"] = (
    "ISO 639-1 code of the merchant's text; 'es' if there is no text")
ESQUEMA_ANALISIS_FOTOS["properties"]["mejor_cuadro_s"]["description"] = (
    "0-based index of the photo where the whole product is most clearly visible")
ESQUEMA_ANALISIS_FOTOS["properties"]["precio_mencionado"]["description"] = (
    "Price exactly as the merchant wrote or said it; empty if none. Never estimate a price.")


class AnalizadorFotosSpark:
    def __init__(self, cliente: ClienteMeta):
        self._cliente = cliente

    def analizar(self, fotos: list[Path], texto: str) -> Analisis:
        partes = [ClienteMeta.parte_texto(
            "A small merchant sent these photos of ONE product to sell, plus this message: "
            f"\"{texto or '(no message)'}\". Identify the product and read any brand or label text exactly as "
            "printed. 'nombre', 'categoria', 'atributos' and 'gancho' in the merchant's language; "
            "'conceptos_sam' in English (short nouns a segmentation model can find, e.g. 'star shaped candle').")]
        partes += [ClienteMeta.parte_imagen(f) for f in fotos[:6]]
        d = json.loads(self._cliente.preguntar(MODELO, partes, esquema=ESQUEMA_ANALISIS_FOTOS))
        mejor = int(d["mejor_cuadro_s"]) if 0 <= int(d["mejor_cuadro_s"]) < len(fotos) else 0
        return Analisis(d["nombre"], d["marca"], d["categoria"], d["atributos"], d["texto_etiqueta"],
                        d["precio_mencionado"], d["conceptos_sam"], (d["idioma"] or "es")[:2].lower(),
                        float(mejor), d["gancho"])


ESQUEMA_GUION = {
    "type": "object",
    "properties": {
        "gancho": {"type": "string", "description": "max 6 words; a question or bold promise that stops the scroll"},
        "beneficios": {"type": "array", "items": {"type": "string"},
                       "description": "exactly 3 benefits, 2-4 words each, concrete"},
        "llamado": {"type": "string", "description": "call to action, max 4 words"},
        "escenas": {"type": "array", "items": {"type": "string"},
                    "description": "2 short English descriptions of a realistic place where this product is used"},
    },
    "required": ["gancho", "beneficios", "llamado", "escenas"],
    "additionalProperties": False,
}

REGLAS_GUION = (
    "Rules: on-screen text in {idioma}; only facts from the merchant's message and the photos; never invent "
    "free shipping, warranties, discounts, certifications or 'organic'; do not write the price (it is added "
    "separately from the merchant's own number); numbers in digits; no emojis, no hashtags.")


class GuionistaSpark:
    """Escribe el guion de un Reel de producto de 8 a 15 s hecho solo con fotos."""

    def __init__(self, cliente: ClienteMeta):
        self._cliente = cliente

    def guion(self, analisis: Analisis, texto: str, foto: Path, pedido: str = "",
              anterior: Guion | None = None, problemas: list[str] | None = None) -> Guion:
        idioma = NOMBRES_IDIOMA.get(analisis.idioma, analisis.idioma)
        tarea = "Write the script of a product Reel made only from photos: hook, 3 benefits, call to action."
        if anterior:
            tarea = (f"Rewrite this Reel script: {json.dumps(asdict(anterior), ensure_ascii=False)}. "
                     + (f"The merchant asks: \"{pedido}\". " if pedido else "")
                     + (f"A reviewer found: {'; '.join(problemas)}. " if problemas else "")
                     + "Keep what was not asked to change.")
        hechos = {k: getattr(analisis, k) for k in ("nombre", "marca", "categoria", "atributos", "texto_etiqueta")}
        d = json.loads(self._cliente.preguntar(MODELO, [
            ClienteMeta.parte_texto(f"{tarea} {REGLAS_GUION.format(idioma=idioma)}\n\n"
                                    f"Product: {json.dumps(hechos, ensure_ascii=False)}\n"
                                    f"Merchant's message: {texto or '(none)'}"),
            ClienteMeta.parte_imagen(foto)], esquema=ESQUEMA_GUION))
        return Guion(d["gancho"], d["beneficios"], d["llamado"], d["escenas"])


class EscenografoMuse:
    """Escena de uso con Muse Image editada desde el recorte real, para que sea el mismo producto."""

    def __init__(self, cliente: ClienteMeta, carpeta: Path):
        self._cliente = cliente
        self._carpeta = carpeta

    def escena(self, descripcion: str, recorte: Path) -> Path:
        prompt = (f"Vertical lifestyle photo: {descripcion}. Feature exactly this product, identical shape, "
                  "colors, logo and label, at a natural size in the scene. Natural light, realistic, warm, "
                  "shallow depth of field, empty space in the lower third. No text, no people's faces.")
        huella = hashlib.sha1((prompt + recorte.name).encode()).hexdigest()[:8]
        destino = self._carpeta / f"escena_{huella}.png"
        if not destino.exists():
            self._carpeta.mkdir(parents=True, exist_ok=True)
            self._cliente.editar_imagen(prompt, [recorte], destino, "1024x1536")
        return destino


ESQUEMA_REVISION_FOTOS = {
    "type": "object",
    "properties": {
        "aprobado": {"type": "boolean"},
        "problemas": {"type": "array", "items": {"type": "string"}},
        "comentario": {"type": "string"},
    },
    "required": ["aprobado", "problemas", "comentario"],
    "additionalProperties": False,
}


class RevisorFotosSpark:
    """Mira el Reel terminado como un editor exigente y dice qué corregir del guion."""

    def __init__(self, cliente: ClienteMeta):
        self._cliente = cliente

    def revisar(self, reel: Path, guion: Guion, precio: str) -> tuple[bool, list[str], str]:
        d = json.loads(self._cliente.preguntar(MODELO, [
            ClienteMeta.parte_texto(
                "You are a strict Instagram Reels editor. Watch this product Reel made from photos. Check: is the "
                "hook readable in the first second and does it stop the scroll? Is every on-screen word spelled "
                "right and readable? Do the AI scenes show the same product truthfully? Is the price "
                f"({precio or 'none'}) visible and correct? Is the call to action clear? Report a problem only if "
                "you are certain and it is about the text (the script can be rewritten; photos cannot). Approve if "
                f"nothing hurts the sale. 'problemas' and 'comentario' in Spanish, short.\n\nScript: "
                f"{json.dumps(asdict(guion), ensure_ascii=False)}"),
            ClienteMeta.parte_video(reel)], esquema=ESQUEMA_REVISION_FOTOS, max_tokens=24000))
        return d["aprobado"], d["problemas"], d["comentario"]

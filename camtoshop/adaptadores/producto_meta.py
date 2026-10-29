"""Adaptadores del producto con Meta Model API: análisis del video, fotos de catálogo, ficha y anuncios."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from camtoshop.adaptadores.meta_api import ClienteMeta
from camtoshop.dominio.anuncios import FORMATOS, Anuncio
from camtoshop.dominio.producto import Analisis, Ficha, Texto, precio_valido

RESPALDO_SAM = "object held in hands"
NOMBRES_IDIOMA = {"es": "Spanish", "en": "English", "pt": "Portuguese", "fr": "French"}


def copia_liviana(video: Path, destino: Path) -> Path:
    """720 px a 30 cuadros/s con audio: cabe holgado en el límite de 50 MB de Muse Spark."""
    if not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-hwaccel", "videotoolbox", "-i", str(video),
                        "-map", "0:v:0", "-map", "0:a:0?", "-vf", "scale=720:-2,fps=30", "-c:v", "libx264",
                        "-preset", "veryfast", "-crf", "28", "-c:a", "aac", "-b:a", "96k", "-ac", "1",
                        str(destino)], check=True)
    return destino


ESQUEMA_ANALISIS = {
    "type": "object",
    "properties": {
        "nombre": {"type": "string"},
        "marca": {"type": "string"},
        "categoria": {"type": "string"},
        "atributos": {"type": "array", "items": {"type": "string"}},
        "texto_etiqueta": {"type": "string", "description": "Text printed on the label or packaging, empty if none"},
        "precio_mencionado": {"type": "string"},
        "conceptos_sam": {"type": "array", "items": {"type": "string"},
                          "description": "3 short English noun phrases for the product, from specific to generic"},
        "idioma": {"type": "string", "description": "ISO 639-1 code of the spoken language"},
        "mejor_cuadro_s": {"type": "number", "description": "Second where the whole product is most clearly visible"},
        "gancho": {"type": "string", "description": "Short Instagram hook in the spoken language"},
    },
    "required": ["nombre", "marca", "categoria", "atributos", "texto_etiqueta", "precio_mencionado",
                 "conceptos_sam", "idioma", "mejor_cuadro_s", "gancho"],
    "additionalProperties": False,
}


class AnalizadorSpark:
    def __init__(self, cliente: ClienteMeta, trabajo: Path):
        self._cliente = cliente
        self._trabajo = trabajo

    def analizar(self, video: Path) -> Analisis:
        liviano = copia_liviana(video, self._trabajo / "liviano.mp4")
        d = json.loads(self._cliente.preguntar("muse-spark-1.3", [
            ClienteMeta.parte_texto(
                "A merchant filmed this vertical video selling one product. Watch and listen. Identify the "
                "product and read any brand or label text exactly as printed. 'nombre', 'categoria' and "
                "'atributos' in the spoken language; 'conceptos_sam' in English."),
            ClienteMeta.parte_video(liviano)], esquema=ESQUEMA_ANALISIS))
        return Analisis(d["nombre"], d["marca"], d["categoria"], d["atributos"], d["texto_etiqueta"],
                        d["precio_mencionado"], d["conceptos_sam"], d["idioma"][:2].lower(),
                        float(d["mejor_cuadro_s"]), d["gancho"])


ESTUDIO = ("Professional e-commerce studio product photo of exactly this product, centered on a seamless soft "
           "white background, soft diffused studio lighting, subtle natural shadow. Keep the product identical: "
           "same shape, colors, logo, label text and proportions. Remove hands and any background.")
AMBIENTE = ("Premium editorial product photo of exactly this product on a surface and backdrop whose colors "
            "complement it, soft directional light, elegant minimal props. Keep the product identical: same "
            "shape, colors, logo, label text and proportions. No hands, no text.")


class FotografoMuse:
    """Mejor cuadro del video original -> recorte con SAM 3.1 -> foto de estudio con Muse Image."""

    def __init__(self, cliente: ClienteMeta, trabajo: Path):
        self._cliente = cliente
        self._trabajo = trabajo

    def fotos(self, video: Path, analisis: Analisis) -> list[Path]:
        self._trabajo.mkdir(parents=True, exist_ok=True)
        cuadro = self._trabajo / "cuadro.jpg"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{analisis.mejor_cuadro_s:.2f}",
                        "-i", str(video), "-frames:v", "1", "-vf", "scale=1080:-2", "-q:v", "2", str(cuadro)],
                       check=True)
        recorte = self._recortar(cuadro, analisis.conceptos_sam + [RESPALDO_SAM])
        fotos = []
        for nombre, prompt, tamano in (("catalogo.png", ESTUDIO, "1024x1024"), ("ambiente.png", AMBIENTE, "1024x1024")):
            destino = self._trabajo / nombre
            if not destino.exists():
                self._cliente.editar_imagen(prompt, [recorte], destino, tamano)
            fotos.append(destino)
        return fotos

    def _recortar(self, cuadro: Path, conceptos: list[str]) -> Path:
        for concepto in conceptos:
            cajas = [c for lista in self._cliente.segmentar(concepto, cuadro).values() for c in lista]
            if cajas:
                c = max(cajas, key=lambda c: (c.x2 - c.x1) * (c.y2 - c.y1))
                mx, my = int((c.x2 - c.x1) * 0.08), int((c.y2 - c.y1) * 0.08)
                ancho, alto = c.ancho, c.alto
                x1, y1 = max(0, c.x1 - mx), max(0, c.y1 - my)
                x2, y2 = min(ancho, c.x2 + mx), min(alto, c.y2 + my)
                destino = self._trabajo / "recorte.jpg"
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(cuadro), "-vf",
                                f"crop={x2 - x1}:{y2 - y1}:{x1}:{y1}", str(destino)], check=True)
                return destino
        return cuadro


def _esquema_texto() -> dict:
    return {
        "type": "object",
        "properties": {
            "titulo": {"type": "string", "description": "max 70 characters"},
            "descripcion": {"type": "string", "description": "2 short persuasive paragraphs, only true claims"},
            "puntos": {"type": "array", "items": {"type": "string"}, "description": "3-5 benefit bullets"},
            "seo_titulo": {"type": "string"},
            "seo_descripcion": {"type": "string", "description": "max 160 characters"},
        },
        "required": ["titulo", "descripcion", "puntos", "seo_titulo", "seo_descripcion"],
        "additionalProperties": False,
    }


class RedactorSpark:
    """Ficha de venta multilingüe: el idioma del video más los pedidos (inglés primero)."""

    def __init__(self, cliente: ClienteMeta):
        self._cliente = cliente

    def ficha(self, analisis: Analisis, transcripcion: str, idiomas: list[str]) -> Ficha:
        todos = [analisis.idioma] + [i for i in idiomas if i != analisis.idioma]
        esquema = {
            "type": "object",
            "properties": {
                "textos": {"type": "object", "properties": {i: _esquema_texto() for i in todos},
                           "required": todos, "additionalProperties": False},
                "precio": {"type": "number", "description": "Price in digits; 0 if none was said"},
                "moneda": {"type": "string", "description": "ISO 4217 code, e.g. COP or USD"},
                "etiquetas": {"type": "array", "items": {"type": "string"}, "description": "5-10 search tags"},
            },
            "required": ["textos", "precio", "moneda", "etiquetas"],
            "additionalProperties": False,
        }
        hechos = {k: getattr(analisis, k) for k in ("nombre", "marca", "categoria", "atributos",
                                                     "texto_etiqueta", "precio_mencionado")}
        d = json.loads(self._cliente.preguntar("muse-spark-1.3", [ClienteMeta.parte_texto(
            "Write the online store listing for this product, in each requested language "
            f"({', '.join(NOMBRES_IDIOMA.get(i, i) for i in todos)}). Use only facts from the merchant's "
            "words and the product data; never invent certifications, ingredients or numbers. Warm, clear, "
            "persuasive, for a small independent shop.\n\n"
            f"Product data: {json.dumps(hechos, ensure_ascii=False)}\n\nMerchant's words: {transcripcion}")],
            esquema=esquema))
        textos = {i: Texto(**d["textos"][i]) for i in todos}
        return Ficha(analisis.idioma, textos, precio_valido(d["precio"], d["moneda"]), analisis.marca,
                     analisis.categoria, d["etiquetas"])


ESQUEMA_ANUNCIOS = {
    "type": "object",
    "properties": {"anuncios": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "angulo": {"type": "string", "enum": ["beneficio", "historia", "oferta"]},
            "titular": {"type": "string", "description": "max 40 characters"},
            "texto": {"type": "string", "description": "primary text, max 125 characters"},
            "llamado": {"type": "string", "description": "call to action button, max 20 characters"},
            "concepto_visual": {"type": "string", "description": "English art direction for the ad image"},
        },
        "required": ["angulo", "titular", "texto", "llamado", "concepto_visual"],
        "additionalProperties": False,
    }}},
    "required": ["anuncios"],
    "additionalProperties": False,
}


class PublicistaMuse:
    """Muse Spark escribe tres ángulos; Muse Image diseña cada pieza con el producto real y el titular."""

    def __init__(self, cliente: ClienteMeta, trabajo: Path):
        self._cliente = cliente
        self._trabajo = trabajo

    def anuncios(self, ficha: Ficha, foto: Path) -> list[Anuncio]:
        t = ficha.principal
        d = json.loads(self._cliente.preguntar("muse-spark-1.3", [ClienteMeta.parte_texto(
            "Write three Meta ads (Instagram/Facebook) for this product, one per angle: 'beneficio' (main "
            "benefit), 'historia' (origin or who makes it), 'oferta' (price and urgency without lying). Language: "
            f"{NOMBRES_IDIOMA.get(ficha.idioma, ficha.idioma)}. Only true claims from the listing.\n\n"
            f"Listing: {t.titulo}. {t.descripcion} Points: {'; '.join(t.puntos)}. "
            f"Price: {ficha.precio.texto() if ficha.precio else 'not stated'}."),
            ClienteMeta.parte_imagen(foto)], esquema=ESQUEMA_ANUNCIOS))
        return [Anuncio(**a) for a in d["anuncios"]]

    def creativo(self, anuncio: Anuncio, foto: Path, formato: str) -> Path:
        prompt = (f"Social media ad creative, {'square' if formato == 'feed' else 'vertical story'} format. "
                  f"{anuncio.concepto_visual}. Feature exactly this product, keep it identical (shape, colors, "
                  f"logo, label). Render this headline in large bold clean type, exact spelling: "
                  f"\"{anuncio.titular}\". Add a small rounded button with the text \"{anuncio.llamado}\". "
                  "Modern, premium, high contrast, plenty of breathing room.")
        huella = hashlib.sha1(prompt.encode()).hexdigest()[:8]
        destino = self._trabajo / f"anuncio_{anuncio.angulo}_{formato}_{huella}.png"
        if not destino.exists():
            self._trabajo.mkdir(parents=True, exist_ok=True)
            self._cliente.editar_imagen(prompt, [foto], destino, FORMATOS[formato])
        return destino

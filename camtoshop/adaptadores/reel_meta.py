"""Adaptadores del Reel que usan Meta Model API: transcripción, elección de tomas y rastreo del producto."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from camtoshop.adaptadores.alineador_xlsr import escribir_wav, leer_audio
from camtoshop.adaptadores.meta_api import ClienteMeta
from camtoshop.dominio.direccion import Propuesta
from camtoshop.dominio.reel import Caja, Palabra

IDIOMAS = {"es": "Spanish", "en": "English", "pt": "Portuguese", "fr": "French"}


class TranscriptorMeta:
    """Muse Voice Transcribe en modo ENDPOINTING."""

    def __init__(self, cliente: ClienteMeta, palabras_clave: list[str] | None = None):
        self._cliente = cliente
        self._clave = palabras_clave

    def transcribir(self, video: Path, idioma: str) -> list[tuple[float, float, str]]:
        with tempfile.TemporaryDirectory() as tmp:
            wav = escribir_wav(leer_audio(video), Path(tmp) / "audio.wav")
            respuesta = self._cliente.transcribir(wav, [IDIOMAS.get(idioma[:2], "English")], self._clave)
        return [(t["startMs"] / 1000, t["endMs"] / 1000, t["transcript"]) for t in respuesta["turns"]]


ESQUEMA_TOMAS = {
    "type": "object",
    "properties": {
        "conservar": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"desde": {"type": "integer"}, "hasta": {"type": "integer"}},
                "required": ["desde", "hasta"],
                "additionalProperties": False,
            },
        },
        "explicacion": {"type": "string"},
    },
    "required": ["conservar", "explicacion"],
    "additionalProperties": False,
}

INSTRUCCION_TOMAS = """You edit short product videos for social media. Below is the word-by-word transcript of a \
merchant talking to the camera, each word with its index and start time in seconds.

Choose the word ranges to KEEP so that the result is one clean, fluent sales message:
- When a sentence is started and then restarted, keep only the LAST complete attempt; drop the failed attempt entirely.
- Drop self-corrections and meta comments ("sorry", "I made a mistake", "perdón", "me equivoqué", "otra vez").
- Drop stutters and immediately repeated words ("coffee coffee", "por por").
- Drop fillers ("eh", "um") and any cut-off word fragment.
- Never change the order and never drop information about the product, its price or how to buy it.

Return inclusive index ranges, in order. 'explicacion' in Spanish, one sentence."""


class EditorSpark:
    """Muse Spark lee la transcripción alineada y decide qué palabras se quedan."""

    def __init__(self, cliente: ClienteMeta, modelo: str = "muse-spark-1.3"):
        self._cliente = cliente
        self._modelo = modelo
        self.explicacion = ""

    def elegir(self, palabras: list[Palabra], idioma: str) -> list[tuple[int, int]]:
        listado = "\n".join(f"{i} [{p.inicio:.2f}] {p.texto}" for i, p in enumerate(palabras))
        datos = json.loads(self._cliente.preguntar(
            self._modelo, [ClienteMeta.parte_texto(f"{INSTRUCCION_TOMAS}\n\nLanguage: {idioma}\n\n{listado}")],
            esquema=ESQUEMA_TOMAS))
        self.explicacion = datos["explicacion"]
        return [(r["desde"], r["hasta"]) for r in datos["conservar"]]


class RastreadorSAM:
    """SAM 3.1 sigue el producto sobre una copia liviana del video (480 px, pocos cuadros por segundo)."""

    def __init__(self, cliente: ClienteMeta, conceptos: list[str], ancho_reel: int = 1080,
                 fps: int = 6, ancho_proxy: int = 480):
        self._cliente = cliente
        self._conceptos = conceptos
        self._escala = ancho_reel / ancho_proxy
        self._fps = fps
        self._ancho = ancho_proxy
        self.concepto = None

    def cajas(self, video: Path) -> dict[float, Caja]:
        with tempfile.TemporaryDirectory() as tmp:
            proxy = Path(tmp) / "sam.mp4"
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-an", "-vf",
                            f"scale={self._ancho}:-2,fps={self._fps}", "-c:v", "libx264", "-preset", "veryfast",
                            "-crf", "30", str(proxy)], check=True)
            for concepto in self._conceptos:
                cuadros = self._cliente.segmentar(concepto, proxy)
                if any(cuadros.values()):
                    self.concepto = concepto
                    break
            else:
                return {}
        e = self._escala
        salida = {}
        for n, cajas in cuadros.items():
            if cajas:
                c = max(cajas, key=lambda c: (c.x2 - c.x1) * (c.y2 - c.y1))
                salida[n / self._fps] = Caja(c.x1 * e, c.y1 * e, c.x2 * e, c.y2 * e)
        return salida


ESQUEMA_DIRECCION = {
    "type": "object",
    "properties": {
        "texto_portada": {"type": "string", "description": "2-4 word hook shown over the opening product shot"},
        "textos_detras": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "lineas": {"type": "array", "items": {"type": "string"}, "description": "1-3 lines, max 12 characters each"},
                    "desde": {"type": "integer"},
                    "hasta": {"type": "integer"},
                },
                "required": ["lineas", "desde", "hasta"],
                "additionalProperties": False,
            },
        },
        "escenas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "palabra": {"type": "integer"},
                    "escena": {"type": "string", "description": "English scene description of the product in use"},
                },
                "required": ["palabra", "escena"],
                "additionalProperties": False,
            },
        },
        "enfasis": {"type": "array", "items": {"type": "integer"}},
        "cierre_titulo": {"type": "string"},
        "cierre_precio": {"type": "string"},
        "cierre_llamado": {"type": "string"},
    },
    "required": ["texto_portada", "textos_detras", "escenas", "enfasis", "cierre_titulo", "cierre_precio",
                 "cierre_llamado"],
    "additionalProperties": False,
}

INSTRUCCION_DIRECCION = """You are the creative director of a short vertical product video for Instagram Reels. \
The merchant's speech is already edited; below is every word with its index and time in seconds. Plan the on-screen \
graphics for the look "{look}" ({descripcion}).

- texto_portada: a 2-4 word hook in the video's language, shown over a studio shot of the product during the first second.
- textos_detras: up to {usos} moments for giant words placed BEHIND the speaker. Pick the strongest claims (origin, \
who makes it, the key benefit, the price). Lines are short (max 12 characters each, 1-3 lines), numbers in digits, and paraphrase what is \
said at that moment, in the video's language. 'desde'/'hasta' are the word indices where it is said.
- escenas: up to {escenas} cutaways that show THIS product in use (e.g. lit at night, served in a cup). Never \
illustrate claims you cannot show truthfully (no rivers, mothers, factories). 'palabra' is where it starts; avoid \
the first 1.5 seconds and the textos_detras moments.
- enfasis: indices of 3-8 words to color: price, numbers, origin, the main benefit.
- cierre: product title (max 3 words), price in digits with its currency symbol as customers in that market write it (e.g. "$85.000", "US$50"), never in words, and a call to action \
(max 3 words), all in the video's language.

Product: {producto}
Language: {idioma}"""

DESCRIPCIONES_LOOK = {
    "directo": "organic Reel, energetic but personal; one bold moment",
    "anuncio": "paid ad, fast and sales-driven; emphasize the offer and the price",
    "premium": "elegant and calm, for a high-end product; no giant text",
}


class DirectorSpark:
    """Muse Spark planea los gráficos del Reel sobre la transcripción ya editada."""

    def __init__(self, cliente: ClienteMeta, modelo: str = "muse-spark-1.3"):
        self._cliente = cliente
        self._modelo = modelo

    def proponer(self, palabras: list[Palabra], producto: dict, look, idioma: str) -> Propuesta:
        listado = "\n".join(f"{i} [{p.inicio:.2f}] {p.texto}" for i, p in enumerate(palabras))
        instruccion = INSTRUCCION_DIRECCION.format(
            look=look.nombre, descripcion=DESCRIPCIONES_LOOK.get(look.nombre, ""), usos=look.usos_texto_detras,
            escenas=look.escenas, idioma=idioma,
            producto=json.dumps({k: producto.get(k) for k in ("nombre", "marca", "atributos", "precio_mencionado")},
                                ensure_ascii=False))
        d = json.loads(self._cliente.preguntar(
            self._modelo, [ClienteMeta.parte_texto(f"{instruccion}\n\n{listado}")], esquema=ESQUEMA_DIRECCION))
        return Propuesta(
            texto_portada=d["texto_portada"],
            textos_detras=[(t["lineas"], t["desde"], t["hasta"]) for t in d["textos_detras"]],
            escenas=[(e["escena"], e["palabra"]) for e in d["escenas"]],
            enfasis=d["enfasis"],
            cierre=(d["cierre_titulo"], d["cierre_precio"], d["cierre_llamado"]),
        )


class IlustradorMuse:
    """Muse Image genera portada, escenas y cierre a partir de la foto de catálogo del producto."""

    def __init__(self, cliente: ClienteMeta, foto_producto: Path, carpeta: Path, estilo: str = ""):
        self._cliente = cliente
        self._foto = foto_producto
        self._carpeta = carpeta
        self._estilo = estilo
        carpeta.mkdir(parents=True, exist_ok=True)

    def _generar(self, nombre: str, prompt: str) -> Path:
        destino = self._carpeta / nombre
        if not destino.exists():
            self._cliente.editar_imagen(prompt, [self._foto], destino, "1024x1536")
        return destino

    def portada(self, texto: str) -> Path:
        return self._generar("portada.png", (
            "Vertical hero product photo: this exact product centered, dramatic premium studio lighting, rich "
            f"gradient background that suits the product, subtle reflection, empty space at the top. {self._estilo} "
            "Keep the product identical: shape, colors, logo and label text. No text."))

    def escena(self, prompt: str) -> Path:
        nombre = "escena_" + "".join(c for c in prompt.lower() if c.isalnum())[:40] + ".png"
        return self._generar(nombre, (
            f"Vertical lifestyle photo: {prompt}. Use this exact product, keep it identical: shape, colors, "
            f"logo and label text. Natural, realistic, warm light, shallow depth of field. {self._estilo} No text."))

    def cierre(self, titulo: str, precio: str, llamado: str) -> Path:
        return self._generar("cierre.png", (
            "Vertical Instagram end card. This exact product centered on a clean background whose color suits "
            f"the product, soft shadow. At the top, large elegant bold text: \"{titulo}\". Below the product, very "
            f"large text: \"{precio}\". At the bottom a rounded yellow button with dark text: \"{llamado}\". "
            f"Clean premium e-commerce design, exact spelling. {self._estilo}"))

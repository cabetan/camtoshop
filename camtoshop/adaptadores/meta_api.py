"""Adaptador HTTP para Meta Model API (Muse Spark, SAM 3.1, Muse Image).

Solo transporte: arma las solicitudes y devuelve datos crudos. Las reglas de
negocio viven en camtoshop/dominio.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import requests

URL_BASE = "https://api.meta.ai/v1"


def _clave_api() -> str:
    clave = os.environ.get("MODEL_API_KEY")
    if clave:
        return clave
    # Respaldo: llavero de macOS (servicio MODEL_API_KEY). Nunca se imprime.
    salida = subprocess.run(
        ["security", "find-generic-password", "-a", os.environ.get("USER", ""), "-s", "MODEL_API_KEY", "-w"],
        capture_output=True, text=True,
    )
    if salida.returncode != 0 or not salida.stdout.strip():
        raise RuntimeError("No encuentro MODEL_API_KEY ni en el entorno ni en el llavero.")
    return salida.stdout.strip()


def _data_url(ruta: Path) -> str:
    tipo = mimetypes.guess_type(ruta.name)[0] or "application/octet-stream"
    return f"data:{tipo};base64," + base64.b64encode(ruta.read_bytes()).decode()


@dataclass
class Caja:
    objeto: int
    x1: int
    y1: int
    x2: int
    y2: int
    ancho: int
    alto: int


_RE_CAJA = re.compile(r"(\d+)<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=(\d+);h=(\d+)")
_RE_CUADRO = re.compile(r"<(\d+)f>")


class ClienteMeta:
    def __init__(self, tiempo_limite: int = 600):
        self._sesion = requests.Session()
        self._sesion.headers["Authorization"] = f"Bearer {_clave_api()}"
        self._tiempo = tiempo_limite

    # --- Muse Spark -------------------------------------------------------

    def preguntar(self, modelo: str, partes: list[dict], esquema: dict | None = None,
                  max_tokens: int = 8000) -> str:
        cuerpo: dict = {
            "model": modelo,
            "input": [{"type": "message", "role": "user", "content": partes}],
            "max_output_tokens": max_tokens,
        }
        if esquema:
            cuerpo["text"] = {"format": {"type": "json_schema", "name": "salida", "schema": esquema, "strict": True}}
        r = self._sesion.post(f"{URL_BASE}/responses", json=cuerpo, timeout=self._tiempo)
        if not r.ok:
            raise RuntimeError(f"Muse {modelo} respondió {r.status_code}: {r.text[:500]}")
        datos = r.json()
        textos = [
            c.get("text", "")
            for item in datos.get("output", []) if item.get("type") == "message"
            for c in item.get("content", []) if c.get("type") == "output_text"
        ]
        if not "".join(textos).strip():
            # Pasa cuando el razonamiento agota max_output_tokens antes de responder.
            raise RuntimeError(f"Muse {modelo} no devolvió texto (estado {datos.get('status')}, "
                               f"{datos.get('incomplete_details')}, uso {datos.get('usage')})")
        return "".join(textos)

    @staticmethod
    def parte_texto(texto: str) -> dict:
        return {"type": "input_text", "text": texto}

    @staticmethod
    def parte_imagen(ruta: Path) -> dict:
        return {"type": "input_image", "image_url": _data_url(ruta)}

    @staticmethod
    def parte_video(ruta: Path) -> dict:
        return {"type": "input_file", "filename": ruta.name, "file_data": _data_url(ruta)}

    # --- SAM 3.1 ----------------------------------------------------------

    def segmentar(self, concepto: str, ruta: Path) -> dict[int, list[Caja]]:
        """Devuelve {cuadro: [cajas]} para el concepto (frase corta en inglés)."""
        es_video = ruta.suffix.lower() in {".mp4", ".mov"}
        media = ({"type": "input_video", "video_url": _data_url(ruta)} if es_video
                 else {"type": "input_image", "image_url": _data_url(ruta)})
        cuerpo = {
            "model": "sam-3.1",
            "input": [{"type": "message", "role": "user",
                       "content": [{"type": "input_text", "text": concepto}, media]}],
            "metadata": {"mask_encoding": "one_bit"},
            "stream": True,
        }
        r = self._sesion.post(f"{URL_BASE}/responses", json=cuerpo, stream=True, timeout=self._tiempo,
                              headers={"Accept": "text/event-stream"})
        if not r.ok:
            raise RuntimeError(f"SAM respondió {r.status_code}: {r.text[:500]}")
        texto = []
        for linea in r.iter_lines(decode_unicode=False):
            if not linea or not linea.startswith(b"data: "):
                continue
            dato = linea[6:].decode("utf-8", "replace")
            if dato == "[DONE]":
                break
            evento = json.loads(dato)
            if evento.get("type") == "response.output_text.delta":
                texto.append(evento.get("delta", ""))
        return self._leer_cajas("".join(texto))

    @staticmethod
    def _leer_cajas(salida: str) -> dict[int, list[Caja]]:
        cuadros: dict[int, list[Caja]] = {}
        for linea in re.split(r"(?=<\d+f>)", salida):
            m = _RE_CUADRO.match(linea)
            if not m:
                continue
            n = int(m.group(1))
            cuadros[n] = [Caja(*map(int, g)) for g in _RE_CAJA.findall(linea)]
        return cuadros

    # --- Muse Voice Transcribe --------------------------------------------

    def transcribir(self, wav: Path, idiomas: list[str] | None = None,
                    palabras_clave: list[str] | None = None) -> dict:
        """Devuelve {'transcript', 'turns': [{startMs, endMs, transcript}]}.

        El WAV debe ser mono, PCM de 16 bits a 16 o 24 kHz.
        """
        ajustes: dict = {"mode": "ENDPOINTING", "model": "muse-voice-transcribe-1.0", "audioEncoding": "WAV"}
        if idiomas:
            ajustes["languageBias"] = idiomas
        if palabras_clave:
            ajustes["keywords"] = palabras_clave
        with wav.open("rb") as audio:
            r = self._sesion.post(f"{URL_BASE}/asr/transcribe", timeout=self._tiempo, files={
                "request": (None, json.dumps(ajustes), "application/json"),
                "audio": (wav.name, audio, "audio/wav"),
            })
        if not r.ok:
            raise RuntimeError(f"Voice Transcribe respondió {r.status_code}: {r.text[:500]}")
        return r.json()

    # --- Muse Image -------------------------------------------------------

    def generar_imagen(self, prompt: str, destino: Path, tamano: str = "1024x1024") -> Path:
        r = self._sesion.post(f"{URL_BASE}/images/generations", timeout=self._tiempo, json={
            "model": "muse-image-1.0", "prompt": prompt, "n": 1, "size": tamano, "output_format": "png",
        })
        if not r.ok:
            raise RuntimeError(f"Muse Image respondió {r.status_code}: {r.text[:500]}")
        destino.write_bytes(base64.b64decode(r.json()["data"][0]["b64_json"]))
        return destino

    def editar_imagen(self, prompt: str, referencias: list[Path], destino: Path, tamano: str = "1024x1024") -> Path:
        r = self._sesion.post(f"{URL_BASE}/images/edits", timeout=self._tiempo, json={
            "model": "muse-image-1.0", "prompt": prompt, "size": tamano, "output_format": "png",
            "images": [{"image_url": _data_url(p)} for p in referencias],
        })
        if not r.ok:
            raise RuntimeError(f"Muse Image (edición) respondió {r.status_code}: {r.text[:500]}")
        destino.write_bytes(base64.b64decode(r.json()["data"][0]["b64_json"]))
        return destino

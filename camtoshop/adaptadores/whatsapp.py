"""WhatsApp Cloud API: la línea única de Camtoshop.

Recibe por webhook lo que mandan los comercios (fotos, notas de voz, video, texto, botones) y
responde con texto o con el Reel y tres botones. Meta firma cada webhook con el secreto de la app
(X-Hub-Signature-256): sin firma válida no se procesa nada.
"""

from __future__ import annotations

import hashlib
import hmac
import subprocess
import tempfile
from pathlib import Path

import requests

from camtoshop.dominio.conversacion import Mensaje

GRAPH = "https://graph.facebook.com/v23.0"
MAX_VIDEO = 15 * 1024 * 1024  # WhatsApp acepta 16 MB
EXTENSIONES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "video/mp4": ".mp4",
               "audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/mp4": ".m4a", "audio/aac": ".aac"}


def firma_valida(cuerpo: bytes, firma: str, secreto_app: str) -> bool:
    if not firma or not secreto_app:
        return False
    esperada = "sha256=" + hmac.new(secreto_app.encode(), cuerpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, firma)


def mensajes_del_webhook(cuerpo: dict) -> list[tuple[str, str, str, Mensaje]]:
    """(celular, id del mensaje, nombre del perfil, Mensaje) por cada mensaje entrante del webhook."""
    salida = []
    for entrada in cuerpo.get("entry", []):
        for cambio in entrada.get("changes", []):
            valor = cambio.get("value", {})
            nombres = {c.get("wa_id"): c.get("profile", {}).get("name", "") for c in valor.get("contacts", [])}
            for m in valor.get("messages", []):
                tipo, celular = m.get("type"), m.get("from", "")
                if tipo == "text":
                    msg = Mensaje("texto", m["text"].get("body", ""))
                elif tipo == "image":
                    msg = Mensaje("imagen", m["image"].get("caption", ""), m["image"]["id"])
                elif tipo == "audio":
                    msg = Mensaje("audio", media=m["audio"]["id"])
                elif tipo == "video":
                    msg = Mensaje("video", m["video"].get("caption", ""), m["video"]["id"])
                elif tipo == "interactive" and m["interactive"].get("type") == "button_reply":
                    msg = Mensaje("boton", boton=m["interactive"]["button_reply"]["id"])
                elif tipo == "button":  # respuesta a botón de plantilla
                    msg = Mensaje("boton", boton=m["button"].get("payload", ""))
                else:
                    msg = Mensaje("texto", "")
                salida.append((celular, m.get("id", ""), nombres.get(celular, ""), msg))
    return salida


def video_para_whatsapp(video: Path) -> Path:
    """Copia de 720 px que pesa menos de 15 MB, para mandarla como vista previa."""
    destino = video.with_name(video.stem + "_wa.mp4")
    if destino.exists() and destino.stat().st_mtime >= video.stat().st_mtime:
        return destino
    for crf in (26, 30, 34):
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-vf", "scale=720:-2",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-c:a", "aac", "-b:a", "96k",
                        "-movflags", "+faststart", str(destino)], check=True)
        if destino.stat().st_size <= MAX_VIDEO:
            break
    return destino


class ClienteWhatsApp:
    def __init__(self, telefono_id: str, token: str):
        self._telefono = telefono_id
        self._sesion = requests.Session()
        self._sesion.headers["Authorization"] = f"Bearer {token}"

    def _revisar(self, r: requests.Response, que: str) -> dict:
        if not r.ok:
            try:
                detalle = r.json()["error"]["message"]
            except (ValueError, KeyError):
                detalle = r.text[:300]
            raise RuntimeError(f"WhatsApp ({que}): {detalle}")
        return r.json()

    def _enviar(self, para: str, cuerpo: dict) -> str:
        r = self._sesion.post(f"{GRAPH}/{self._telefono}/messages", timeout=60,
                              json={"messaging_product": "whatsapp", "to": para, **cuerpo})
        return self._revisar(r, "enviar")["messages"][0]["id"]

    def texto(self, para: str, texto: str) -> str:
        return self._enviar(para, {"type": "text", "text": {"body": texto[:4096], "preview_url": True}})

    def subir(self, archivo: Path, tipo: str) -> str:
        with archivo.open("rb") as f:
            r = self._sesion.post(f"{GRAPH}/{self._telefono}/media", timeout=300,
                                  data={"messaging_product": "whatsapp", "type": tipo},
                                  files={"file": (archivo.name, f, tipo)})
        return self._revisar(r, "subir archivo")["id"]

    def video_con_botones(self, para: str, video: Path, cuerpo: str, botones: list[tuple[str, str]]) -> str:
        media = self.subir(video_para_whatsapp(video), "video/mp4")
        return self._enviar(para, {"type": "interactive", "interactive": {
            "type": "button",
            "header": {"type": "video", "video": {"id": media}},
            "body": {"text": cuerpo[:1024]},
            "action": {"buttons": [{"type": "reply", "reply": {"id": i[:256], "title": titulo[:20]}}
                                   for i, titulo in botones[:3]]},
        }})

    def texto_con_botones(self, para: str, cuerpo: str, botones: list[tuple[str, str]]) -> str:
        return self._enviar(para, {"type": "interactive", "interactive": {
            "type": "button",
            "body": {"text": cuerpo[:1024]},
            "action": {"buttons": [{"type": "reply", "reply": {"id": i[:256], "title": titulo[:20]}}
                                   for i, titulo in botones[:3]]},
        }})

    def descargar(self, media_id: str, carpeta: Path | None = None) -> Path:
        """Baja un archivo recibido. La URL de Meta vence en 5 minutos: se baja de inmediato."""
        info = self._revisar(self._sesion.get(f"{GRAPH}/{media_id}", timeout=30), "archivo")
        r = self._sesion.get(info["url"], timeout=120)
        if not r.ok:
            raise RuntimeError(f"WhatsApp (descarga): {r.status_code}")
        carpeta = carpeta or Path(tempfile.mkdtemp(prefix="wa_"))
        destino = carpeta / f"{media_id}{EXTENSIONES.get(info.get('mime_type', '').split(';')[0], '.bin')}"
        destino.write_bytes(r.content)
        return destino

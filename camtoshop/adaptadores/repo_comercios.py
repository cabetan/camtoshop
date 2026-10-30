"""Repositorio de comercios y chats en archivos JSON, con los tokens de cada comercio cifrados.

La clave de cifrado vive en el llavero de macOS (o en CAMTOSHOP_CLAVE en el servidor) y nunca en disco
junto a los datos. Con muchos comercios esto se cambia por una base de datos sin tocar el dominio.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import uuid
from dataclasses import asdict
from pathlib import Path

from cryptography.fernet import Fernet

from camtoshop.adaptadores.config import secreto
from camtoshop.dominio.comercio import Comercio, Conexiones
from camtoshop.dominio.conversacion import Chat


def _clave() -> bytes:
    clave = secreto("CAMTOSHOP_CLAVE")
    if not clave:  # primera vez en este Mac: se crea y se guarda en el llavero
        clave = Fernet.generate_key().decode()
        subprocess.run(["security", "add-generic-password", "-U", "-a", os.environ.get("USER", ""),
                        "-s", "CAMTOSHOP_CLAVE", "-w", clave], check=True, capture_output=True)
    return clave.encode()


class RepoComercios:
    def __init__(self, carpeta: Path):
        self._comercios = carpeta / "comercios"
        self._chats = carpeta / "chats"
        self._comercios.mkdir(parents=True, exist_ok=True)
        self._chats.mkdir(parents=True, exist_ok=True)
        self._fernet = None
        self._cerrojo = threading.RLock()

    @property
    def fernet(self) -> Fernet:
        if self._fernet is None:
            self._fernet = Fernet(_clave())
        return self._fernet

    @staticmethod
    def _escribir(ruta: Path, datos: dict):
        temporal = ruta.with_suffix(".tmp")
        temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=1))
        temporal.replace(ruta)

    # --- Comercios ------------------------------------------------------------

    def crear(self, nombre: str, correo: str, idioma: str = "es") -> Comercio:
        c = Comercio(uuid.uuid4().hex[:12], nombre.strip(), correo.strip().lower(), idioma=idioma)
        self.guardar(c)
        return c

    def guardar(self, c: Comercio):
        with self._cerrojo:
            self._escribir(self._comercios / f"{c.id}.json", asdict(c))

    def obtener(self, identificador: str) -> Comercio | None:
        ruta = self._comercios / f"{identificador}.json"
        if not ruta.exists() or not identificador.isalnum():
            return None
        d = json.loads(ruta.read_text())
        d["conexiones"] = Conexiones(**d.get("conexiones", {}))
        return Comercio(**d)

    def todos(self) -> list[Comercio]:
        return [self.obtener(r.stem) for r in sorted(self._comercios.glob("*.json"))]

    def por_correo(self, correo: str) -> Comercio | None:
        return next((c for c in self.todos() if c.correo == correo.strip().lower()), None)

    # --- Tokens cifrados --------------------------------------------------------

    def guardar_token(self, comercio_id: str, nombre: str, valor: str):
        with self._cerrojo:
            tokens = self._tokens(comercio_id)
            tokens[nombre] = valor
            ruta = self._comercios / f"{comercio_id}.tokens"
            ruta.write_bytes(self.fernet.encrypt(json.dumps(tokens).encode()))

    def token(self, comercio_id: str, nombre: str) -> str | None:
        return self._tokens(comercio_id).get(nombre)

    def _tokens(self, comercio_id: str) -> dict:
        ruta = self._comercios / f"{comercio_id}.tokens"
        return json.loads(self.fernet.decrypt(ruta.read_bytes())) if ruta.exists() else {}

    # --- Chats ------------------------------------------------------------------

    def chat(self, celular: str) -> Chat:
        ruta = self._chats / f"{celular}.json"
        return Chat(**json.loads(ruta.read_text())) if ruta.exists() else Chat(celular)

    def guardar_chat(self, chat: Chat):
        with self._cerrojo:
            self._escribir(self._chats / f"{chat.celular}.json", asdict(chat))

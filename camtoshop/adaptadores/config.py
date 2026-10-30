"""Credenciales de los canales: variable de entorno o, en macOS, el llavero. Nunca se imprimen."""

from __future__ import annotations

import os
import subprocess

# Lo que necesita cada canal para estar "conectado". Shopify acepta dos formas (ver shopify.py).
CANALES = {
    "shopify": ("SHOPIFY_TIENDA", "SHOPIFY_CLIENT_ID", "SHOPIFY_CLIENT_SECRET"),
    "catalogo_meta": ("META_CATALOGO_ID", "META_TOKEN"),
    "instagram": ("IG_USUARIO_ID", "META_TOKEN"),  # IG_TOKEN, si existe, reemplaza a META_TOKEN
}


def secreto(nombre: str) -> str | None:
    valor = os.environ.get(nombre)
    if valor:
        return valor
    try:
        salida = subprocess.run(["security", "find-generic-password", "-a", os.environ.get("USER", ""),
                                 "-s", nombre, "-w"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if salida.returncode != 0:
        return None
    return salida.stdout.strip() or None


def canal_conectado(canal: str) -> bool:
    if canal == "shopify" and secreto("SHOPIFY_TIENDA") and secreto("SHOPIFY_TOKEN"):
        return True  # app personalizada antigua con token fijo
    return all(secreto(n) for n in CANALES[canal])

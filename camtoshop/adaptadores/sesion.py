"""Valores firmados con HMAC: la cookie de sesión del portal y el `state` del inicio de sesión con Facebook."""

from __future__ import annotations

import base64
import hashlib
import hmac


def _sello(clave: str, proposito: str, carga: str) -> str:
    return hmac.new(clave.encode(), f"{proposito}|{carga}".encode(), hashlib.sha256).hexdigest()


def firmar(clave: str, proposito: str, valor: str, vence: float) -> str:
    carga = base64.urlsafe_b64encode(f"{valor}|{int(vence)}".encode()).decode()
    return f"{carga}.{_sello(clave, proposito, carga)}"


def verificar(clave: str, proposito: str, firmado: str, ahora: float) -> str | None:
    """El valor firmado, o None si la firma no cuadra, venció o es de otro propósito."""
    carga, _, sello = (firmado or "").partition(".")
    if not sello or not hmac.compare_digest(sello, _sello(clave, proposito, carga)):
        return None
    valor, _, vence = base64.urlsafe_b64decode(carga).decode().rpartition("|")
    return valor if int(vence) > ahora else None

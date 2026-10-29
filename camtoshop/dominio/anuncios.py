"""Variantes de anuncio: tres ángulos de venta en los formatos de Meta."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from camtoshop.dominio.producto import recortar

# Límites recomendados por Meta Ads para que el texto no se corte.
LIMITE_TITULAR = 40
LIMITE_TEXTO = 125
LIMITE_LLAMADO = 20

FORMATOS = {
    "feed": "1024x1024",      # 1:1
    "historia": "1024x1536",  # vertical; se ajusta a 9:16
}
ANGULOS = ("beneficio", "historia", "oferta")


@dataclass
class Anuncio:
    angulo: str
    titular: str
    texto: str
    llamado: str
    concepto_visual: str  # en inglés, para Muse Image
    imagenes: dict[str, Path] | None = None


def normalizar_anuncios(propuestos: list[Anuncio]) -> list[Anuncio]:
    """Uno por ángulo, en orden, con los textos dentro de los límites de Meta."""
    por_angulo: dict[str, Anuncio] = {}
    for a in propuestos:
        if a.angulo in ANGULOS and a.angulo not in por_angulo and a.titular.strip():
            a.titular = recortar(a.titular, LIMITE_TITULAR)
            a.texto = recortar(a.texto, LIMITE_TEXTO)
            a.llamado = recortar(a.llamado, LIMITE_LLAMADO)
            por_angulo[a.angulo] = a
    return [por_angulo[x] for x in ANGULOS if x in por_angulo]

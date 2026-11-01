"""Kit de marca de un comercio: cómo se ven y cómo suenan sus Reels."""

from __future__ import annotations

import re
from dataclasses import dataclass

from camtoshop.dominio.estilos import ANTIGUOS, ESTILO_INICIAL, ESTILOS, estilo_de

FUENTES = ("barlow", "playfair", "poppins", "caveat")
MUSICAS = ("energia", "calida", "elegante", "pulso", "tarde", "cinematica", "propia", "ninguna")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
CLARO = "#F7F6F2"
OSCURO = "#141414"


@dataclass
class Marca:
    estilo: str = ESTILO_INICIAL
    fuente: str = "playfair"
    primario: str = "#FFD23F"
    secundario: str = "#141414"
    musica: str = "elegante"
    logo: bool = False  # el comercio subió logo
    musica_propia: bool = False  # el comercio subió su pista

    def __post_init__(self):
        self.estilo = ANTIGUOS.get(self.estilo, self.estilo)


@dataclass(frozen=True)
class Tema:
    """Lo que el render necesita saber, ya resuelto a colores concretos."""
    fuente: str
    texto: str  # color del texto normal
    acento: str  # color de la línea destacada y del precio
    fondo: str = ""  # vacío: la foto desenfocada; con color: fondo plano
    acento_foto: str = "#FFD23F"  # el acento cuando el texto cae sobre una foto oscurecida


def validar_marca(datos: dict) -> Marca:
    """Marca desde lo que llega del portal. ValueError con un mensaje para el comercio."""
    m = Marca(**datos)
    if m.estilo not in ESTILOS or m.fuente not in FUENTES or m.musica not in MUSICAS:
        raise ValueError("Choose one of the available options")
    if not _HEX.match(m.primario) or not _HEX.match(m.secundario):
        raise ValueError("Use colors like #FFD23F")
    if m.musica == "propia" and not m.musica_propia:
        raise ValueError("Upload your track first")
    return m


def luminancia(color: str) -> float:
    canales = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canales)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a: str, b: str) -> float:
    claro, oscuro = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (claro + 0.05) / (oscuro + 0.05)


def legible_sobre(fondo: str) -> str:
    return "#FFFFFF" if contraste(fondo, "#FFFFFF") >= contraste(fondo, OSCURO) else OSCURO


def _acento_legible(fondo: str, *candidatos: str, minimo: float = 2.5) -> str:
    """El primer color de marca que se lee sobre el fondo; si ninguno, blanco o negro."""
    return next((c for c in candidatos if contraste(c, fondo) >= minimo), legible_sobre(fondo))


def tema_de(m: Marca) -> Tema:
    """El texto siempre debe leerse: un color de marca sin contraste cede ante blanco o negro."""
    sobre_foto = _acento_legible(OSCURO, m.primario, m.secundario, minimo=4.5)  # una foto es un fondo irregular
    fondo = estilo_de(m.estilo).fondo
    if fondo == "marca":
        return Tema(m.fuente, legible_sobre(m.primario), _acento_legible(m.primario, m.secundario), m.primario, sobre_foto)
    if fondo == "claro":
        return Tema(m.fuente, OSCURO, _acento_legible(CLARO, m.primario, m.secundario), CLARO, sobre_foto)
    return Tema(m.fuente, "#FFFFFF", sobre_foto, "", sobre_foto)

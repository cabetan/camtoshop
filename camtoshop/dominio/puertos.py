"""Puertos: lo que el dominio necesita del mundo, sin saber quién lo implementa."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from camtoshop.dominio.direccion import Look, Plan, Propuesta
from camtoshop.dominio.reel import Bloque, Caja, Palabra, Tramo


class Transcriptor(Protocol):
    def transcribir(self, video: Path, idioma: str) -> list[tuple[float, float, str]]:
        """Turnos de habla: (inicio, fin, texto)."""


class Alineador(Protocol):
    def alinear(self, video: Path, turnos: list[tuple[float, float, str]], idioma: str) -> list[Palabra]:
        """Una Palabra por cada palabra de los turnos, con su tiempo exacto."""


class EditorDeTomas(Protocol):
    def elegir(self, palabras: list[Palabra], idioma: str) -> list[tuple[int, int]]:
        """Rangos inclusivos de índices de palabras que forman el mensaje limpio."""


class Rastreador(Protocol):
    def cajas(self, video: Path) -> dict[float, Caja]:
        """Caja del producto por instante del video original, en coordenadas del Reel."""


class Director(Protocol):
    def proponer(self, palabras: list[Palabra], producto: dict, look: Look, idioma: str) -> Propuesta:
        """Gancho, textos en pantalla, escenas, palabras a resaltar y cierre, sobre las palabras del Reel."""


class Ilustrador(Protocol):
    def portada(self, texto: str) -> Path:
        """Foto de estudio del producto para abrir el Reel."""

    def escena(self, prompt: str) -> Path:
        """El producto en uso, en vertical."""

    def cierre(self, titulo: str, precio: str, llamado: str) -> Path:
        """Tarjeta final con producto, precio y llamado a la acción."""


class Renderizador(Protocol):
    def render(self, video: Path, tramos: list[Tramo], bloques: list[Bloque],
               posiciones: list[float], plan: Plan, destino: Path) -> Path:
        """Corta, nivela el audio, aplica los efectos del plan y quema los subtítulos."""

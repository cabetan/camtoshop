"""Puertos: lo que el dominio necesita del mundo, sin saber quién lo implementa."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from camtoshop.dominio.anuncios import Anuncio
from camtoshop.dominio.direccion import Look, Plan, Propuesta, Revision
from camtoshop.dominio.producto import Analisis, Ficha
from camtoshop.dominio.reel import Bloque, Caja, Palabra, Tramo


class Analizador(Protocol):
    def analizar(self, video: Path) -> Analisis:
        """Mira y escucha el video: qué producto es, en qué idioma se habla, el mejor cuadro."""


class Fotografo(Protocol):
    def fotos(self, video: Path, analisis: Analisis) -> list[Path]:
        """Fotos de catálogo de estudio a partir del mejor cuadro (la primera es la principal)."""


class Redactor(Protocol):
    def ficha(self, analisis: Analisis, transcripcion: str, idiomas: list[str]) -> Ficha:
        """Ficha de venta en el idioma del video y en los demás pedidos."""


class Publicista(Protocol):
    def anuncios(self, ficha: Ficha, foto: Path) -> list[Anuncio]:
        """Tres ángulos de anuncio con su texto y su concepto visual."""

    def creativo(self, anuncio: Anuncio, foto: Path, formato: str) -> Path:
        """La pieza gráfica del anuncio en un formato."""


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

    def ajustar(self, propuesta: Propuesta, pedido: str, palabras: list[Palabra], producto: dict,
                look: Look, idioma: str) -> tuple[Propuesta, str]:
        """Aplica un pedido del comerciante; devuelve la propuesta nueva y el nombre del look."""


class Revisor(Protocol):
    def revisar(self, reel: Path, propuesta: Propuesta, palabras: list[Palabra], look: Look,
                idioma: str) -> Revision:
        """Mira el Reel terminado; si algo falla, devuelve una propuesta corregida."""


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


# --- Reel desde fotos ----------------------------------------------------------

class Guionista(Protocol):
    def guion(self, analisis: Analisis, texto: str, foto: Path, pedido: str = "",
              anterior: "Guion | None" = None, problemas: list[str] | None = None) -> "Guion":
        """Gancho, beneficios, llamado y escenas de uso para un Reel hecho solo con fotos."""


class Escenografo(Protocol):
    def escena(self, descripcion: str, recorte: Path) -> Path:
        """El producto real (desde su recorte) en una escena de uso, en vertical."""


class RenderizadorDeFotos(Protocol):
    def render(self, tomas: list["Toma"], fotos: list[Path], recortes: list[Path | None], escenas: list[Path],
               voz: Path | None, destino: Path, nombre: str = "") -> Path:
        """Compone las tomas en un Reel vertical con la voz del comerciante si la hay."""


class RevisorDeFotos(Protocol):
    def revisar(self, reel: Path, guion: "Guion", precio: str) -> tuple[bool, list[str], str]:
        """(aprobado, problemas, comentario) tras mirar el Reel terminado."""


from camtoshop.dominio.reel_fotos import Guion, Toma  # noqa: E402  (solo para las anotaciones)

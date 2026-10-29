"""Dirección del Reel: looks y plan de efectos.

El director (un modelo) propone qué decir en pantalla y dónde; estas reglas
recortan la propuesta a lo que el look permite y la pasan a tiempos del Reel.
Los auditores fijaron los límites: texto detrás del sujeto 2 veces como máximo,
escenas de 2 s como máximo y nada antes del primer segundo y medio salvo la portada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from camtoshop.dominio.reel import Caja, Palabra, Tramo


@dataclass(frozen=True)
class Look:
    nombre: str
    palabras_por_bloque: int
    usos_texto_detras: int
    escenas: int
    segundos_escena: float
    segundos_portada: float
    segundos_cierre: float
    zoom: float  # acercamiento en cortes alternos; 1.0 = sin zoom
    pop: bool  # subtítulos que saltan al aparecer cada palabra


LOOKS = {
    "directo": Look("directo", 2, 1, 1, 1.6, 0.8, 2.0, 1.12, True),
    "anuncio": Look("anuncio", 2, 2, 2, 1.4, 1.0, 3.0, 1.15, True),
    "premium": Look("premium", 3, 0, 2, 2.0, 1.4, 2.5, 1.0, False),
}
LOOK_POR_DEFECTO = "directo"

DURACION_TEXTO_DETRAS = (1.2, 3.0)
INICIO_LIBRE = 1.5  # el gancho hablado no se tapa


@dataclass(frozen=True)
class Propuesta:
    """Lo que devuelve el director, con índices de palabras del Reel."""
    texto_portada: str
    textos_detras: list[tuple[list[str], int, int]]
    escenas: list[tuple[str, int]]
    enfasis: list[int]
    cierre: tuple[str, str, str]  # título, precio, llamado a la acción


@dataclass
class Efecto:
    inicio: float
    fin: float


@dataclass
class TextoDetras(Efecto):
    lineas: list[str] = field(default_factory=list)


@dataclass
class Escena(Efecto):
    prompt: str = ""
    imagen: Path | None = None


@dataclass
class Plan:
    look: Look
    texto_portada: str
    textos_detras: list[TextoDetras]
    escenas: list[Escena]
    enfasis: set[Palabra]
    centros_zoom: list[tuple[float, float, float]]  # (zoom, x, y) por tramo
    cierre: tuple[str, str, str]
    imagen_portada: Path | None = None
    imagen_cierre: Path | None = None


def _choca(a: Efecto, ocupados: list[Efecto], aire: float = 0.3) -> bool:
    return any(a.inicio < o.fin + aire and o.inicio < a.fin + aire for o in ocupados)


def armar_plan(propuesta: Propuesta, palabras: list[Palabra], look: Look,
               centros_zoom: list[tuple[float, float, float]]) -> Plan:
    total = len(palabras)
    duracion = palabras[-1].fin if palabras else 0.0
    ocupados: list[Efecto] = []

    textos = []
    for lineas, a, b in propuesta.textos_detras:
        if len(textos) >= look.usos_texto_detras or not lineas or not (0 <= a <= b < total):
            continue
        minimo, maximo = DURACION_TEXTO_DETRAS
        inicio = palabras[a].inicio
        fin = min(max(palabras[b].fin, inicio + minimo), inicio + maximo, duracion)
        efecto = TextoDetras(inicio, fin, [l.upper() for l in lineas[:3]])
        if fin - inicio >= minimo * 0.8 and not _choca(efecto, ocupados):
            textos.append(efecto)
            ocupados.append(efecto)

    escenas = []
    for prompt, i in propuesta.escenas:
        if len(escenas) >= look.escenas or not (0 <= i < total) or not prompt.strip():
            continue
        inicio = max(palabras[i].inicio, INICIO_LIBRE)
        efecto = Escena(inicio, min(inicio + look.segundos_escena, duracion), prompt)
        if efecto.fin - efecto.inicio >= 0.8 and not _choca(efecto, ocupados):
            escenas.append(efecto)
            ocupados.append(efecto)

    return Plan(
        look=look,
        texto_portada=propuesta.texto_portada.upper(),
        textos_detras=sorted(textos, key=lambda e: e.inicio),
        escenas=sorted(escenas, key=lambda e: e.inicio),
        enfasis={palabras[i] for i in propuesta.enfasis if 0 <= i < total},
        centros_zoom=centros_zoom,
        cierre=propuesta.cierre,
    )


def centros_de_zoom(tramos: list[Tramo], cajas: dict[float, Caja], look: Look,
                    ancho: float = 1080, alto: float = 1920) -> list[tuple[float, float, float]]:
    """Acercamiento en tramos alternos, centrado en el producto y sin salirse del cuadro.

    Alternar plano abierto y cerrado disimula los saltos de cada corte.
    """
    salida = []
    for n, tramo in enumerate(tramos):
        zoom = look.zoom if n % 2 == 1 else 1.0
        dentro = [c for t, c in cajas.items() if tramo.inicio <= t <= tramo.fin]
        if dentro and zoom > 1.0:
            # A medio camino entre el centro del cuadro y el producto: sigue viéndose la cara.
            cx = (ancho / 2 + sum((c.x1 + c.x2) / 2 for c in dentro) / len(dentro)) / 2
            cy = (alto / 2 + sum((c.y1 + c.y2) / 2 for c in dentro) / len(dentro)) / 2
        else:
            cx, cy = ancho / 2, alto / 2
        medio_ancho, medio_alto = ancho / zoom / 2, alto / zoom / 2
        cx = min(max(cx, medio_ancho), ancho - medio_ancho)
        cy = min(max(cy, medio_alto), alto - medio_alto)
        salida.append((zoom, cx, cy))
    return salida


@dataclass
class Revision:
    """Lo que el revisor concluye tras mirar el Reel terminado."""
    aprobado: bool
    problemas: list[str]
    comentario: str = ""
    propuesta: Propuesta | None = None
    correcciones: dict[int, str] = field(default_factory=dict)  # índice de palabra -> texto corregido


def correcciones_validas(palabras: list[Palabra], correcciones: dict[int, str], parecido: float = 0.6) -> dict[int, str]:
    """Solo se aceptan arreglos de ortografía o de transcripción, nunca frases reescritas.

    La palabra corregida tiene que parecerse a la original (o ser la misma cifra escrita en números).
    """
    validas = {}
    for i, texto in correcciones.items():
        if not (0 <= i < len(palabras)) or not texto.strip() or " " in texto.strip():
            continue
        original = palabras[i].texto
        cercana = SequenceMatcher(None, original.lower(), texto.lower()).ratio() >= parecido
        if cercana and texto != original:
            validas[i] = texto.strip()
    return validas

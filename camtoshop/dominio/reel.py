"""Reglas de edición del Reel: qué se conserva, cómo se corta y dónde van los subtítulos.

Todo aquí es puro: recibe datos y devuelve datos. Los tiempos van en segundos.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Una pausa entre palabras conservadas más larga que esto se recorta.
PAUSA_MAXIMA = 0.35
# Aire que se deja antes y después de cada tramo para no comerse sílabas.
MARGEN = 0.08
# Un tramo más corto que esto deja una isla de una sílaba que suena a error.
TRAMO_MINIMO = 0.12


@dataclass(frozen=True)
class Palabra:
    texto: str
    inicio: float
    fin: float


@dataclass(frozen=True)
class Tramo:
    inicio: float
    fin: float

    @property
    def duracion(self) -> float:
        return self.fin - self.inicio


@dataclass(frozen=True)
class Caja:
    """Caja del producto en coordenadas del video final."""
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass
class Bloque:
    """Grupo de 1 a 3 palabras que aparecen juntas en pantalla."""
    palabras: list[Palabra] = field(default_factory=list)

    @property
    def inicio(self) -> float:
        return self.palabras[0].inicio

    @property
    def fin(self) -> float:
        return self.palabras[-1].fin

    @property
    def texto(self) -> str:
        return " ".join(p.texto for p in self.palabras)


def indices_conservados(rangos: list[tuple[int, int]], total: int) -> list[int]:
    """Convierte rangos inclusivos [a, b] (posiblemente desordenados o solapados) en índices válidos."""
    elegidos: set[int] = set()
    for a, b in rangos:
        a, b = sorted((a, b))
        elegidos.update(i for i in range(max(0, a), min(total - 1, b) + 1))
    return sorted(elegidos)


def tramos_desde_palabras(palabras: list[Palabra], conservar: list[int],
                          pausa_maxima: float = PAUSA_MAXIMA, margen: float = MARGEN,
                          tramo_minimo: float = TRAMO_MINIMO) -> list[Tramo]:
    """Tramos del video original que forman el Reel.

    Se abre un tramo nuevo cuando hay una palabra descartada en medio o una pausa
    larga. El margen nunca invade una palabra descartada vecina.
    """
    if not conservar:
        return []
    grupos: list[list[int]] = [[conservar[0]]]
    for i in conservar[1:]:
        anterior = grupos[-1][-1]
        pausa = palabras[i].inicio - palabras[anterior].fin
        if i != anterior + 1 or pausa > pausa_maxima:
            grupos.append([i])
        else:
            grupos[-1].append(i)

    tramos: list[Tramo] = []
    for grupo in grupos:
        primero, ultimo = grupo[0], grupo[-1]
        limite_izq = palabras[primero - 1].fin if primero > 0 else 0.0
        limite_der = palabras[ultimo + 1].inicio if ultimo + 1 < len(palabras) else palabras[ultimo].fin + margen
        inicio = max(palabras[primero].inicio - margen, limite_izq, 0.0)
        fin = min(palabras[ultimo].fin + margen, max(limite_der, palabras[ultimo].fin))
        if fin - inicio < tramo_minimo:
            continue
        if tramos and inicio <= tramos[-1].fin:
            tramos[-1] = Tramo(tramos[-1].inicio, max(fin, tramos[-1].fin))
        else:
            tramos.append(Tramo(inicio, fin))
    return tramos


def a_linea_del_reel(t: float, tramos: list[Tramo]) -> float | None:
    """Traduce un instante del video original al Reel; None si quedó cortado."""
    acumulado = 0.0
    for tramo in tramos:
        if tramo.inicio <= t <= tramo.fin:
            return acumulado + (t - tramo.inicio)
        acumulado += tramo.duracion
    return None


def al_original(t: float, tramos: list[Tramo]) -> float:
    """Traduce un instante del Reel al video original."""
    acumulado = 0.0
    for tramo in tramos:
        if t <= acumulado + tramo.duracion:
            return tramo.inicio + (t - acumulado)
        acumulado += tramo.duracion
    return tramos[-1].fin if tramos else t


def palabras_del_reel(palabras: list[Palabra], conservar: list[int], tramos: list[Tramo]) -> list[Palabra]:
    """Palabras conservadas con sus tiempos ya en la línea del Reel."""
    salida = []
    for i in conservar:
        p = palabras[i]
        inicio = a_linea_del_reel(p.inicio, tramos)
        fin = a_linea_del_reel(p.fin, tramos)
        if inicio is None or fin is None:
            continue
        salida.append(Palabra(p.texto, inicio, max(fin, inicio + 0.05)))
    return salida


def armar_bloques(palabras: list[Palabra], max_palabras: int = 3, max_caracteres: int = 16) -> list[Bloque]:
    """Agrupa palabras en bloques cortos; un punto o una coma cierra el bloque."""
    bloques: list[Bloque] = []
    actual = Bloque()
    for p in palabras:
        largo = len(actual.texto) + 1 + len(p.texto) if actual.palabras else len(p.texto)
        if actual.palabras and (len(actual.palabras) >= max_palabras or largo > max_caracteres):
            bloques.append(actual)
            actual = Bloque()
        actual.palabras.append(p)
        if p.texto[-1:] in ".,!?;:":
            bloques.append(actual)
            actual = Bloque()
    if actual.palabras:
        bloques.append(actual)
    return bloques


def posicion_subtitulo(producto: Caja | None, alto_bloque: float, alto_video: float = 1920,
                       zona_segura: tuple[float, float] = (0.20, 0.80), aire: float = 30) -> float:
    """Borde superior del subtítulo, sin tapar el producto.

    La zona segura deja libre la parte de arriba y la de abajo, donde Instagram pone
    su interfaz. Se prefiere debajo del producto; si no cabe, encima; si no cabe en
    ningún lado, se usa el borde inferior de la zona segura.
    """
    arriba, abajo = zona_segura[0] * alto_video, zona_segura[1] * alto_video
    por_defecto = abajo - alto_bloque
    if producto is None:
        return por_defecto
    debajo = producto.y2 + aire
    if debajo + alto_bloque <= abajo:
        return debajo
    encima = producto.y1 - aire - alto_bloque
    if encima >= arriba:
        return encima
    return por_defecto

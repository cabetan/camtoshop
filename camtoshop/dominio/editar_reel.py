"""Casos de uso del Reel: preparar el montaje, dirigirlo, revisarlo y rehacerlo a pedido.

1. `preparar_montaje`: transcribe, alinea, elige las tomas y rastrea el producto (una vez por video).
2. `dirigir_y_revisar`: el director propone, se renderiza y el revisor mira el resultado; si
   encuentra problemas propone una dirección corregida y se vuelve a renderizar (agente con bucle).
3. `rehacer`: el comerciante pide un cambio en palabras ("más sobrio") y el director lo aplica.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from camtoshop.dominio.direccion import (
    LOOKS, Look, Plan, Propuesta, armar_plan, centros_de_zoom, correcciones_validas,
)
from camtoshop.dominio.puertos import (
    Alineador, Director, EditorDeTomas, Ilustrador, Rastreador, Renderizador, Revisor, Transcriptor,
)
from camtoshop.dominio.reel import (
    Bloque, Caja, Palabra, Tramo, al_original, armar_bloques, indices_conservados, palabras_del_reel,
    posicion_subtitulo, tramos_desde_palabras,
)

ALTO_BLOQUE = 150
RONDAS_DE_REVISION = 2

Aviso = Callable[[str], None]


@dataclass
class Montaje:
    """Todo lo que no depende de la dirección: se calcula una vez por video."""
    video: Path
    idioma: str
    palabras: list[Palabra]
    conservadas: list[int]
    tramos: list[Tramo]
    del_reel: list[Palabra]
    cajas: dict[float, Caja]

    @property
    def duracion(self) -> float:
        return sum(t.duracion for t in self.tramos)


@dataclass
class ResultadoReel:
    reel: Path
    montaje: Montaje
    propuesta: Propuesta
    plan: Plan
    bloques: list[Bloque]
    bitacora: list[str] = field(default_factory=list)

    # Atajos usados por los scripts y las pruebas.
    @property
    def palabras(self) -> list[Palabra]:
        return self.montaje.palabras

    @property
    def conservadas(self) -> list[int]:
        return self.montaje.conservadas

    @property
    def tramos(self) -> list[Tramo]:
        return self.montaje.tramos

    @property
    def duracion(self) -> float:
        return self.montaje.duracion


@dataclass
class Puertos:
    transcriptor: Transcriptor
    alineador: Alineador
    editor: EditorDeTomas
    rastreador: Rastreador
    director: Director
    ilustrador: Ilustrador
    renderizador: Renderizador
    revisor: Revisor | None = None


def caja_en(cajas: dict[float, Caja], inicio: float, fin: float) -> Caja | None:
    """Envolvente de las cajas del producto mientras se ve un bloque."""
    dentro = [c for t, c in cajas.items() if inicio <= t <= fin]
    if not dentro:
        cercano = min(cajas, key=lambda t: abs(t - (inicio + fin) / 2), default=None)
        return cajas[cercano] if cercano is not None else None
    return Caja(min(c.x1 for c in dentro), min(c.y1 for c in dentro),
                max(c.x2 for c in dentro), max(c.y2 for c in dentro))


def preparar_montaje(video: Path, idioma: str, p: Puertos, avisar: Aviso = lambda _: None) -> Montaje:
    avisar("Transcribiendo con Muse Voice Transcribe")
    turnos = p.transcriptor.transcribir(video, idioma)
    avisar("Alineando cada palabra con XLSR-53")
    palabras = p.alineador.alinear(video, turnos, idioma)
    avisar("Muse Spark elige las tomas buenas")
    conservadas = indices_conservados(p.editor.elegir(palabras, idioma), len(palabras))
    tramos = tramos_desde_palabras(palabras, conservadas)
    avisar("SAM 3.1 sigue el producto cuadro a cuadro")
    cajas = p.rastreador.cajas(video)
    return Montaje(video, idioma, palabras, conservadas, tramos,
                   palabras_del_reel(palabras, conservadas, tramos), cajas)


def renderizar(m: Montaje, propuesta: Propuesta, look: Look, destino: Path, p: Puertos) -> ResultadoReel:
    plan = armar_plan(propuesta, m.del_reel, look, centros_de_zoom(m.tramos, m.cajas, look))
    plan.imagen_portada = p.ilustrador.portada(plan.texto_portada)
    for escena in plan.escenas:
        escena.imagen = p.ilustrador.escena(escena.prompt)
    plan.imagen_cierre = p.ilustrador.cierre(*plan.cierre)

    bloques = armar_bloques(m.del_reel, max_palabras=look.palabras_por_bloque)
    # Los bloques viven en la línea del Reel; las cajas, en la del original.
    posiciones = []
    for bloque in bloques:
        inicio, fin = al_original(bloque.inicio, m.tramos), al_original(bloque.fin, m.tramos)
        posiciones.append(posicion_subtitulo(caja_en(m.cajas, inicio, fin), ALTO_BLOQUE))

    p.renderizador.render(m.video, m.tramos, bloques, posiciones, plan, destino)
    return ResultadoReel(destino, m, propuesta, plan, bloques)


def dirigir_y_revisar(m: Montaje, producto: dict, look: Look, destino: Path, p: Puertos,
                      avisar: Aviso = lambda _: None, rondas: int = RONDAS_DE_REVISION) -> ResultadoReel:
    """El director propone; el revisor mira el Reel terminado y, si hace falta, lo corrige."""
    bitacora: list[str] = []

    def anotar(texto: str):
        bitacora.append(texto)
        avisar(texto)

    anotar(f"Muse Spark dirige el Reel (look {look.nombre})")
    propuesta = p.director.proponer(m.del_reel, producto, look, m.idioma)
    resultado = None
    for ronda in range(1, rondas + 1):
        anotar(f"Renderizando (versión {ronda})")
        resultado = renderizar(m, propuesta, look, destino, p)
        if p.revisor is None or ronda == rondas:
            break
        anotar("Muse Spark revisa el Reel terminado")
        try:
            revision = p.revisor.revisar(resultado.reel, propuesta, m.del_reel, look, m.idioma)
        except Exception as e:  # sin revisión se entrega lo ya renderizado, no se pierde el trabajo
            anotar(f"Revisión no disponible, se entrega la versión {ronda} ({e.__class__.__name__})")
            break
        arreglos = correcciones_validas(m.del_reel, revision.correcciones)
        if (revision.aprobado or revision.propuesta is None) and not arreglos:
            anotar("Revisión aprobada" + (f": {revision.comentario}" if revision.comentario else ""))
            break
        anotar("Corrige: " + "; ".join(revision.problemas))
        if arreglos:
            anotar("Subtítulos corregidos: " + ", ".join(f"{m.del_reel[i].texto} → {t}" for i, t in arreglos.items()))
            m.del_reel = [Palabra(arreglos.get(i, w.texto), w.inicio, w.fin) for i, w in enumerate(m.del_reel)]
        propuesta = revision.propuesta or propuesta
    resultado.bitacora = bitacora
    return resultado


def rehacer(m: Montaje, anterior: ResultadoReel, pedido: str, producto: dict, destino: Path, p: Puertos,
            avisar: Aviso = lambda _: None) -> ResultadoReel:
    """El comerciante pide un cambio en sus palabras; el director ajusta la propuesta y quizás el look."""
    avisar(f"Muse Spark interpreta el pedido: «{pedido}»")
    propuesta, nombre_look = p.director.ajustar(anterior.propuesta, pedido, m.del_reel, producto,
                                                anterior.plan.look, m.idioma)
    look = LOOKS.get(nombre_look, anterior.plan.look)
    avisar(f"Renderizando con el look {look.nombre}")
    resultado = renderizar(m, propuesta, look, destino, p)
    resultado.bitacora = anterior.bitacora + [f"Pedido: «{pedido}» → look {look.nombre}"]
    return resultado


def editar_reel(video: Path, idioma: str, producto: dict, destino: Path, p: Puertos,
                look: Look = LOOKS["directo"]) -> ResultadoReel:
    """Todo el flujo de una vez."""
    return dirigir_y_revisar(preparar_montaje(video, idioma, p), producto, look, destino, p)

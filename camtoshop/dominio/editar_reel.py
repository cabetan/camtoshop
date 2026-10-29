"""Caso de uso: de la grabación del comerciante a un Reel dirigido, con efectos y subtítulos."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from camtoshop.dominio.direccion import LOOKS, Look, Plan, armar_plan, centros_de_zoom
from camtoshop.dominio.puertos import (
    Alineador, Director, EditorDeTomas, Ilustrador, Rastreador, Renderizador, Transcriptor,
)
from camtoshop.dominio.reel import (
    Bloque, Caja, Palabra, Tramo, al_original, armar_bloques, indices_conservados, palabras_del_reel,
    posicion_subtitulo, tramos_desde_palabras,
)

ALTO_BLOQUE = 150


@dataclass
class ResultadoReel:
    reel: Path
    palabras: list[Palabra]
    conservadas: list[int]
    tramos: list[Tramo]
    bloques: list[Bloque]
    plan: Plan

    @property
    def duracion(self) -> float:
        return sum(t.duracion for t in self.tramos)


@dataclass
class Puertos:
    transcriptor: Transcriptor
    alineador: Alineador
    editor: EditorDeTomas
    rastreador: Rastreador
    director: Director
    ilustrador: Ilustrador
    renderizador: Renderizador


def caja_en(cajas: dict[float, Caja], inicio: float, fin: float) -> Caja | None:
    """Envolvente de las cajas del producto mientras se ve un bloque."""
    dentro = [c for t, c in cajas.items() if inicio <= t <= fin]
    if not dentro:
        cercano = min(cajas, key=lambda t: abs(t - (inicio + fin) / 2), default=None)
        return cajas[cercano] if cercano is not None else None
    return Caja(min(c.x1 for c in dentro), min(c.y1 for c in dentro),
                max(c.x2 for c in dentro), max(c.y2 for c in dentro))


def editar_reel(video: Path, idioma: str, producto: dict, destino: Path, p: Puertos,
                look: Look = LOOKS["directo"]) -> ResultadoReel:
    turnos = p.transcriptor.transcribir(video, idioma)
    palabras = p.alineador.alinear(video, turnos, idioma)
    conservadas = indices_conservados(p.editor.elegir(palabras, idioma), len(palabras))
    tramos = tramos_desde_palabras(palabras, conservadas)
    del_reel = palabras_del_reel(palabras, conservadas, tramos)
    cajas = p.rastreador.cajas(video)

    plan = armar_plan(p.director.proponer(del_reel, producto, look, idioma), del_reel, look,
                      centros_de_zoom(tramos, cajas, look))
    plan.imagen_portada = p.ilustrador.portada(plan.texto_portada)
    for escena in plan.escenas:
        escena.imagen = p.ilustrador.escena(escena.prompt)
    plan.imagen_cierre = p.ilustrador.cierre(*plan.cierre)

    bloques = armar_bloques(del_reel, max_palabras=look.palabras_por_bloque)
    # Los bloques viven en la línea del Reel; las cajas, en la del original.
    posiciones = []
    for bloque in bloques:
        inicio, fin = al_original(bloque.inicio, tramos), al_original(bloque.fin, tramos)
        posiciones.append(posicion_subtitulo(caja_en(cajas, inicio, fin), ALTO_BLOQUE))

    p.renderizador.render(video, tramos, bloques, posiciones, plan, destino)
    return ResultadoReel(destino, palabras, conservadas, tramos, bloques, plan)

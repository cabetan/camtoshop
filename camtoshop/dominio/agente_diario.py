"""Agente diario: cada mañana propone qué promocionar y aprende de lo que funcionó en Instagram.

Solo propone: el Reel se hace si el comercio toca «Hazlo», y se publica si toca «Publicar».
Con pocos datos no saca conclusiones: una lección exige varios Reels de cada estilo de gancho.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from camtoshop.dominio.producto import ProductoDeTienda, apto_para_reel
from camtoshop.dominio.reel_fotos import montos_en

DESCANSO_DIAS = 14  # un producto no se repite antes de esto, mientras haya otros
MIN_POR_ESTILO = 2
INSTRUCCION = {
    "pregunta": "Open with a question the buyer would ask themselves.",
    "precio": "Open with the value or the price.",
    "directo": "Open with the main benefit, stated directly.",
}


@dataclass(frozen=True)
class Desempeno:
    gancho: str
    alcance: int
    me_gusta: int = 0
    comentarios: int = 0
    compartidos: int = 0
    guardados: int = 0

    @property
    def tasa(self) -> float:
        """Interacción por cada 100 personas alcanzadas; guardar y compartir pesan más que un me gusta."""
        puntos = self.me_gusta + 2 * self.comentarios + 3 * (self.compartidos + self.guardados)
        return 100 * puntos / max(self.alcance, 1)


@dataclass(frozen=True)
class Leccion:
    estilo: str
    tasa: float
    tasa_otros: float
    reels: int


@dataclass(frozen=True)
class Propuesta:
    producto: ProductoDeTienda
    dias_sin_promover: int | None  # None: nunca se ha promovido
    leccion: Leccion | None

    @property
    def pedido(self) -> str:
        return INSTRUCCION[self.leccion.estilo] if self.leccion else ""


def estilo_de(gancho: str) -> str:
    if "?" in gancho or "¿" in gancho:
        return "pregunta"
    if montos_en(gancho) or re.search(r"\b(precio|price|oferta|offer)\b", gancho, re.I):
        return "precio"
    return "directo"


def aprender(desempenos: list[Desempeno]) -> Leccion | None:
    """El estilo de gancho que mejor funciona, si hay con qué compararlo y una ventaja real."""
    por_estilo: dict[str, list[Desempeno]] = {}
    for d in desempenos:
        if d.alcance > 0:
            por_estilo.setdefault(estilo_de(d.gancho), []).append(d)
    validos = {e: v for e, v in por_estilo.items() if len(v) >= MIN_POR_ESTILO}
    if len(validos) < 2:
        return None
    promedio = {e: sum(d.tasa for d in v) / len(v) for e, v in validos.items()}
    mejor = max(promedio, key=promedio.get)
    otros = [d.tasa for e, v in validos.items() if e != mejor for d in v]
    tasa_otros = sum(otros) / len(otros)
    if promedio[mejor] <= tasa_otros * 1.2:
        return None  # una diferencia pequeña puede ser casualidad
    return Leccion(mejor, promedio[mejor], tasa_otros, len(validos[mejor]))


def elegir_producto(productos: list[ProductoDeTienda], promovidos: dict[str, str], dia: str,
                    excluir: tuple[str, ...] = (), incluir_borradores: bool = False) -> ProductoDeTienda | None:
    """El producto que lleva más tiempo sin promoverse; los recién promovidos solo si no queda otro."""
    def dias(p: ProductoDeTienda) -> int:
        ultimo = promovidos.get(p.handle)
        return 10 ** 6 if not ultimo else (date.fromisoformat(dia) - date.fromisoformat(ultimo)).days

    aptos = [p for p in productos if apto_para_reel(p) and p.handle not in excluir
             and (p.estado == "ACTIVE" or (incluir_borradores and p.estado == "DRAFT"))]
    descansados = [p for p in aptos if dias(p) >= DESCANSO_DIAS] or aptos
    return max(descansados, key=dias, default=None)


def proponer(productos: list[ProductoDeTienda], promovidos: dict[str, str], desempenos: list[Desempeno], dia: str,
             excluir: tuple[str, ...] = (), incluir_borradores: bool = False) -> Propuesta | None:
    producto = elegir_producto(productos, promovidos, dia, excluir, incluir_borradores)
    if producto is None:
        return None
    ultimo = promovidos.get(producto.handle)
    dias = (date.fromisoformat(dia) - date.fromisoformat(ultimo)).days if ultimo else None
    return Propuesta(producto, dias, aprender(desempenos))


NOMBRES_ESTILO = {"es": {"pregunta": "con pregunta", "precio": "con el precio", "directo": "directos"},
                  "en": {"pregunta": "with a question", "precio": "with the price", "directo": "that are direct"}}


def _numero(valor: float, idioma: str) -> str:
    texto = f"{valor:.1f}"
    return texto.replace(".", ",") if idioma == "es" else texto


def texto_de_propuesta(p: Propuesta, idioma: str) -> str:
    producto = p.producto
    precio = f" ({producto.precio.texto()})" if producto.precio else ""
    if idioma == "en":
        motivo = "It hasn't been on your socials yet." if p.dias_sin_promover is None \
            else f"It's been {p.dias_sin_promover} days since you promoted it."
        partes = [f"☀️ Good morning! Today I'd promote *{producto.titulo}*{precio}. {motivo}"]
        if p.leccion:
            partes.append(f"📈 Your hooks {NOMBRES_ESTILO['en'][p.leccion.estilo]} get "
                          f"{p.leccion.tasa:.1f} interactions per 100 people, vs {p.leccion.tasa_otros:.1f} for the "
                          f"rest ({p.leccion.reels} Reels). I'll use that.")
        partes.append("Shall I make the Reel?")
    else:
        motivo = "Todavía no ha salido en tus redes." if p.dias_sin_promover is None \
            else f"Lleva {p.dias_sin_promover} días sin promocionarse."
        partes = [f"☀️ ¡Buenos días! Hoy te propongo promocionar *{producto.titulo}*{precio}. {motivo}"]
        if p.leccion:
            partes.append(f"📈 Tus ganchos {NOMBRES_ESTILO['es'][p.leccion.estilo]} logran "
                          f"{_numero(p.leccion.tasa, 'es')} interacciones por cada 100 personas, frente a "
                          f"{_numero(p.leccion.tasa_otros, 'es')} del resto ({p.leccion.reels} Reels). Voy a usar eso.")
        partes.append("¿Te hago el Reel?")
    return "\n\n".join(partes)

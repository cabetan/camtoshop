"""Reel desde fotos: cuando nadie grabó un video, el Reel se arma con las fotos reales del producto.

El guionista (un modelo) propone el gancho, los beneficios y el llamado; estas reglas los
recortan a lo que se lee en un Reel, quitan lo que el comerciante no dijo y reparten el tiempo.
Los auditores fijaron la forma: 8 a 15 s, gancho en el primer segundo, 3 beneficios cortos,
precio grande antes del final y llamado claro. El precio nunca lo inventa el modelo.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from camtoshop.dominio.producto import Precio

PALABRAS_GANCHO = 6
PALABRAS_BENEFICIO = 4
MAX_BENEFICIOS = 3
DURACION = (8.0, 20.0)  # con nota de voz el Reel puede durar lo que dura la voz, hasta 20 s
SEGUNDOS = {"gancho": 1.8, "beneficio": 1.7, "escena": 1.7, "precio": 2.2, "cierre": 2.0}
MOVIMIENTOS = ("acercar", "izquierda", "alejar", "derecha")

# Promesas que comprometen al comerciante: solo salen si él las dijo.
SENSIBLES = (
    r"env[ií]o gratis", r"free shipping", r"garant[ií]a", r"warrant", r"org[aá]nic", r"organic",
    r"100 ?%", r"certificad", r"certified", r"cura", r"cures?", r"sin qu[ií]micos", r"chemical[- ]free",
    r"hecho a mano", r"handmade", r"el mejor", r"the best", r"descuento", r"discount", r"\d+ ?% off",
)


@dataclass
class Guion:
    gancho: str
    beneficios: list[str]
    llamado: str
    escenas: list[str] = field(default_factory=list)  # qué mostrar en las escenas de uso (en inglés)


@dataclass(frozen=True)
class Toma:
    tipo: str  # gancho | beneficio | escena | precio | cierre
    inicio: float
    fin: float
    lineas: tuple[str, ...]
    imagen: int  # índice de la foto (o de la escena, si tipo == "escena")
    movimiento: str

    @property
    def duracion(self) -> float:
        return self.fin - self.inicio


def _plano(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in sin_tildes if not unicodedata.combining(c))


def dicho_en(frase: str, fuente: str) -> bool:
    """True si la frase no hace promesas sensibles o si cada promesa aparece en lo que dio el comerciante."""
    f, origen = _plano(frase), _plano(fuente)
    for patron in SENSIBLES:
        p = _plano(patron)
        if re.search(p, f) and not re.search(p, origen):
            return False
    return True


def recortar_palabras(texto: str, maximo: int) -> str:
    palabras = texto.replace("\n", " ").split()
    return " ".join(palabras[:maximo]).strip(" ,.;:-")


def limpiar_guion(guion: Guion, fuente: str) -> tuple[Guion, list[str]]:
    """Recorta el guion a lo legible y quita promesas no dichas. Devuelve el guion y los avisos."""
    avisos = []
    beneficios = []
    for b in guion.beneficios:
        corto = recortar_palabras(b, PALABRAS_BENEFICIO)
        if not corto:
            continue
        if not dicho_en(corto, fuente):
            avisos.append(f"Quité «{corto}»: el comerciante no lo dijo.")
            continue
        if _plano(corto) not in {_plano(x) for x in beneficios}:
            beneficios.append(corto)
    gancho = recortar_palabras(guion.gancho, PALABRAS_GANCHO)
    if not dicho_en(gancho, fuente):
        avisos.append(f"Cambié el gancho «{gancho}»: prometía algo que el comerciante no dijo.")
        gancho = beneficios[0] if beneficios else ""
    llamado = recortar_palabras(guion.llamado, 4)
    return Guion(gancho, beneficios[:MAX_BENEFICIOS], llamado, guion.escenas[:2]), avisos


_NUMERO = re.compile(r"(\d+(?:[.,]\d{3})*(?:[.,]\d{1,2})?)\s*(millones|millón|millon|mil|k)?", re.I)


def montos_en(texto: str) -> set[float]:
    """Montos escritos por el comerciante: «85 mil», «85.000», «$85,000», «49.90», «1,5 millones»."""
    montos = set()
    for numero, sufijo in _NUMERO.findall(texto):
        limpio = numero
        if re.fullmatch(r"\d{1,3}([.,]\d{3})+", numero):
            limpio = re.sub(r"[.,]", "", numero)  # separadores de miles
        else:
            limpio = numero.replace(",", ".")
        valor = float(limpio)
        sufijo = sufijo.lower()
        if sufijo in {"mil", "k"}:
            valor *= 1000
        elif sufijo.startswith("mill"):
            valor *= 1_000_000
        montos.add(round(valor, 2))
    return montos


def precio_respaldado(precio: Precio | None, fuente: str) -> bool:
    """El precio solo vale si el comerciante (o su tienda) lo escribió o lo dijo."""
    return precio is not None and round(precio.monto, 2) in montos_en(fuente)


def lineas_de(texto: str, max_caracteres: int = 14) -> tuple[str, ...]:
    """Parte el texto en 1 a 3 líneas parejas para la tipografía gigante."""
    palabras = texto.upper().split()
    if not palabras:
        return ()
    lineas: list[str] = []
    for p in palabras:
        if lineas and len(lineas[-1]) + 1 + len(p) <= max_caracteres:
            lineas[-1] += " " + p
        else:
            lineas.append(p)
    while len(lineas) > 3:  # se juntan las dos más cortas vecinas
        i = min(range(len(lineas) - 1), key=lambda k: len(lineas[k]) + len(lineas[k + 1]))
        lineas[i:i + 2] = [lineas[i] + " " + lineas[i + 1]]
    return tuple(lineas)


def armar_tomas(guion: Guion, fotos: int, escenas: int, precio: Precio | None,
                duracion_voz: float | None = None) -> list[Toma]:
    """Reparte el guion en tomas: gancho, beneficios (alternando fotos y escenas), precio y cierre.

    Las fotos reales se usan en orden y se repiten si hay pocas. Con nota de voz, los beneficios
    se estiran para que el Reel dure lo que dura la voz (dentro de DURACION).
    """
    if fotos < 1:
        raise ValueError("Hace falta al menos una foto del producto.")
    plan: list[tuple[str, tuple[str, ...], int]] = [("gancho", lineas_de(guion.gancho), 0)]
    siguiente_foto, siguiente_escena = 1, 0
    for n, beneficio in enumerate(guion.beneficios):
        if n % 2 == 1 and siguiente_escena < escenas:
            plan.append(("escena", lineas_de(beneficio), siguiente_escena))
            siguiente_escena += 1
        else:
            plan.append(("beneficio", lineas_de(beneficio), siguiente_foto % fotos))
            siguiente_foto += 1
    if precio is not None:
        plan.append(("precio", (precio.texto(),), 0))
    plan.append(("cierre", lineas_de(guion.llamado), siguiente_foto % fotos))

    duraciones = [SEGUNDOS[tipo] for tipo, _, _ in plan]
    total = sum(duraciones)
    objetivo = min(max(duracion_voz + 0.6 if duracion_voz else total, DURACION[0]), DURACION[1])
    elasticas = [i for i, (tipo, _, _) in enumerate(plan) if tipo in {"beneficio", "escena"}] or [0]
    extra = (objetivo - total) / len(elasticas)
    for i in elasticas:
        duraciones[i] = max(1.2, duraciones[i] + extra)

    tomas, t = [], 0.0
    for n, ((tipo, lineas, imagen), d) in enumerate(zip(plan, duraciones)):
        tomas.append(Toma(tipo, round(t, 3), round(t + d, 3), lineas, imagen, MOVIMIENTOS[n % len(MOVIMIENTOS)]))
        t += d
    return tomas


# --- Caso de uso ----------------------------------------------------------------

@dataclass
class PuertosFotos:
    guionista: object  # Guionista
    escenografo: object  # Escenografo
    renderizador: object  # RenderizadorDeFotos
    revisor: object | None = None  # RevisorDeFotos


@dataclass
class ReelDeFotos:
    reel: object  # Path
    guion: Guion
    tomas: list[Toma]
    bitacora: list[str]
    avisos: list[str]


def reel_desde_fotos(analisis, texto: str, fotos: list, recortes: list, precio: Precio | None, voz,
                     duracion_voz: float | None, destino, p: PuertosFotos, avisar=lambda t: None,
                     pedido: str = "", anterior: Guion | None = None, rondas: int = 1) -> ReelDeFotos:
    """Guion → escenas desde el recorte real → render → revisión → (corrección y nuevo render)."""
    fuente = " ".join([texto, analisis.texto_etiqueta])
    bitacora: list[str] = []

    def anotar(t: str):
        bitacora.append(t)
        avisar(t)

    principal = int(analisis.mejor_cuadro_s) if int(analisis.mejor_cuadro_s) < len(fotos) else 0
    anotar("Muse Spark escribe el guion del Reel" if not pedido else f"Muse Spark reescribe el guion: «{pedido}»")
    guion, avisos = limpiar_guion(p.guionista.guion(analisis, texto, fotos[principal], pedido, anterior), fuente)
    for a in avisos:
        anotar(a)

    reales = [r for r in recortes if r is not None]
    necesarias = len(guion.beneficios) // 2
    escenas = []
    if reales and necesarias:
        anotar("Muse Image pone el producto real en una escena de uso")
        escenas = [p.escenografo.escena(d, reales[0]) for d in guion.escenas[:necesarias]]

    nombre = analisis.nombre
    precio_texto = precio.texto() if precio else ""
    for ronda in range(rondas + 1):
        tomas = armar_tomas(guion, len(fotos), len(escenas), precio, duracion_voz)
        anotar(f"Renderizando {tomas[-1].fin:.0f} s: producto recortado con SAM, en capas")
        p.renderizador.render(tomas, fotos, recortes, escenas, voz, destino, nombre)
        if p.revisor is None or ronda == rondas:
            break
        try:
            aprobado, problemas, comentario = p.revisor.revisar(destino, guion, precio_texto)
        except Exception as e:  # sin revisión el Reel sigue siendo válido
            anotar(f"No se pudo revisar el Reel: {e}")
            break
        anotar(f"Muse Spark revisa el Reel: {comentario}")
        if aprobado or not problemas:
            break
        anotar("Corrige: " + "; ".join(problemas))
        nuevo = p.guionista.guion(analisis, texto, fotos[principal], "", guion, problemas)
        guion, mas = limpiar_guion(nuevo, fuente)
        avisos += mas
    return ReelDeFotos(destino, guion, tomas, bitacora, avisos)

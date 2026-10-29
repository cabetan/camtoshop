"""Producto, ficha de venta y precio: lo que el comerciante dijo, convertido en datos vendibles."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Monedas sin decimales en la práctica comercial.
SIN_DECIMALES = {"COP", "CLP", "JPY", "KRW", "PYG", "VND", "HUF"}
SIMBOLOS = {"COP": "$", "USD": "US$", "EUR": "€", "MXN": "MX$", "BRL": "R$", "GBP": "£"}
LIMITE_TITULO = 70
LIMITE_SEO_DESCRIPCION = 160


@dataclass(frozen=True)
class Analisis:
    """Lo que Muse Spark entendió del video."""
    nombre: str
    marca: str
    categoria: str
    atributos: list[str]
    texto_etiqueta: str
    precio_mencionado: str
    conceptos_sam: list[str]
    idioma: str
    mejor_cuadro_s: float
    gancho: str


@dataclass(frozen=True)
class Precio:
    monto: float
    moneda: str

    def texto(self) -> str:
        simbolo = SIMBOLOS.get(self.moneda, self.moneda + " ")
        if self.moneda in SIN_DECIMALES or self.monto == int(self.monto):
            entero = f"{int(round(self.monto)):,}"
            return simbolo + (entero.replace(",", ".") if self.moneda in {"COP", "CLP", "EUR", "BRL"} else entero)
        return f"{simbolo}{self.monto:,.2f}"

    def para_api(self) -> str:
        """Monto como texto plano con punto decimal, como lo piden Shopify y Meta."""
        return f"{self.monto:.0f}" if self.moneda in SIN_DECIMALES else f"{self.monto:.2f}"


@dataclass
class Texto:
    """Título, descripción y viñetas en un idioma."""
    titulo: str
    descripcion: str
    puntos: list[str]
    seo_titulo: str = ""
    seo_descripcion: str = ""


@dataclass
class Ficha:
    idioma: str
    textos: dict[str, Texto]  # por código de idioma; incluye el del video
    precio: Precio | None
    marca: str
    categoria: str
    etiquetas: list[str] = field(default_factory=list)
    imagenes: list[str] = field(default_factory=list)  # rutas locales

    @property
    def principal(self) -> Texto:
        return self.textos[self.idioma]

    @property
    def identificador(self) -> str:
        return slug(f"{self.marca} {self.principal.titulo}" if self.marca else self.principal.titulo)


def slug(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", sin_tildes.lower()).strip("-")[:60]


def precio_valido(monto: float | None, moneda: str | None) -> Precio | None:
    """Spark extrae el precio en cifras; aquí se descarta lo absurdo."""
    if monto is None or moneda is None or monto <= 0:
        return None
    moneda = moneda.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", moneda):
        return None
    if moneda in SIN_DECIMALES:
        monto = float(round(monto))
    return Precio(round(monto, 2), moneda)


def recortar(texto: str, limite: int) -> str:
    """Corta en la última palabra completa y añade puntos suspensivos."""
    texto = " ".join(texto.split())
    if len(texto) <= limite:
        return texto
    corte = texto[:limite - 1].rsplit(" ", 1)[0].rstrip(",.;:")
    return corte + "…"


def normalizar_ficha(ficha: Ficha) -> list[str]:
    """Ajusta límites de cada canal y devuelve las advertencias para el comerciante."""
    avisos = []
    for idioma, t in ficha.textos.items():
        t.titulo = recortar(t.titulo, LIMITE_TITULO)
        t.seo_titulo = recortar(t.seo_titulo or t.titulo, LIMITE_TITULO)
        t.seo_descripcion = recortar(t.seo_descripcion or t.descripcion, LIMITE_SEO_DESCRIPCION)
        t.puntos = [p.strip() for p in t.puntos if p.strip()][:6]
        if not t.descripcion.strip():
            avisos.append(f"La descripción en '{idioma}' quedó vacía.")
    ficha.etiquetas = sorted({e.strip().lower() for e in ficha.etiquetas if e.strip()})[:15]
    if ficha.precio is None:
        avisos.append("No se escuchó un precio en el video: hay que escribirlo antes de publicar.")
    if ficha.idioma not in ficha.textos:
        avisos.append("Falta el texto en el idioma del video.")
    return avisos

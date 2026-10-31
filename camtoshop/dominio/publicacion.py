"""Publicación en los canales del comerciante: tienda Shopify, catálogo de Meta e Instagram.

El orden importa: Shopify devuelve la URL del producto y de sus fotos, y el catálogo
de Meta las necesita para que el producto se pueda comprar desde Instagram y Facebook.
Si un canal falla, los demás siguen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from camtoshop.dominio.producto import Ficha

LIMITE_PIE = 2200
LIMITE_ETIQUETAS = 30


@dataclass
class EnTienda:
    url_producto: str
    urls_imagenes: list[str] = field(default_factory=list)
    url_revision: str = ""  # en modo borrador: dónde lo revisa el comerciante antes de publicarlo


@dataclass
class Resultado:
    canal: str
    ok: bool
    url: str = ""
    detalle: str = ""


class Tienda(Protocol):
    def publicar_producto(self, ficha: Ficha, video: Path | None) -> EnTienda: ...


class Catalogo(Protocol):
    def publicar_producto(self, ficha: Ficha, en_tienda: EnTienda | None) -> str: ...


class RedSocial(Protocol):
    def publicar_reel(self, video: Path, pie: str, portada: Path | None) -> str: ...


def pie_de_instagram(ficha: Ficha, gancho: str = "") -> str:
    """Texto del Reel: gancho, beneficios, precio, llamado y etiquetas, dentro de los límites de Instagram."""
    t = ficha.principal
    espanol = ficha.idioma.startswith("es")
    lineas = [gancho or t.titulo, ""]
    lineas += [f"✨ {p}" for p in t.puntos[:3]]
    if ficha.precio:
        lineas += ["", f"{'Precio' if espanol else 'Price'}: {ficha.precio.texto()}"]
    lineas.append("🛒 " + ("Compra en el enlace de la biografía" if espanol else "Shop via the link in bio"))
    etiquetas = []
    for e in ficha.etiquetas + [ficha.marca, ficha.categoria]:
        limpia = "".join(ch for ch in e.title() if ch.isalnum())
        if limpia and f"#{limpia}" not in etiquetas:
            etiquetas.append(f"#{limpia}")
    cuerpo = "\n".join(lineas)
    pie = cuerpo + "\n\n" + " ".join(etiquetas[:LIMITE_ETIQUETAS])
    while len(pie) > LIMITE_PIE and etiquetas:
        etiquetas.pop()
        pie = cuerpo + "\n\n" + " ".join(etiquetas)
    return pie[:LIMITE_PIE]


def canales_de_destino(origen: str, conectados: list[str]) -> list[str]:
    """Un producto que ya vive en la tienda no se vuelve a crear: solo va a las redes."""
    return [c for c in conectados if c == "instagram"] if origen == "shopify" else conectados


def publicar(ficha: Ficha, reel: Path | None, portada: Path | None, canales: list[str],
             tienda: Tienda | None, catalogo: Catalogo | None, red: RedSocial | None,
             gancho: str = "") -> list[Resultado]:
    resultados: list[Resultado] = []
    en_tienda: EnTienda | None = None

    if "shopify" in canales:
        try:
            if tienda is None:
                raise RuntimeError("Shopify no está conectado (faltan SHOPIFY_TIENDA y SHOPIFY_TOKEN).")
            if ficha.precio is None:
                raise ValueError("La ficha no tiene precio.")
            en_tienda = tienda.publicar_producto(ficha, reel)
            resultados.append(Resultado("shopify", True, en_tienda.url_revision or en_tienda.url_producto,
                                        "Borrador: revísalo en Shopify y publícalo cuando quieras."
                                        if en_tienda.url_revision else ""))
        except Exception as e:  # cada canal informa su error sin detener a los demás
            resultados.append(Resultado("shopify", False, detalle=str(e)))

    if "catalogo_meta" in canales:
        try:
            if catalogo is None:
                raise RuntimeError("El catálogo de Meta no está conectado (faltan META_CATALOGO_ID y META_TOKEN).")
            if ficha.precio is None:
                raise ValueError("La ficha no tiene precio.")
            resultados.append(Resultado("catalogo_meta", True, catalogo.publicar_producto(ficha, en_tienda)))
        except Exception as e:
            resultados.append(Resultado("catalogo_meta", False, detalle=str(e)))

    if "instagram" in canales:
        try:
            if red is None:
                raise RuntimeError("Instagram no está conectado (faltan IG_USUARIO_ID y META_TOKEN).")
            if reel is None:
                raise ValueError("No hay Reel para publicar.")
            resultados.append(Resultado("instagram", True, red.publicar_reel(reel, pie_de_instagram(ficha, gancho), portada)))
        except Exception as e:
            resultados.append(Resultado("instagram", False, detalle=str(e)))
    return resultados

"""Catálogo de Meta (Instagram y Facebook Shops, catálogo de WhatsApp) y publicación de Reels en Instagram.

Ambos usan la Graph API con un token de usuario del sistema del Business Manager (META_TOKEN),
con los permisos catalog_management, instagram_basic e instagram_content_publish.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

from camtoshop.dominio.producto import Ficha
from camtoshop.dominio.publicacion import EnTienda

GRAPH = "https://graph.facebook.com/v23.0"


def _revisar(r: requests.Response, que: str) -> dict:
    if not r.ok:
        try:
            mensaje = r.json()["error"]["message"]
        except (ValueError, KeyError):
            mensaje = r.text[:300]
        raise RuntimeError(f"{que}: {mensaje}")
    return r.json()


class CatalogoMeta:
    """Crea o actualiza el producto en un catálogo de Commerce Manager con items_batch."""

    def __init__(self, catalogo_id: str, token: str, url_tienda: str = "", borrador: bool = True):
        # En borrador el producto entra oculto ("staging"): no sale en tiendas ni en anuncios de catálogo.
        self._borrador = borrador
        self._catalogo = catalogo_id
        self._token = token
        self._url_tienda = url_tienda.rstrip("/")

    def publicar_producto(self, ficha: Ficha, en_tienda: EnTienda | None) -> str:
        enlace = en_tienda.url_producto if en_tienda else (
            f"{self._url_tienda}/products/{ficha.identificador}" if self._url_tienda else "")
        imagenes = en_tienda.urls_imagenes if en_tienda else []
        if not enlace or not imagenes:
            raise RuntimeError("El catálogo de Meta necesita la URL pública del producto y de su foto: "
                               "publica primero en Shopify o configura una tienda.")
        t = ficha.principal
        datos = {
            "id": ficha.identificador,
            "title": t.titulo,
            "description": t.descripcion,
            "availability": "in stock",
            "condition": "new",
            "price": f"{ficha.precio.para_api()} {ficha.precio.moneda}",
            "link": enlace,
            "image_link": imagenes[0],
            "additional_image_link": imagenes[1:10],
            "brand": ficha.marca or "Camtoshop",
            "visibility": "staging" if self._borrador else "published",
            "google_product_category": ficha.categoria,
        }
        r = _revisar(requests.post(f"{GRAPH}/{self._catalogo}/items_batch", timeout=60, data={
            "access_token": self._token,
            "item_type": "PRODUCT_ITEM",
            "requests": json.dumps([{"method": "UPDATE", "data": datos}]),
        }), "Catálogo de Meta")
        lote = (r.get("handles") or [""])[0]
        self._esperar_lote(lote)
        return f"https://business.facebook.com/commerce/catalogs/{self._catalogo}/products"

    def _esperar_lote(self, lote: str, intentos: int = 10):
        if not lote:
            return
        for _ in range(intentos):
            r = _revisar(requests.get(f"{GRAPH}/{self._catalogo}/check_batch_request_status", timeout=30,
                                      params={"access_token": self._token, "handle": lote}),
                         "Catálogo de Meta (estado)")
            estado = (r.get("data") or [{}])[0]
            if estado.get("status") == "finished":
                errores = estado.get("errors") or []
                if errores:
                    raise RuntimeError("Catálogo de Meta: " + "; ".join(e.get("message", "") for e in errores))
                return
            time.sleep(2)


class InstagramReels:
    """Publica un Reel con subida reanudable: el archivo va directo a Meta, sin hosting propio."""

    def __init__(self, usuario_id: str, token: str):
        self._usuario = usuario_id
        self._token = token

    def publicar_reel(self, video: Path, pie: str, portada: Path | None) -> str:
        contenedor = _revisar(requests.post(f"{GRAPH}/{self._usuario}/media", timeout=60, data={
            "media_type": "REELS", "upload_type": "resumable", "caption": pie,
            "share_to_feed": "true", "access_token": self._token,
        }), "Instagram (contenedor)")
        datos = video.read_bytes()
        _revisar(requests.post(contenedor["uri"], data=datos, timeout=600, headers={
            "Authorization": f"OAuth {self._token}", "offset": "0", "file_size": str(len(datos)),
        }), "Instagram (subida)")
        self._esperar(contenedor["id"])
        publicado = _revisar(requests.post(f"{GRAPH}/{self._usuario}/media_publish", timeout=60, data={
            "creation_id": contenedor["id"], "access_token": self._token,
        }), "Instagram (publicación)")
        enlace = _revisar(requests.get(f"{GRAPH}/{publicado['id']}", timeout=30, params={
            "fields": "permalink", "access_token": self._token,
        }), "Instagram (enlace)")
        return enlace.get("permalink", "")

    def _esperar(self, contenedor: str, intentos: int = 60):
        for _ in range(intentos):
            r = _revisar(requests.get(f"{GRAPH}/{contenedor}", timeout=30, params={
                "fields": "status_code,status", "access_token": self._token,
            }), "Instagram (estado)")
            if r.get("status_code") == "FINISHED":
                return
            if r.get("status_code") == "ERROR":
                raise RuntimeError(f"Instagram no pudo procesar el video: {r.get('status')}")
            time.sleep(5)
        raise RuntimeError("Instagram tardó demasiado en procesar el video.")

    def metricas(self, media_id: str) -> dict:
        r = _revisar(requests.get(f"{GRAPH}/{media_id}/insights", timeout=30, params={
            "metric": "views,reach,likes,comments,shares,saved", "access_token": self._token,
        }), "Instagram (métricas)")
        return {m["name"]: m["values"][0]["value"] for m in r.get("data", [])}

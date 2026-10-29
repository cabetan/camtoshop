"""Tienda Shopify por la Admin GraphQL API.

Crea el producto con su precio, sube las fotos y el Reel con staged uploads y lo publica en la
tienda en línea. Requiere una app del Dev Dashboard instalada en la tienda, con los permisos
write_products, write_files y write_publications. Se autentica con el client credentials grant
(SHOPIFY_CLIENT_ID y SHOPIFY_CLIENT_SECRET), que da un token de 24 horas; también acepta un
token fijo de app personalizada antigua (SHOPIFY_TOKEN = shpat_…).

Por defecto crea el producto como borrador: no aparece en la tienda hasta que el comerciante
lo revise y lo publique. Así se puede usar con la tienda real de un cliente sin riesgo.
"""

from __future__ import annotations

import html
import mimetypes
import time
from pathlib import Path

import requests

from camtoshop.dominio.producto import Ficha
from camtoshop.dominio.publicacion import EnTienda

VERSION = "2026-10"


def token_por_credenciales(tienda: str, cliente_id: str, secreto: str) -> str:
    """Client credentials grant: la app del Dev Dashboard pide un token de acceso de 24 horas."""
    r = requests.post(f"https://{tienda}/admin/oauth/access_token", timeout=30, data={
        "grant_type": "client_credentials", "client_id": cliente_id, "client_secret": secreto,
    })
    if not r.ok:
        raise RuntimeError(f"Shopify no entregó el token ({r.status_code}): {r.text[:200]}")
    return r.json()["access_token"]


class TiendaShopify:
    def __init__(self, tienda: str, token: str, version: str = VERSION, borrador: bool = True):
        self._tienda = tienda
        self._borrador = borrador
        self._url = f"https://{tienda}/admin/api/{version}/graphql.json"
        self._sesion = requests.Session()
        self._sesion.headers.update({"X-Shopify-Access-Token": token, "Content-Type": "application/json"})

    def _gql(self, consulta: str, variables: dict | None = None) -> dict:
        r = self._sesion.post(self._url, json={"query": consulta, "variables": variables or {}}, timeout=120)
        if not r.ok:
            raise RuntimeError(f"Shopify respondió {r.status_code}: {r.text[:300]}")
        datos = r.json()
        if datos.get("errors"):
            raise RuntimeError(f"Shopify: {datos['errors']}")
        return datos["data"]

    @staticmethod
    def _errores(resultado: dict):
        if resultado.get("userErrors"):
            raise RuntimeError("Shopify: " + "; ".join(e["message"] for e in resultado["userErrors"]))

    # --- Archivos -----------------------------------------------------------

    def _subir(self, ruta: Path, recurso: str) -> str:
        """Staged upload: Shopify da una URL firmada, se sube el archivo y queda una resourceUrl."""
        tipo = mimetypes.guess_type(ruta.name)[0] or "application/octet-stream"
        datos = self._gql("""
            mutation($input: [StagedUploadInput!]!) {
              stagedUploadsCreate(input: $input) {
                stagedTargets { url resourceUrl parameters { name value } }
                userErrors { message }
              }
            }""", {"input": [{"filename": ruta.name, "mimeType": tipo, "resource": recurso,
                              "fileSize": str(ruta.stat().st_size), "httpMethod": "POST"}]})
        self._errores(datos["stagedUploadsCreate"])
        destino = datos["stagedUploadsCreate"]["stagedTargets"][0]
        campos = {p["name"]: p["value"] for p in destino["parameters"]}
        with ruta.open("rb") as archivo:
            r = requests.post(destino["url"], data=campos, files={"file": (ruta.name, archivo, tipo)}, timeout=600)
        if r.status_code >= 300:
            raise RuntimeError(f"Subida a Shopify falló ({r.status_code}): {r.text[:200]}")
        return destino["resourceUrl"]

    # --- Producto -----------------------------------------------------------

    def publicar_producto(self, ficha: Ficha, video: Path | None) -> EnTienda:
        moneda = self._gql("{ shop { currencyCode } }")["shop"]["currencyCode"]
        if ficha.precio.moneda != moneda:
            raise ValueError(f"La tienda vende en {moneda} y el precio de la ficha está en "
                             f"{ficha.precio.moneda}: ajusta el precio antes de publicar.")
        t = ficha.principal
        cuerpo = f"<p>{html.escape(t.descripcion)}</p>"
        if t.puntos:
            cuerpo += "<ul>" + "".join(f"<li>{html.escape(p)}</li>" for p in t.puntos) + "</ul>"

        medios = [{"originalSource": self._subir(Path(r), "IMAGE"), "mediaContentType": "IMAGE",
                   "alt": t.titulo} for r in ficha.imagenes]
        if video:
            medios.append({"originalSource": self._subir(video, "VIDEO"), "mediaContentType": "VIDEO",
                           "alt": t.titulo})

        datos = self._gql("""
            mutation($producto: ProductSetInput!) {
              productSet(input: $producto, synchronous: true) {
                product { id handle onlineStorePreviewUrl }
                userErrors { message }
              }
            }""", {"producto": {
                "title": t.titulo,
                "descriptionHtml": cuerpo,
                "handle": ficha.identificador,
                "vendor": ficha.marca or "Camtoshop",
                "productType": ficha.categoria,
                "tags": ficha.etiquetas,
                "status": "DRAFT" if self._borrador else "ACTIVE",
                "seo": {"title": t.seo_titulo, "description": t.seo_descripcion},
                "productOptions": [{"name": "Title", "values": [{"name": "Default Title"}]}],
                "variants": [{"optionValues": [{"optionName": "Title", "name": "Default Title"}],
                              "price": ficha.precio.para_api()}],
            }})
        self._errores(datos["productSet"])
        producto = datos["productSet"]["product"]

        if medios:
            r = self._gql("""
                mutation($id: ID!, $medios: [CreateMediaInput!]!) {
                  productCreateMedia(productId: $id, media: $medios) { mediaUserErrors { message } }
                }""", {"id": producto["id"], "medios": medios})
            if r["productCreateMedia"]["mediaUserErrors"]:
                raise RuntimeError("Shopify (medios): " + "; ".join(
                    e["message"] for e in r["productCreateMedia"]["mediaUserErrors"]))
        imagenes = self._urls_imagenes(producto["id"])
        if self._borrador:
            numero = producto["id"].rsplit("/", 1)[-1]
            return EnTienda(self._url_publica(producto), imagenes, f"https://{self._tienda}/admin/products/{numero}")
        self._publicar_en_tienda_online(producto["id"])
        return EnTienda(self._url_publica(producto), imagenes)

    def _publicar_en_tienda_online(self, producto_id: str):
        canales = self._gql("{ publications(first: 20) { nodes { id name } } }")["publications"]["nodes"]
        tienda = [c["id"] for c in canales if c["name"] in ("Online Store", "Tienda online")]
        if tienda:
            r = self._gql("""
                mutation($id: ID!, $en: [PublicationInput!]!) {
                  publishablePublish(id: $id, input: $en) { userErrors { message } }
                }""", {"id": producto_id, "en": [{"publicationId": tienda[0]}]})
            self._errores(r["publishablePublish"])

    def _url_publica(self, producto: dict) -> str:
        dominio = self._gql("{ shop { primaryDomain { url } } }")["shop"]["primaryDomain"]["url"]
        return f"{dominio}/products/{producto['handle']}"

    def _urls_imagenes(self, producto_id: str, intentos: int = 10) -> list[str]:
        """Las imágenes tardan unos segundos en procesarse; el catálogo de Meta necesita sus URLs."""
        for _ in range(intentos):
            nodos = self._gql("""
                query($id: ID!) { product(id: $id) { media(first: 10) { nodes {
                  ... on MediaImage { status image { url } } } } } }""", {"id": producto_id})
            imagenes = [n for n in nodos["product"]["media"]["nodes"] if n]
            listas = [n["image"]["url"] for n in imagenes if n.get("status") == "READY" and n.get("image")]
            if imagenes and len(listas) == len(imagenes):
                return listas
            time.sleep(3)
        return listas

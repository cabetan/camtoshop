"""Capa HTTP de Camtoshop: rutas delgadas que validan la entrada y llaman al servicio."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import hmac
import os
import threading
import time

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from camtoshop.adaptadores.config import secreto
from camtoshop.adaptadores.meta_oauth import MetaOAuth
from camtoshop.adaptadores.shopify import ConectorShopify
from camtoshop.adaptadores.whatsapp import firma_valida
from camtoshop.aplicacion.agente_whatsapp import AgenteWhatsApp
from camtoshop.aplicacion.servicio import Proyecto, Servicio
from camtoshop.dominio.direccion import LOOKS
from camtoshop.dominio.portal import Portal
from camtoshop.web.portal import rutas_del_portal

ESTATICO = Path(__file__).parent / "estatico"
FORMATOS_VIDEO = {".mov", ".mp4", ".m4v"}
FORMATOS_FOTO = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
FORMATOS_VOZ = {".m4a", ".mp3", ".ogg", ".opus", ".wav", ".aac"}
MAX_FOTOS = 8

app = FastAPI(title="Camtoshop")
servicio = Servicio()
agente = AgenteWhatsApp(servicio)
if not os.environ.get("K_SERVICE"):  # en Cloud Run la instancia se apaga: lo dispara Cloud Scheduler
    agente.diario.arrancar()
META_APP_ID = "2033143300693121"
portal = Portal(servicio.repo_comercios, MetaOAuth(META_APP_ID, secreto("META_APP_SECRET") or ""), ConectorShopify(),
                time.time)
app.include_router(rutas_del_portal(portal, servicio.repo_comercios, META_APP_ID, servicio))
servicio.recuperar()  # antes de atender, para no tocar lo que esta instancia cree
RUTAS_PUBLICAS = ("/webhook/", "/portal", "/api/portal", "/estatico/")


def llega_de_internet(cabeceras) -> bool:
    return "cf-connected-ip" in cabeceras or "x-forwarded-for" in cabeceras


@app.middleware("http")
async def solo_lo_publico(request: Request, siguiente):
    """Por el túnel solo se ve el portal y el webhook: el resto puede gastar créditos y publicar."""
    if llega_de_internet(request.headers) and request.url.path == "/":
        respuesta = FileResponse(ESTATICO / "inicio.html", headers={"Cache-Control": "no-cache"})
    elif llega_de_internet(request.headers) and not request.url.path.startswith(RUTAS_PUBLICAS):
        respuesta = JSONResponse({"detail": "Not found"}, 404)
    else:
        respuesta = await siguiente(request)
    respuesta.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
                              "Strict-Transport-Security": "max-age=31536000"})
    return respuesta


def _proyecto(identificador: str) -> Proyecto:
    pr = servicio.obtener(identificador)
    if pr is None:
        raise HTTPException(404, "Proyecto no encontrado")
    return pr


class PedidoLook(BaseModel):
    look: Literal["directo", "anuncio", "premium"]


class PedidoCambio(BaseModel):
    texto: str = Field(min_length=3, max_length=300)


class CambiosFicha(BaseModel):
    idioma: str | None = None
    titulo: str | None = Field(default=None, max_length=200)
    descripcion: str | None = Field(default=None, max_length=5000)
    puntos: list[str] | None = None
    precio: float | None = Field(default=None, gt=0)
    moneda: str | None = Field(default=None, pattern=r"^[A-Za-z]{3}$")


class PedidoPublicar(BaseModel):
    canales: list[Literal["shopify", "catalogo_meta", "instagram"]] = Field(min_length=1)


@app.post("/api/proyectos")
def crear(archivos: list[UploadFile] = File(...), texto: str = Form("", max_length=1500)):
    """Un video, o de 1 a 8 fotos con un mensaje y, si se quiere, una nota de voz."""
    def tipo(a: UploadFile) -> str:
        ext = Path(a.filename or "").suffix.lower()
        return "video" if ext in FORMATOS_VIDEO else "foto" if ext in FORMATOS_FOTO else "voz" if ext in FORMATOS_VOZ else ""
    por_tipo: dict[str, list[UploadFile]] = {}
    for a in archivos:
        por_tipo.setdefault(tipo(a), []).append(a)
    if "" in por_tipo:
        raise HTTPException(400, "Formato no soportado: sube un video, fotos (jpg, png) o una nota de voz")
    if por_tipo.get("video"):
        video = por_tipo["video"][0]
        return {"id": servicio.crear(video.filename, video.file).id}
    fotos = por_tipo.get("foto", [])
    if not 1 <= len(fotos) <= MAX_FOTOS:
        raise HTTPException(400, f"Sube un video o entre 1 y {MAX_FOTOS} fotos del producto")
    voz = por_tipo.get("voz", [None])[0]
    return {"id": servicio.crear_desde_fotos([(f.filename, f.file) for f in fotos], texto.strip(),
                                             (voz.filename, voz.file) if voz else None).id}


class PedidoTienda(BaseModel):
    handles: list[str] = Field(min_length=1, max_length=6)


@app.get("/api/tienda/productos")
def productos_de_tienda():
    try:
        return servicio.productos_de_tienda()
    except RuntimeError as e:
        raise HTTPException(409, str(e))


@app.post("/api/tienda/reels")
def reels_desde_tienda(pedido: PedidoTienda):
    return {"ids": servicio.reels_desde_tienda(pedido.handles)}


# --- WhatsApp -------------------------------------------------------------------

@app.get("/webhook/whatsapp")
def verificar_webhook(request: Request):
    """Meta confirma la URL del webhook con el token de verificación que configuramos."""
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == secreto("WA_VERIFICACION"):
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(403, "Token de verificación inválido")


@app.post("/webhook/whatsapp")
async def webhook_whatsapp(request: Request):
    cuerpo = await request.body()
    if not firma_valida(cuerpo, request.headers.get("x-hub-signature-256", ""), secreto("META_APP_SECRET") or ""):
        raise HTTPException(403, "Firma inválida")
    # Meta espera un 200 enseguida: el trabajo se hace aparte.
    threading.Thread(target=agente.recibir, args=(await request.json(),), daemon=True).start()
    return {"ok": True}


@app.post("/webhook/diario")
def propuesta_diaria(request: Request):
    """Cloud Scheduler llama cada mañana. Corre aparte para responder enseguida."""
    clave = secreto("WA_VERIFICACION") or ""
    if not clave or not hmac.compare_digest(request.headers.get("x-camtoshop-clave", ""), clave):
        raise HTTPException(403, "Clave inválida")
    threading.Thread(target=agente.diario.revisar, daemon=True).start()
    return {"ok": True}


@app.get("/api/proyectos")
def listar():
    return servicio.listar()


@app.get("/api/proyectos/{identificador}")
def estado(identificador: str):
    pr = _proyecto(identificador)
    return {**pr.estado, "canales": servicio.canales(),
            "pie": servicio.pie(pr) if pr.estado.get("ficha") else "",
            "looks": {k: {"nombre": k} for k in LOOKS}}


@app.get("/api/proyectos/{identificador}/archivos/{ruta:path}")
def archivo(identificador: str, ruta: str):
    pr = _proyecto(identificador)
    destino = (pr.carpeta / ruta).resolve()
    if pr.carpeta.resolve() not in destino.parents or not destino.is_file():
        raise HTTPException(404, "Archivo no encontrado")
    return FileResponse(destino)


@app.post("/api/proyectos/{identificador}/look")
def look(identificador: str, pedido: PedidoLook):
    servicio.cambiar_look(_proyecto(identificador), pedido.look)
    return {"ok": True}


@app.post("/api/proyectos/{identificador}/cambio")
def cambio(identificador: str, pedido: PedidoCambio):
    servicio.pedir_cambio(_proyecto(identificador), pedido.texto)
    return {"ok": True}


@app.post("/api/proyectos/{identificador}/reintentar")
def reintentar(identificador: str):
    pr = _proyecto(identificador)
    if pr.estado.get("fase") != "error":
        raise HTTPException(409, "Solo se reintenta un proyecto con error")
    servicio.reintentar(pr)
    return {"ok": True}


@app.patch("/api/proyectos/{identificador}/ficha")
def ficha(identificador: str, cambios: CambiosFicha):
    pr = _proyecto(identificador)
    if not pr.estado.get("ficha"):
        raise HTTPException(409, "La ficha todavía no está lista")
    return servicio.editar_ficha(pr, cambios.model_dump(exclude_none=True))


@app.post("/api/proyectos/{identificador}/publicar")
def publicar(identificador: str, pedido: PedidoPublicar):
    pr = _proyecto(identificador)
    if pr.estado.get("fase") != "listo":
        raise HTTPException(409, "El proyecto todavía se está procesando")
    return servicio.publicar(pr, pedido.canales)


@app.get("/api/canales")
def canales():
    return servicio.canales()


@app.get("/")
def inicio():
    # Sin caché: la interfaz cambia seguido y el navegador no debe quedarse con una versión vieja.
    return FileResponse(ESTATICO / "index.html", headers={"Cache-Control": "no-cache"})


app.mount("/estatico", StaticFiles(directory=ESTATICO), name="estatico")

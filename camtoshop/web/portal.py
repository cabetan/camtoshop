"""Rutas del portal de comercios: delgadas, solo validan la entrada y llaman al dominio."""

from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from camtoshop.adaptadores.config import secreto
from camtoshop.adaptadores.meta_oauth import url_de_login
from camtoshop.adaptadores.sesion import firmar, verificar
from camtoshop.dominio.comercio import Comercio
from camtoshop.dominio.portal import ErrorPortal, Portal

PAGINA = Path(__file__).parent / "estatico" / "portal.html"
COOKIE = "camtoshop_sesion"
DURACION = 14 * 24 * 3600
CONFIG_LOGIN = "1845619373423690"
LINEA = "15550321707"


class Registro(BaseModel):
    nombre: str = Field(max_length=120)
    correo: str = Field(max_length=200)
    clave: str = Field(max_length=200)
    idioma: str = Field(default="es", pattern="^(es|en)$")


class Entrada(BaseModel):
    correo: str = Field(max_length=200)
    clave: str = Field(max_length=200)


class Eleccion(BaseModel):
    pagina_id: str = Field(max_length=40)


class Shopify(BaseModel):
    tienda: str = Field(max_length=200)
    token: str = Field(max_length=300)


def _clave() -> str:
    return secreto("CAMTOSHOP_CLAVE") or ""


def _origen(request: Request) -> str:
    esquema = request.headers.get("x-forwarded-proto", request.url.scheme)
    return f"{esquema}://{request.headers.get('host', request.url.netloc)}"


def rutas_del_portal(portal: Portal, repo, app_id: str) -> APIRouter:
    r = APIRouter()

    def comercio_actual(request: Request) -> Comercio:
        comercio_id = verificar(_clave(), "sesion", request.cookies.get(COOKIE, ""), time.time())
        comercio = repo.obtener(comercio_id) if comercio_id else None
        if comercio is None:
            raise HTTPException(401, "Sign in first")
        return comercio

    def con_sesion(c: Comercio, request: Request, respuesta):
        respuesta.set_cookie(COOKIE, firmar(_clave(), "sesion", c.id, time.time() + DURACION), max_age=DURACION,
                             httponly=True, samesite="lax", secure=_origen(request).startswith("https"))
        return respuesta

    def intentar(accion, *args):
        try:
            return accion(*args)
        except ErrorPortal as e:
            raise HTTPException(400, str(e))

    @r.get("/portal")
    def pagina():
        return FileResponse(PAGINA, headers={"Cache-Control": "no-cache"})

    @r.post("/api/portal/registro")
    def registro(datos: Registro, request: Request):
        c = intentar(portal.registrar, datos.nombre, datos.correo, datos.clave, datos.idioma)
        return con_sesion(c, request, RedirectResponse("/api/portal/yo", 303))

    @r.post("/api/portal/entrar")
    def entrar(datos: Entrada, request: Request):
        c = intentar(portal.entrar, datos.correo, datos.clave)
        return con_sesion(c, request, RedirectResponse("/api/portal/yo", 303))

    @r.post("/api/portal/salir")
    def salir():
        respuesta = RedirectResponse("/portal", 303)
        respuesta.delete_cookie(COOKIE)
        return respuesta

    @r.get("/api/portal/yo")
    def yo(c: Comercio = Depends(comercio_actual)):
        return portal.estado(c)

    @r.post("/api/portal/codigo")
    def codigo(c: Comercio = Depends(comercio_actual)):
        texto = portal.codigo_de_celular(c)
        return {"codigo": texto, "enlace": f"https://wa.me/{LINEA}?text={quote(texto)}"}

    @r.delete("/api/portal/celulares/{celular}")
    def quitar_celular(celular: str, c: Comercio = Depends(comercio_actual)):
        portal.quitar_celular(c, celular)
        return {"ok": True}

    @r.get("/portal/meta/iniciar")
    def meta_iniciar(request: Request, c: Comercio = Depends(comercio_actual)):
        estado = firmar(_clave(), "meta", c.id, time.time() + 600)
        return RedirectResponse(url_de_login(app_id, CONFIG_LOGIN, _origen(request) + "/portal/meta/volver", estado))

    @r.get("/portal/meta/volver")
    def meta_volver(request: Request, code: str = "", state: str = ""):
        # El state firmado debe ser del mismo comercio que tiene la sesión abierta.
        c = comercio_actual(request)
        if verificar(_clave(), "meta", state, time.time()) != c.id or not code:
            return RedirectResponse("/portal?error=meta", 303)
        try:
            portal.conectar_meta(c, code, _origen(request) + "/portal/meta/volver")
        except ErrorPortal as e:
            return RedirectResponse(f"/portal?error={quote(str(e))}", 303)
        return RedirectResponse("/portal", 303)

    @r.post("/api/portal/cuenta")
    def elegir(datos: Eleccion, c: Comercio = Depends(comercio_actual)):
        intentar(portal.elegir_cuenta, c, datos.pagina_id)
        return portal.estado(c)

    @r.post("/api/portal/shopify")
    def shopify(datos: Shopify, c: Comercio = Depends(comercio_actual)):
        intentar(portal.conectar_shopify, c, datos.tienda, datos.token)
        return portal.estado(c)

    @r.delete("/api/portal/conexiones/{canal}")
    def desconectar(canal: str, c: Comercio = Depends(comercio_actual)):
        intentar(portal.desconectar, c, canal)
        return portal.estado(c)

    return r

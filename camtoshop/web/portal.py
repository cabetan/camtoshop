"""Rutas del portal de comercios: delgadas, solo validan la entrada y llaman al dominio."""

from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import quote

from collections import defaultdict

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

from camtoshop.adaptadores.archivos_marca import guardar_logo, guardar_pista
from camtoshop.adaptadores.config import secreto
from camtoshop.adaptadores.meta_oauth import url_de_login
from camtoshop.adaptadores.sesion import firmar, verificar
from camtoshop.dominio.agente_diario import texto_de_propuesta
from camtoshop.dominio.comercio import Comercio, registrar_uso
from camtoshop.dominio.marca import MUSICAS, validar_marca
from camtoshop.dominio.portal import ErrorPortal, Portal

PAGINA = Path(__file__).parent / "estatico" / "portal.html"
COOKIE = "camtoshop_sesion"
DURACION = 14 * 24 * 3600
CONFIG_LOGIN = "1845619373423690"
LINEA = "15550321707"
MAX_DIARIO = 60  # Reels al día entre todos: protege los créditos mientras el registro esté abierto
MAX_FOTOS = 8
MAX_FOTO = 10 * 1024 * 1024
FOTOS = {".jpg", ".jpeg", ".png", ".webp"}
PISTAS = Path(__file__).parents[1] / "assets" / "musica"


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


class MarcaEntrada(BaseModel):
    estilo: str = Field(max_length=20)
    fuente: str = Field(max_length=20)
    primario: str = Field(max_length=7)
    secundario: str = Field(max_length=7)
    musica: str = Field(max_length=20)


class EstiloDeReel(BaseModel):
    """Lo que cambia solo en este Reel. Lo que no llega se toma del kit de marca."""
    estilo: str | None = Field(default=None, max_length=20)
    fuente: str | None = Field(default=None, max_length=20)
    primario: str | None = Field(default=None, max_length=7)
    secundario: str | None = Field(default=None, max_length=7)
    musica: str | None = Field(default=None, max_length=20)


class Pedido(BaseModel):
    producto: str = Field(max_length=80)


def _clave() -> str:
    return secreto("CAMTOSHOP_CLAVE") or ""


def _origen(request: Request) -> str:
    esquema = request.headers.get("x-forwarded-proto", request.url.scheme)
    return f"{esquema}://{request.headers.get('host', request.url.netloc)}"


def rutas_del_portal(portal: Portal, repo, app_id: str, servicio) -> APIRouter:
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

    intentos: defaultdict[str, list[float]] = defaultdict(list)

    def limitar(request: Request, que: str, maximo: int, ventana: int = 3600):
        ip = request.headers.get("x-forwarded-for", "local").split(",")[0].strip()
        ahora = time.time()
        recientes = intentos[f"{que}:{ip}"] = [t for t in intentos[f"{que}:{ip}"] if ahora - t < ventana]
        if len(recientes) >= maximo:
            raise HTTPException(429, "Too many attempts. Try again later.")
        recientes.append(ahora)

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
        limitar(request, "registro", 5)
        c = intentar(portal.registrar, datos.nombre, datos.correo, datos.clave, datos.idioma)
        return con_sesion(c, request, RedirectResponse("/api/portal/yo", 303))

    @r.post("/api/portal/entrar")
    def entrar(datos: Entrada, request: Request):
        limitar(request, "entrar", 20, 900)
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
        try:
            c = comercio_actual(request)
        except HTTPException:
            return RedirectResponse("/portal", 303)
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

    # --- Marca --------------------------------------------------------------------

    @r.post("/api/portal/marca")
    def marca(datos: MarcaEntrada, c: Comercio = Depends(comercio_actual)):
        intentar(portal.guardar_marca, c, datos.model_dump())
        return portal.estado(c)

    @r.post("/api/portal/marca/logo")
    def subir_logo(archivo: UploadFile = File(...), c: Comercio = Depends(comercio_actual)):
        try:
            color = guardar_logo(archivo.file.read(), repo.archivo(c.id, "logo.png"))
        except ValueError as e:
            raise HTTPException(400, str(e))
        portal.registrar_logo(c, True)
        return {**portal.estado(c), "color_sugerido": color}

    @r.delete("/api/portal/marca/logo")
    def quitar_logo(c: Comercio = Depends(comercio_actual)):
        portal.registrar_logo(c, False)
        return portal.estado(c)

    @r.get("/portal/marca/logo")
    def ver_logo(c: Comercio = Depends(comercio_actual)):
        ruta = repo.archivo(c.id, "logo.png")
        if not c.marca.logo or not ruta.exists():
            raise HTTPException(404, "No logo")
        return FileResponse(ruta, headers={"Cache-Control": "no-cache"})

    @r.post("/api/portal/marca/musica")
    def subir_pista(archivo: UploadFile = File(...), c: Comercio = Depends(comercio_actual)):
        try:
            guardar_pista(archivo.file.read(), repo.archivo(c.id, "musica.m4a"))
        except ValueError as e:
            raise HTTPException(400, str(e))
        portal.registrar_pista(c, True)
        return portal.estado(c)

    @r.get("/portal/musica/{pista}")
    def oir_pista(pista: str, c: Comercio = Depends(comercio_actual)):
        ruta = repo.archivo(c.id, "musica.m4a") if pista == "propia" else PISTAS / f"{pista}.m4a"
        if pista not in MUSICAS or not ruta.exists():
            raise HTTPException(404, "No track")
        return FileResponse(ruta, media_type="audio/mp4")

    # --- Reels ----------------------------------------------------------------------

    def reel_propio(reel_id: str, c: Comercio):
        pr = servicio.obtener(reel_id) if reel_id.replace("-", "").isalnum() else None
        if pr is None or pr.estado.get("comercio_id") != c.id:
            raise HTTPException(404, "Reel not found")
        return pr

    @r.get("/api/portal/reels")
    def reels(c: Comercio = Depends(comercio_actual)):
        return servicio.reels_de(c.id)

    @r.post("/api/portal/reels")
    def crear_reel(fotos: list[UploadFile] = File(...), texto: str = Form("", max_length=500),
                   c: Comercio = Depends(comercio_actual)):
        """El mismo Reel que por WhatsApp, para quien todavía no tiene su número autorizado."""
        if not 1 <= len(fotos) <= MAX_FOTOS:
            raise HTTPException(400, f"Upload 1 to {MAX_FOTOS} photos of one product")
        if not texto.strip():
            raise HTTPException(400, "Say what it is and what it costs")
        if any(Path(f.filename or "").suffix.lower() not in FOTOS or (f.size or 0) > MAX_FOTO for f in fotos):
            raise HTTPException(400, "Use JPG, PNG or WEBP photos under 10 MB")
        if servicio.reels_de_hoy() >= MAX_DIARIO:
            raise HTTPException(429, "Camtoshop reached today's limit. Try again tomorrow.")
        if not registrar_uso(c, time.strftime("%Y-%m-%d")):
            raise HTTPException(429, "You reached today's limit of Reels")
        repo.guardar(c)
        pr = servicio.crear_desde_fotos([(f.filename, f.file) for f in fotos], texto.strip(), None, origen="portal",
                                        extra={"comercio_id": c.id})
        return {"id": pr.id}

    @r.get("/api/portal/propuesta")
    def propuesta(idioma: str = "es", excluir: str = "", c: Comercio = Depends(comercio_actual)):
        p = servicio.propuesta_para(c, tuple(x for x in excluir.split(",") if x)[:30])
        if p is None:
            return {}
        return {"producto": p.producto.handle, "texto": texto_de_propuesta(p, "en" if idioma == "en" else "es")}

    @r.post("/api/portal/propuesta")
    def hacer_propuesta(datos: Pedido, c: Comercio = Depends(comercio_actual)):
        p = servicio.propuesta_para(c)
        pedido = p.pedido if p else ""
        if servicio.reels_de_hoy() >= MAX_DIARIO:
            raise HTTPException(429, "Camtoshop reached today's limit. Try again tomorrow.")
        dia = time.strftime("%Y-%m-%d")
        if not registrar_uso(c, dia):
            raise HTTPException(429, "You reached today's limit of Reels")
        try:
            pr = servicio.reel_de_producto(c, datos.producto, "", pedido)
        except RuntimeError:
            raise HTTPException(400, "That product isn't available")
        c.promovidos[datos.producto] = dia
        repo.guardar(c)
        return {"id": pr.id}

    @r.post("/api/portal/reels/{reel_id}/publicar")
    def publicar_reel(reel_id: str, c: Comercio = Depends(comercio_actual)):
        pr = reel_propio(reel_id, c)
        if pr.estado.get("fase") != "listo":
            raise HTTPException(400, "This Reel is still rendering")
        if not c.conexiones.instagram_id:
            raise HTTPException(400, "Connect Instagram first")
        resultados = servicio.publicar_en_canales(pr, c)
        if not any(x["ok"] for x in resultados):
            raise HTTPException(400, resultados[0]["detalle"] if resultados else "Connect Instagram first")
        return {"resultados": resultados}

    @r.get("/portal/reels/{reel_id}/video")
    def video_de_reel(reel_id: str, c: Comercio = Depends(comercio_actual)):
        pr = reel_propio(reel_id, c)
        if "fotos" not in pr.estado.get("reels", {}):
            raise HTTPException(404, "Still rendering")
        return FileResponse(servicio.archivo_de_reel(pr), media_type="video/mp4")

    @r.get("/portal/reels/{reel_id}/producto")
    def producto_de_reel(reel_id: str, c: Comercio = Depends(comercio_actual)):
        return FileResponse(servicio.recorte_de(reel_propio(reel_id, c)))

    @r.post("/api/portal/reels/{reel_id}/estilo")
    def estilo_de_reel(reel_id: str, datos: EstiloDeReel, c: Comercio = Depends(comercio_actual)):
        pr = reel_propio(reel_id, c)
        if pr.estado.get("fase") == "procesando" or "fotos" not in pr.estado.get("reels", {}):
            raise HTTPException(400, "This Reel is still rendering")
        celular = pr.estado.get("celular")
        if celular and repo.chat(celular).estado == "generando":
            raise HTTPException(400, "Another Reel is rendering. Try again in a few minutes.")
        cambios = datos.model_dump(exclude_none=True)
        probar = {"estilo": c.marca.estilo, "fuente": c.marca.fuente, "primario": c.marca.primario,
                  "secundario": c.marca.secundario, "musica": c.marca.musica, **cambios}
        try:
            validar_marca({**probar, "musica_propia": c.marca.musica_propia})
        except ValueError as e:
            raise HTTPException(400, str(e))
        servicio.reestilizar(pr, cambios)
        return {"ok": True}

    @r.post("/api/portal/shopify")
    def shopify(datos: Shopify, c: Comercio = Depends(comercio_actual)):
        intentar(portal.conectar_shopify, c, datos.tienda, datos.token)
        return portal.estado(c)

    @r.delete("/api/portal/conexiones/{canal}")
    def desconectar(canal: str, c: Comercio = Depends(comercio_actual)):
        intentar(portal.desconectar, c, canal)
        return portal.estado(c)

    return r

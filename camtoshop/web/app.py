"""Capa HTTP de Camtoshop: rutas delgadas que validan la entrada y llaman al servicio."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from camtoshop.aplicacion.servicio import Proyecto, Servicio
from camtoshop.dominio.direccion import LOOKS

ESTATICO = Path(__file__).parent / "estatico"
FORMATOS_VIDEO = {".mov", ".mp4", ".m4v"}

app = FastAPI(title="Camtoshop")
servicio = Servicio()


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
def crear(video: UploadFile):
    if Path(video.filename or "").suffix.lower() not in FORMATOS_VIDEO:
        raise HTTPException(400, "Sube un video .mov o .mp4")
    return {"id": servicio.crear(video.filename, video.file).id}


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

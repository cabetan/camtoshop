"""Agente de WhatsApp: recibe los mensajes de la línea, decide con el dominio y ejecuta.

Cada celular se atiende de a un mensaje a la vez (las fotos llegan en ráfaga) y los mensajes
repetidos de Meta se ignoran por su id. Cuando un Reel termina, se manda con sus botones.
"""

from __future__ import annotations

import hashlib
import threading
import time
import traceback
from collections import OrderedDict, defaultdict

from camtoshop.adaptadores.config import secreto
from camtoshop.adaptadores.whatsapp import ClienteWhatsApp, mensajes_del_webhook
from camtoshop.aplicacion.servicio import Proyecto, Servicio
from camtoshop.dominio.comercio import comercio_de, vincular
from camtoshop.dominio.conversacion import (
    CrearDesdeFotos, CrearDesdeVideo, Mensaje, PedirCambio, Publicar, Responder, atender, botones, fallo,
    listo_para_aprobar, t,
)

NOMBRES_CANAL = {"shopify": "Shopify", "catalogo_meta": "Catálogo de Meta", "instagram": "Instagram"}


def version_de(pr: Proyecto) -> str:
    archivo = pr.estado["reels"][pr.estado["look"]]["archivo"]
    return hashlib.sha1(f"{pr.id}/{archivo}".encode()).hexdigest()[:10]


class AgenteWhatsApp:
    def __init__(self, servicio: Servicio, portal: str = ""):
        self._servicio = servicio
        self._repo = servicio.repo_comercios
        self._portal = portal or secreto("CAMTOSHOP_URL_PUBLICA") or "camtoshop.app"
        self._vistos: OrderedDict[str, None] = OrderedDict()
        self._cerrojos: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)
        self._wa = None
        Proyecto.al_terminar = self.proyecto_terminado

    @property
    def wa(self) -> ClienteWhatsApp:
        if self._wa is None:
            self._wa = ClienteWhatsApp(secreto("WA_TELEFONO_ID"), secreto("WA_TOKEN"))
        return self._wa

    # --- Entrada -------------------------------------------------------------------

    def recibir(self, cuerpo: dict):
        for celular, wamid, _, msg in mensajes_del_webhook(cuerpo):
            if wamid in self._vistos:
                continue
            self._vistos[wamid] = None
            while len(self._vistos) > 2000:
                self._vistos.popitem(last=False)
            with self._cerrojos[celular]:
                try:
                    self._atender(celular, msg)
                except Exception:  # un mensaje que falla no tumba el webhook
                    traceback.print_exc()

    def _atender(self, celular: str, msg: Mensaje):
        comercios = self._repo.todos()
        vinculado = vincular(comercios, celular, msg.texto, time.time())  # también si el número ya era de otro
        if vinculado:
            for c in comercios:
                self._repo.guardar(c)
            self.wa.texto(celular, t(vinculado, "vinculado", nombre=vinculado.nombre))
            return
        comercio = comercio_de(celular, comercios)
        if comercio is None:
            self.wa.texto(celular, t(None, "desconocido", portal=self._portal))
            return
        chat = self._repo.chat(celular)
        acciones = atender(chat, msg, comercio, time.strftime("%Y-%m-%d"))
        self._repo.guardar(comercio)
        self._repo.guardar_chat(chat)
        for accion in acciones:
            self._ejecutar(accion, celular, comercio)

    def _ejecutar(self, accion, celular: str, comercio):
        if isinstance(accion, Responder):
            self.wa.texto(celular, accion.texto)
        elif isinstance(accion, CrearDesdeFotos):
            fotos = [self.wa.descargar(m) for m in accion.fotos]
            voz = self.wa.descargar(accion.voz) if accion.voz else None
            pr = self._servicio.crear_desde_fotos([(f.name, f.open("rb")) for f in fotos], accion.texto,
                                                  (voz.name, voz.open("rb")) if voz else None, origen="whatsapp",
                                                  extra={"comercio_id": comercio.id, "celular": celular})
            self._anotar(celular, pr)
        elif isinstance(accion, CrearDesdeVideo):
            video = self.wa.descargar(accion.video)
            pr = self._servicio.crear(video.name, video.open("rb"),
                                      extra={"comercio_id": comercio.id, "celular": celular})
            self._anotar(celular, pr)
        elif isinstance(accion, Publicar):
            pr = self._servicio.obtener(accion.proyecto)
            canales = [k for k, v in self._servicio.canales_de(comercio).items() if v]
            resultados = self._servicio.publicar(pr, canales, comercio)
            self.wa.texto(celular, self._resumen(resultados))
        elif isinstance(accion, PedirCambio):
            pr = self._servicio.obtener(accion.proyecto)
            self._servicio.pedir_cambio(pr, accion.pedido)

    def _anotar(self, celular: str, pr: Proyecto):
        chat = self._repo.chat(celular)
        chat.proyecto = pr.id
        self._repo.guardar_chat(chat)

    @staticmethod
    def _resumen(resultados: list[dict]) -> str:
        lineas = []
        for r in resultados:
            nombre = NOMBRES_CANAL.get(r["canal"], r["canal"])
            if r["ok"]:
                lineas.append(f"✅ {nombre}" + (f": {r['url']}" if r.get("url") else "") +
                              (f"\n   {r['detalle']}" if r.get("detalle") else ""))
            else:
                lineas.append(f"⚠️ {nombre}: {r['detalle']}")
        return "\n".join(lineas) or "No hay canales conectados: conéctalos en el portal."

    # --- Salida: el Reel terminó ------------------------------------------------------

    def proyecto_terminado(self, pr: Proyecto):
        celular = pr.estado.get("celular")
        if not celular:
            return
        with self._cerrojos[celular]:
            chat = self._repo.chat(celular)
            comercio = self._repo.obtener(pr.estado.get("comercio_id", ""))
            try:
                if pr.estado["fase"] == "error":
                    fallo(chat)
                    self.wa.texto(celular, t(comercio, "error", error=pr.estado.get("error", "")[:200]))
                    return
                version = version_de(pr)
                listo_para_aprobar(chat, pr.id, version)
                reel = pr.ruta(pr.estado["reels"][pr.estado["look"]]["archivo"])
                cuerpo = t(comercio, "aprobar", pie=self._servicio.pie(pr))
                self.wa.video_con_botones(celular, reel, cuerpo, botones(comercio, pr.id, version))
            except Exception:
                traceback.print_exc()
                fallo(chat)
            finally:
                self._repo.guardar_chat(chat)

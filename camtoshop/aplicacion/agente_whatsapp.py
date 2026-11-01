"""Agente de WhatsApp: recibe los mensajes de la línea, decide con el dominio y ejecuta.

Cada celular se atiende de a un mensaje a la vez (las fotos llegan en ráfaga) y los mensajes
repetidos de Meta se ignoran por su id. Cuando un Reel termina, se manda con sus botones.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
import traceback
from collections import OrderedDict, defaultdict

from camtoshop.adaptadores.config import secreto
from camtoshop.adaptadores.whatsapp import ClienteWhatsApp, mensajes_del_webhook
from camtoshop.aplicacion.agente_diario import AgenteDiario
from camtoshop.aplicacion.servicio import Proyecto, Servicio
from camtoshop.dominio.comercio import codigo_en, comercio_de, vincular
from camtoshop.dominio.publicacion import canales_de_destino
from camtoshop.dominio.conversacion import (
    Chat, CrearDesdeFotos, CrearDesdeProducto, CrearDesdeVideo, Mensaje, OtraPropuesta, PedirCambio, Publicar, Responder,
    atender, botones, fallo, listo_para_aprobar, t,
)

MAX_GENERANDO = 15 * 60  # segundos: más que esto significa que el proceso murió
MAX_INTENTOS = 5  # códigos fallidos por celular y hora
NOMBRES_CANAL = {"shopify": "Shopify", "catalogo_meta": "Catálogo de Meta", "instagram": "Instagram"}


def version_de(pr: Proyecto) -> str:
    archivo = pr.estado["reels"][pr.estado["look"]]["archivo"]
    return hashlib.sha1(f"{pr.id}/{archivo}".encode()).hexdigest()[:10]


class AgenteWhatsApp:
    def __init__(self, servicio: Servicio, portal: str = ""):
        self._servicio = servicio
        self._repo = servicio.repo_comercios
        self._portal = portal or secreto("CAMTOSHOP_URL_PUBLICA") or "camtoshop.com/portal"
        self._vistos: OrderedDict[str, None] = OrderedDict()
        self._cerrojos: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)
        self._wa = None
        self._fallidos: defaultdict[str, list[float]] = defaultdict(list)
        self.diario = AgenteDiario(servicio, lambda: self.wa)
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
        ahora = time.time()
        recientes = self._fallidos[celular] = [x for x in self._fallidos[celular] if ahora - x < 3600]
        vinculado = None
        if len(recientes) < MAX_INTENTOS:
            vinculado = vincular(comercios, celular, msg.texto, ahora)  # también si el número ya era de otro
        if vinculado:
            for c in comercios:
                self._repo.guardar(c)
            self._repo.guardar_chat(Chat(celular))  # lo pendiente era de la cuenta anterior
            self.wa.texto(celular, t(vinculado, "vinculado", nombre=vinculado.nombre))
            return
        if codigo_en(msg.texto):
            recientes.append(ahora)
            self.wa.texto(celular, t(None, "muchos_codigos"))
            return
        comercio = comercio_de(celular, comercios)
        if comercio is None:
            self.wa.texto(celular, t(None, "desconocido", portal=self._portal))
            return
        if msg.tipo == "video" and os.environ.get("K_SERVICE"):  # el flujo de video aún no corre en la nube
            self.wa.texto(celular, t(comercio, "solo_fotos"))
            return
        chat = self._repo.chat(celular)
        if chat.estado == "generando" and ahora - chat.generando_desde > MAX_GENERANDO:
            fallo(chat)
        acciones = atender(chat, msg, comercio, time.strftime("%Y-%m-%d"))
        if chat.estado == "generando" and not chat.generando_desde:
            chat.generando_desde = ahora
        elif chat.estado != "generando":
            chat.generando_desde = 0.0
        self._repo.guardar(comercio)
        self._repo.guardar_chat(chat)
        try:
            for accion in acciones:
                self._ejecutar(accion, celular, comercio)
        except Exception as e:  # sin esto el chat quedaría en «generando» para siempre
            traceback.print_exc()
            chat = self._repo.chat(celular)
            fallo(chat)
            self._repo.guardar_chat(chat)
            self.wa.texto(celular, t(comercio, "error"))

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
        elif isinstance(accion, CrearDesdeProducto):
            self._anotar(celular, self._servicio.reel_de_producto(comercio, accion.producto, celular, accion.pedido))
        elif isinstance(accion, OtraPropuesta):
            if not self.diario.proponer_a(comercio, excluir=(accion.producto,)):
                self.wa.texto(celular, t(comercio, "sin_otro"))
        elif isinstance(accion, Publicar):
            pr = self._servicio.obtener(accion.proyecto)
            if not self._es_vigente(pr, comercio, accion.version):
                self.wa.texto(celular, t(comercio, "otra_version"))
                return
            canales = canales_de_destino(pr.estado.get("origen", ""),
                                         [k for k, v in self._servicio.canales_de(comercio).items() if v])
            resultados = self._servicio.publicar(pr, canales, comercio)
            if resultados:
                self.wa.texto(celular, self._resumen(resultados))
            if not any(r["ok"] for r in resultados):
                chat = self._repo.chat(celular)  # la aprobación sigue viva: nada salió
                listo_para_aprobar(chat, pr.id, accion.version)
                self._repo.guardar_chat(chat)
                self.wa.texto(celular, t(comercio, "reintentar" if resultados else "sin_canales"))
        elif isinstance(accion, PedirCambio):
            pr = self._servicio.obtener(accion.proyecto)
            if pr is None or pr.estado.get("comercio_id") != comercio.id:
                fallo_chat = self._repo.chat(celular)
                fallo(fallo_chat)
                self._repo.guardar_chat(fallo_chat)
                self.wa.texto(celular, t(comercio, "otra_version"))
                return
            self._servicio.pedir_cambio(pr, accion.pedido)

    @staticmethod
    def _es_vigente(pr: Proyecto | None, comercio, version: str) -> bool:
        """Solo sale la versión exacta que se aprobó, y solo del comercio dueño."""
        return (pr is not None and pr.estado.get("comercio_id") == comercio.id and pr.estado.get("fase") == "listo"
                and version_de(pr) == version)

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
        return "\n".join(lineas)

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
                    self.wa.texto(celular, t(comercio, "error"))
                    return
                version = version_de(pr)
                listo_para_aprobar(chat, pr.id, version)
                reel = pr.ruta(pr.estado["reels"][pr.estado["look"]]["archivo"])
                cuerpo = t(comercio, "aprobar", pie=self._servicio.pie(pr))
                self.wa.video_con_botones(celular, reel, cuerpo, botones(comercio, pr.id, version))
            except Exception as e:
                traceback.print_exc()
                fallo(chat)
                self.wa.texto(celular, t(comercio, "error"))
            finally:
                self._repo.guardar_chat(chat)

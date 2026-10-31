"""Corre el agente diario: a la hora acordada le manda a cada comercio su propuesta del día.

La ventana de WhatsApp dura 24 horas desde el último mensaje del comercio. Fuera de ella Meta exige una
plantilla aprobada: el envío falla, se anota y se vuelve a intentar al día siguiente.
"""

from __future__ import annotations

import threading
import time
import traceback
from datetime import datetime
from typing import Callable
from zoneinfo import ZoneInfo

from camtoshop.dominio.agente_diario import texto_de_propuesta
from camtoshop.dominio.comercio import Comercio
from camtoshop.dominio.conversacion import botones_de_propuesta

HORA = 9
ZONA = ZoneInfo("America/Bogota")


class AgenteDiario:
    def __init__(self, servicio, wa: Callable):
        self._servicio = servicio
        self._repo = servicio.repo_comercios
        self._wa = wa

    def proponer_a(self, comercio: Comercio, excluir: tuple[str, ...] = ()) -> bool:
        """Manda la propuesta al primer celular del comercio. False si no hay nada que proponer."""
        propuesta = self._servicio.propuesta_para(comercio, excluir)
        if propuesta is None:
            return False
        celular = comercio.celulares[0]
        chat = self._repo.chat(celular)
        chat.propuesta, chat.pedido_propuesta = propuesta.producto.handle, propuesta.pedido
        self._repo.guardar_chat(chat)
        self._wa().texto_con_botones(celular, texto_de_propuesta(propuesta, comercio.idioma),
                                     botones_de_propuesta(comercio, propuesta.producto.handle))
        return True

    def revisar(self, ahora: datetime | None = None):
        ahora = ahora or datetime.now(ZONA)
        dia = ahora.strftime("%Y-%m-%d")
        if ahora.hour < HORA:
            return
        for comercio in self._repo.todos():
            if not comercio.celulares or comercio.ultima_propuesta == dia:
                continue
            if self._repo.chat(comercio.celulares[0]).estado == "generando":
                continue  # no se le interrumpe mientras se hace un Reel
            comercio.ultima_propuesta = dia
            self._repo.guardar(comercio)
            try:
                self.proponer_a(comercio)
            except Exception:  # un comercio que falla no detiene a los demás
                traceback.print_exc()

    def arrancar(self):
        def ciclo():
            while True:
                try:
                    self.revisar()
                except Exception:
                    traceback.print_exc()
                time.sleep(300)
        threading.Thread(target=ciclo, daemon=True).start()

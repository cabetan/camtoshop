"""Caché en JSON alrededor de un adaptador: no se paga dos veces la misma llamada a la API."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from camtoshop.dominio.direccion import Propuesta
from camtoshop.dominio.reel import Caja, Palabra


class EnCache:
    def __init__(self, adaptador, archivo: Path, metodo: str, a_json: Callable[[Any], Any],
                 de_json: Callable[[Any], Any]):
        self._adaptador, self._archivo, self._metodo = adaptador, archivo, metodo
        self._a_json, self._de_json = a_json, de_json

    def __getattr__(self, nombre):
        if nombre != self._metodo:
            return getattr(self._adaptador, nombre)

        def llamar(*args):
            if self._archivo.exists():
                return self._de_json(json.loads(self._archivo.read_text()))
            r = getattr(self._adaptador, nombre)(*args)
            self._archivo.write_text(json.dumps(self._a_json(r), ensure_ascii=False, indent=1))
            return r
        return llamar


def turnos(adaptador, archivo: Path):
    return EnCache(adaptador, archivo, "transcribir", lambda x: x, lambda d: [tuple(x) for x in d])


def palabras(adaptador, archivo: Path):
    return EnCache(adaptador, archivo, "alinear", lambda ps: [asdict(p) for p in ps],
                   lambda d: [Palabra(**p) for p in d])


def rangos(adaptador, archivo: Path):
    return EnCache(adaptador, archivo, "elegir", lambda x: x, lambda d: [tuple(x) for x in d])


def cajas(adaptador, archivo: Path):
    return EnCache(adaptador, archivo, "cajas", lambda d: {str(k): asdict(v) for k, v in d.items()},
                   lambda d: {float(k): Caja(**v) for k, v in d.items()})


def propuesta(adaptador, archivo: Path):
    return EnCache(adaptador, archivo, "proponer", asdict, lambda d: Propuesta(**d))

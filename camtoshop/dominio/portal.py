"""Portal de comercios: registro, conexión de cuentas y celulares desde los que se manda producto.

El dominio decide qué se acepta; hablar con Meta y con Shopify es de los adaptadores. Los tokens y la
clave solo pasan por el repositorio, que los cifra, y nunca salen hacia la página.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
from dataclasses import asdict, dataclass
from typing import Callable, Protocol

from camtoshop.dominio.comercio import Comercio, Conexiones, nuevo_codigo
from camtoshop.dominio.marca import validar_marca

_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TIENDA = re.compile(r"^[a-z0-9][a-z0-9-]*\.myshopify\.com$")
MIN_CLAVE = 8


class ErrorPortal(ValueError):
    """Un problema que se le puede explicar al comercio tal cual."""


@dataclass(frozen=True)
class Cuenta:
    pagina_id: str
    pagina_nombre: str
    instagram_id: str
    instagram_usuario: str
    token: str


class RepoPortal(Protocol):
    def crear(self, nombre: str, correo: str, idioma: str = "es") -> Comercio: ...
    def guardar(self, c: Comercio) -> None: ...
    def por_correo(self, correo: str) -> Comercio | None: ...
    def guardar_token(self, comercio_id: str, nombre: str, valor: str) -> None: ...
    def token(self, comercio_id: str, nombre: str) -> str | None: ...


class ConectorMeta(Protocol):
    def canjear(self, codigo: str, redirect: str) -> str: ...
    def cuentas(self, token: str) -> list[Cuenta]: ...


class ConectorTienda(Protocol):
    def nombre(self, tienda: str, token: str) -> str: ...


def resumir_clave(clave: str, sal: bytes | None = None) -> str:
    sal = sal or secrets.token_bytes(16)
    resumen = hashlib.scrypt(clave.encode(), salt=sal, n=2 ** 14, r=8, p=1)
    return base64.b64encode(sal).decode() + "$" + base64.b64encode(resumen).decode()


def clave_correcta(clave: str, guardada: str | None) -> bool:
    if not guardada or "$" not in guardada:
        return False
    return hmac.compare_digest(resumir_clave(clave, base64.b64decode(guardada.split("$")[0])), guardada)


def normalizar_tienda(texto: str) -> str:
    """«https://mi-tienda.myshopify.com/admin» → «mi-tienda.myshopify.com». Solo dominios de Shopify."""
    tienda = re.sub(r"^https?://", "", (texto or "").strip().lower()).split("/")[0]
    if "." not in tienda:
        tienda += ".myshopify.com"
    if not _TIENDA.match(tienda):
        raise ErrorPortal("Use your store's myshopify.com address")
    return tienda


class Portal:
    def __init__(self, repo: RepoPortal, meta: ConectorMeta, tienda: ConectorTienda, reloj: Callable[[], float]):
        self._repo, self._meta, self._tienda, self._reloj = repo, meta, tienda, reloj

    def registrar(self, nombre: str, correo: str, clave: str, idioma: str = "es") -> Comercio:
        if len(nombre.strip()) < 2:
            raise ErrorPortal("Tell us your business name")
        if not _CORREO.match(correo.strip()):
            raise ErrorPortal("That email doesn't look right")
        if len(clave) < MIN_CLAVE:
            raise ErrorPortal(f"Use at least {MIN_CLAVE} characters for your password")
        if self._repo.por_correo(correo):
            raise ErrorPortal("That email already has an account")
        comercio = self._repo.crear(nombre, correo, idioma)
        self._repo.guardar_token(comercio.id, "clave", resumir_clave(clave))
        return comercio

    def entrar(self, correo: str, clave: str) -> Comercio:
        comercio = self._repo.por_correo(correo)
        if comercio is None or not clave_correcta(clave, self._repo.token(comercio.id, "clave")):
            raise ErrorPortal("Wrong email or password")
        return comercio

    def estado(self, c: Comercio) -> dict:
        con = c.conexiones
        return {"nombre": c.nombre, "correo": c.correo, "idioma": c.idioma, "demo": c.demo, "celulares": c.celulares,
                "instagram": con.instagram_usuario, "pagina": con.pagina_nombre, "shopify": con.shopify_tienda,
                "por_elegir": [{"id": x["pagina_id"], "pagina": x["pagina_nombre"], "instagram": x["instagram_usuario"]}
                               for x in self._pendientes(c)],
                "marca": asdict(c.marca), "listo": bool(con.instagram_id and c.celulares)}

    def guardar_marca(self, c: Comercio, datos: dict) -> None:
        """Los archivos subidos no se tocan desde aquí: solo cambian al subir o quitar el archivo."""
        try:
            c.marca = validar_marca({**datos, "logo": c.marca.logo, "musica_propia": c.marca.musica_propia})
        except (TypeError, ValueError) as e:
            raise ErrorPortal(str(e) if isinstance(e, ValueError) else "Choose one of the available options")
        self._repo.guardar(c)

    def registrar_logo(self, c: Comercio, hay: bool) -> None:
        c.marca.logo = hay
        self._repo.guardar(c)

    def registrar_pista(self, c: Comercio, hay: bool) -> None:
        c.marca.musica_propia = hay
        if hay:
            c.marca.musica = "propia"
        elif c.marca.musica == "propia":
            c.marca.musica = "energia"
        self._repo.guardar(c)

    def codigo_de_celular(self, c: Comercio) -> str:
        codigo = nuevo_codigo(c, self._reloj())
        self._repo.guardar(c)
        return codigo

    def quitar_celular(self, c: Comercio, celular: str) -> None:
        if celular in c.celulares:
            c.celulares.remove(celular)
            self._repo.guardar(c)

    def conectar_meta(self, c: Comercio, codigo: str, redirect: str) -> None:
        """Canjea el permiso de Facebook. Con una sola cuenta queda conectada; con varias, el comercio elige."""
        cuentas = [x for x in self._meta.cuentas(self._meta.canjear(codigo, redirect)) if x.instagram_id]
        if not cuentas:
            raise ErrorPortal("We found no Instagram professional account linked to a Facebook Page you manage")
        if len(cuentas) == 1:
            self._activar(c, cuentas[0])
        else:
            self._repo.guardar_token(c.id, "meta_por_elegir", json.dumps([asdict(x) for x in cuentas]))

    def elegir_cuenta(self, c: Comercio, pagina_id: str) -> None:
        cuenta = next((x for x in self._pendientes(c) if x["pagina_id"] == pagina_id), None)
        if cuenta is None:
            raise ErrorPortal("Connect Instagram again")
        self._activar(c, Cuenta(**cuenta))

    def _pendientes(self, c: Comercio) -> list[dict]:
        return json.loads(self._repo.token(c.id, "meta_por_elegir") or "[]")

    def _activar(self, c: Comercio, cuenta: Cuenta) -> None:
        c.conexiones.instagram_id, c.conexiones.instagram_usuario = cuenta.instagram_id, cuenta.instagram_usuario
        c.conexiones.pagina_id, c.conexiones.pagina_nombre = cuenta.pagina_id, cuenta.pagina_nombre
        self._repo.guardar_token(c.id, "meta", cuenta.token)
        self._repo.guardar_token(c.id, "meta_por_elegir", "")
        self._repo.guardar(c)

    def conectar_shopify(self, c: Comercio, tienda: str, token: str) -> None:
        tienda = normalizar_tienda(tienda)
        if not token.strip():
            raise ErrorPortal("Paste your Shopify Admin API token")
        self._tienda.nombre(tienda, token.strip())  # si el token no sirve, falla aquí y no al publicar
        c.conexiones.shopify_tienda = tienda
        self._repo.guardar_token(c.id, "shopify", token.strip())
        self._repo.guardar(c)

    def desconectar(self, c: Comercio, canal: str) -> None:
        if canal == "instagram":
            c.conexiones = Conexiones(shopify_tienda=c.conexiones.shopify_tienda)
            self._repo.guardar_token(c.id, "meta", "")
        elif canal == "shopify":
            c.conexiones.shopify_tienda = ""
            self._repo.guardar_token(c.id, "shopify", "")
        else:
            raise ErrorPortal("Unknown channel")
        self._repo.guardar(c)

"""Facebook Login for Business: el comercio autoriza su página y su Instagram profesional."""

from __future__ import annotations

from urllib.parse import urlencode

import requests

from camtoshop.dominio.portal import Cuenta, ErrorPortal

VERSION = "v23.0"
GRAPH = f"https://graph.facebook.com/{VERSION}"
CAMPOS_PAGINA = "id,name,access_token,instagram_business_account{id,username}"


def url_de_login(app_id: str, config_id: str, redirect: str, estado: str) -> str:
    return f"https://www.facebook.com/{VERSION}/dialog/oauth?" + urlencode({
        "client_id": app_id, "config_id": config_id, "redirect_uri": redirect, "state": estado,
        "response_type": "code", "override_default_response_type": "true",
    })


class MetaOAuth:
    def __init__(self, app_id: str, secreto_app: str):
        self._app_id, self._secreto = app_id, secreto_app

    def _token(self, parametros: dict) -> str:
        r = requests.get(f"{GRAPH}/oauth/access_token", timeout=30,
                         params={"client_id": self._app_id, "client_secret": self._secreto, **parametros})
        if not r.ok:
            raise ErrorPortal("Facebook didn't accept the connection. Please try again.")
        return r.json()["access_token"]

    def canjear(self, codigo: str, redirect: str) -> str:
        corto = self._token({"code": codigo, "redirect_uri": redirect})
        try:  # el token de usuario largo da tokens de página que no vencen
            return self._token({"grant_type": "fb_exchange_token", "fb_exchange_token": corto})
        except ErrorPortal:
            return corto  # un token de negocio no se intercambia: ya es de larga duración

    def _leer(self, ruta: str, token: str, **parametros) -> dict | None:
        r = requests.get(f"{GRAPH}/{ruta}", timeout=30, params=parametros,
                         headers={"Authorization": f"Bearer {token}"})
        return r.json() if r.ok else None

    def _paginas_concedidas(self, token: str) -> tuple[list[str], list[str]]:
        """Páginas elegidas en el diálogo y permisos del token.

        Con Facebook Login for Business, /me/accounts puede venir vacío aunque el comercio haya
        elegido su página: la lista fiable está en los granular_scopes del token.
        """
        datos = (self._leer("debug_token", f"{self._app_id}|{self._secreto}", input_token=token) or {}).get("data", {})
        ids = {i for g in datos.get("granular_scopes", []) if g.get("scope", "").startswith("pages_")
               for i in g.get("target_ids", [])}
        return sorted(ids), datos.get("scopes", [])

    def cuentas(self, token: str) -> list[Cuenta]:
        listadas = self._leer("me/accounts", token, fields=CAMPOS_PAGINA, limit=100)
        if listadas is None:
            raise ErrorPortal("We couldn't read your Facebook Pages. Please try again.")
        paginas = {p["id"]: p for p in listadas.get("data", [])}
        concedidas, permisos = self._paginas_concedidas(token)
        for pagina_id in concedidas:
            if pagina_id not in paginas and (p := self._leer(pagina_id, token, fields=CAMPOS_PAGINA)):
                paginas[pagina_id] = p
        print(f"Facebook Login: {len(listadas.get('data', []))} en me/accounts, {len(concedidas)} concedidas, "
              f"{sum('instagram_business_account' in p for p in paginas.values())} con Instagram; "
              f"permisos: {permisos}", flush=True)
        salida = []
        for p in paginas.values():
            ig = p.get("instagram_business_account") or {}
            salida.append(Cuenta(p["id"], p.get("name", ""), ig.get("id", ""), ig.get("username", ""),
                                 p.get("access_token") or token))
        return salida

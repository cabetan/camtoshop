"""Facebook Login for Business: el comercio autoriza su página y su Instagram profesional."""

from __future__ import annotations

from urllib.parse import urlencode

import requests

from camtoshop.dominio.portal import Cuenta, ErrorPortal

VERSION = "v23.0"
GRAPH = f"https://graph.facebook.com/{VERSION}"


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

    def cuentas(self, token: str) -> list[Cuenta]:
        r = requests.get(f"{GRAPH}/me/accounts", timeout=30, params={
            "fields": "id,name,access_token,instagram_business_account{id,username}", "limit": 100,
        }, headers={"Authorization": f"Bearer {token}"})
        if not r.ok:
            raise ErrorPortal("We couldn't read your Facebook Pages. Please try again.")
        salida = []
        for p in r.json().get("data", []):
            ig = p.get("instagram_business_account") or {}
            salida.append(Cuenta(p["id"], p.get("name", ""), ig.get("id", ""), ig.get("username", ""),
                                 p.get("access_token", "")))
        return salida

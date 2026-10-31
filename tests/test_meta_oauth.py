from camtoshop.adaptadores import meta_oauth
from camtoshop.adaptadores.meta_oauth import MetaOAuth


class Respuesta:
    ok = True

    def __init__(self, datos):
        self._datos = datos

    def json(self):
        return self._datos


def graph_falso(monkeypatch, respuestas):
    monkeypatch.setattr(meta_oauth.requests, "get",
                        lambda url, **_: Respuesta(respuestas[url.rsplit("v23.0/", 1)[1]]))


def test_pagina_elegida_en_el_dialogo_aunque_me_accounts_venga_vacio(monkeypatch):
    graph_falso(monkeypatch, {
        "me/accounts": {"data": []},
        "debug_token": {"data": {"scopes": ["pages_show_list"], "granular_scopes": [
            {"scope": "pages_show_list", "target_ids": ["p1"]}, {"scope": "instagram_basic", "target_ids": ["ig9"]}]}},
        "p1": {"id": "p1", "name": "Tienda", "access_token": "tp",
               "instagram_business_account": {"id": "ig1", "username": "tienda"}},
    })
    cuenta = MetaOAuth("app", "secreto").cuentas("t")[0]
    assert (cuenta.pagina_id, cuenta.instagram_id, cuenta.token) == ("p1", "ig1", "tp")


def test_sin_token_de_pagina_usa_el_token_del_login(monkeypatch):
    graph_falso(monkeypatch, {
        "me/accounts": {"data": [{"id": "p1", "instagram_business_account": {"id": "ig1"}}]},
        "debug_token": {"data": {}},
    })
    assert MetaOAuth("app", "secreto").cuentas("t")[0].token == "t"

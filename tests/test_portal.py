import pytest

from camtoshop.adaptadores.sesion import firmar, verificar
from camtoshop.dominio.comercio import comercio_de, vincular
from camtoshop.dominio.portal import Cuenta, ErrorPortal, Portal, clave_correcta, normalizar_tienda, resumir_clave


class RepoFalso:
    def __init__(self):
        self.comercios, self.tokens = {}, {}

    def crear(self, nombre, correo, idioma="es"):
        from camtoshop.dominio.comercio import Comercio
        c = Comercio(f"c{len(self.comercios)}", nombre, correo.lower(), idioma=idioma)
        self.comercios[c.id] = c
        return c

    def guardar(self, c):
        self.comercios[c.id] = c

    def por_correo(self, correo):
        return next((c for c in self.comercios.values() if c.correo == correo.lower()), None)

    def guardar_token(self, comercio_id, nombre, valor):
        self.tokens[comercio_id, nombre] = valor

    def token(self, comercio_id, nombre):
        return self.tokens.get((comercio_id, nombre))


class MetaFalsa:
    def __init__(self, cuentas):
        self._cuentas = cuentas

    def canjear(self, codigo, redirect):
        return "token-usuario"

    def cuentas(self, token):
        return self._cuentas


class TiendaFalsa:
    def nombre(self, tienda, token):
        if token != "bueno":
            raise ErrorPortal("rechazado")
        return "Mi tienda"


UNA = Cuenta("p1", "Velas", "ig1", "velas.luz", "secreto-pagina")
OTRA = Cuenta("p2", "Tazas", "ig2", "tazas.co", "secreto-otra")
SIN_IG = Cuenta("p3", "Sin IG", "", "", "x")


def montar(cuentas=(UNA,)):
    repo = RepoFalso()
    portal = Portal(repo, MetaFalsa(list(cuentas)), TiendaFalsa(), lambda: 1000.0)
    return portal, repo, portal.registrar("Velas Luz", "A@b.co", "una-clave-larga")


def test_registro_valida_y_no_guarda_la_clave_en_claro():
    portal, repo, c = montar()
    assert repo.token(c.id, "clave") != "una-clave-larga" and clave_correcta("una-clave-larga", repo.token(c.id, "clave"))
    assert portal.entrar("a@B.co", "una-clave-larga") is c
    for args in (("x", "a@c.co", "12345678"), ("Tienda", "mal", "12345678"), ("Tienda", "b@c.co", "corta"),
                 ("Tienda", "a@b.co", "12345678")):
        with pytest.raises(ErrorPortal):
            portal.registrar(*args)
    with pytest.raises(ErrorPortal):
        portal.entrar("a@b.co", "otra-clave")


def test_clave_guardada_rara_no_entra():
    assert not clave_correcta("x", None) and not clave_correcta("x", "sin-formato")
    assert clave_correcta("x", resumir_clave("x"))


def test_una_cuenta_de_instagram_queda_conectada():
    portal, repo, c = montar((UNA, SIN_IG))
    portal.conectar_meta(c, "codigo", "https://x/volver")
    assert c.conexiones.instagram_usuario == "velas.luz" and repo.token(c.id, "meta") == "secreto-pagina"
    assert "secreto-pagina" not in str(portal.estado(c))


def test_varias_cuentas_las_elige_el_comercio_y_no_salen_los_tokens():
    portal, repo, c = montar((UNA, OTRA))
    portal.conectar_meta(c, "codigo", "r")
    estado = portal.estado(c)
    assert [x["id"] for x in estado["por_elegir"]] == ["p1", "p2"] and "secreto" not in str(estado)
    assert not c.conexiones.instagram_id
    portal.elegir_cuenta(c, "p2")
    assert repo.token(c.id, "meta") == "secreto-otra" and portal.estado(c)["por_elegir"] == []
    with pytest.raises(ErrorPortal):
        portal.elegir_cuenta(c, "p1")


def test_sin_instagram_profesional_explica_el_problema():
    portal, _, c = montar((SIN_IG,))
    with pytest.raises(ErrorPortal):
        portal.conectar_meta(c, "codigo", "r")


def test_listo_pide_instagram_y_celular():
    portal, _, c = montar()
    portal.conectar_meta(c, "codigo", "r")
    assert not portal.estado(c)["listo"]
    assert vincular([c], "573001234567", portal.codigo_de_celular(c), 1100.0) is c
    assert portal.estado(c)["listo"] and comercio_de("573001234567", [c]) is c
    portal.quitar_celular(c, "573001234567")
    assert not portal.estado(c)["listo"]


def test_shopify_comprueba_el_token_y_solo_acepta_dominios_de_shopify():
    portal, repo, c = montar()
    with pytest.raises(ErrorPortal):
        portal.conectar_shopify(c, "mi-tienda", "malo")
    assert not c.conexiones.shopify_tienda
    portal.conectar_shopify(c, "https://Mi-Tienda.myshopify.com/admin", "bueno")
    assert c.conexiones.shopify_tienda == "mi-tienda.myshopify.com" and repo.token(c.id, "shopify") == "bueno"
    for mala in ("evil.com", "127.0.0.1", "x.myshopify.com.evil.com"):
        with pytest.raises(ErrorPortal):
            normalizar_tienda(mala)


def test_desconectar_borra_el_token():
    portal, repo, c = montar()
    portal.conectar_meta(c, "codigo", "r")
    portal.desconectar(c, "instagram")
    assert not c.conexiones.instagram_id and not repo.token(c.id, "meta")


def test_firma_vence_y_no_sirve_para_otro_proposito():
    f = firmar("k", "sesion", "c1", vence=100)
    assert verificar("k", "sesion", f, 50) == "c1"
    assert verificar("k", "sesion", f, 150) is None
    assert verificar("k", "meta", f, 50) is None
    assert verificar("otra", "sesion", f, 50) is None
    assert verificar("k", "sesion", "", 50) is None


def test_marca_valida_se_guarda_y_la_invalida_no():
    portal, _, c = montar()
    portal.guardar_marca(c, {"estilo": "color", "fuente": "poppins", "primario": "#B3261E",
                             "secundario": "#FFE9C9", "musica": "calida"})
    assert c.marca.estilo == "color"
    with pytest.raises(ErrorPortal):
        portal.guardar_marca(c, {"estilo": "color", "fuente": "comic", "primario": "#B3261E",
                                 "secundario": "#FFE9C9", "musica": "calida"})
    assert c.marca.fuente == "poppins"


def test_no_se_elige_pista_propia_sin_subirla():
    portal, _, c = montar()
    with pytest.raises(ErrorPortal):
        portal.guardar_marca(c, {"estilo": "impacto", "fuente": "barlow", "primario": "#FFD23F",
                                 "secundario": "#141414", "musica": "propia"})
    portal.registrar_pista(c, True)
    assert c.marca.musica == "propia"
    portal.registrar_pista(c, False)
    assert c.marca.musica == "energia"

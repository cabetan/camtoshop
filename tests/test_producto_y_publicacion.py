from pathlib import Path

from camtoshop.dominio.anuncios import Anuncio, normalizar_anuncios
from camtoshop.dominio.producto import Ficha, Precio, Texto, normalizar_ficha, precio_valido, recortar, slug
from camtoshop.dominio.publicacion import EnTienda, pie_de_instagram, publicar


def ficha(precio=Precio(85000, "COP"), idioma="es"):
    return Ficha(idioma, {idioma: Texto("Vela Estrella", "Vela artesanal de soya.", ["Hecha a mano", "Aroma floral"])},
                 precio, "Luz de Madre", "Velas", ["velas", "Hecho En Medellín", "velas"])


def test_precio_en_pesos_sin_decimales_y_con_punto_de_miles():
    assert Precio(85000, "COP").texto() == "$85.000"
    assert Precio(85000, "COP").para_api() == "85000"


def test_precio_en_dolares():
    assert Precio(50, "USD").texto() == "US$50"
    assert Precio(49.9, "USD").para_api() == "49.90"


def test_precio_valido_descarta_lo_absurdo():
    assert precio_valido(0, "COP") is None
    assert precio_valido(10, "pesos") is None
    assert precio_valido(85000.4, "cop") == Precio(85000, "COP")


def test_recortar_respeta_palabras():
    assert recortar("una frase bastante larga para el titular", 20) == "una frase bastante…"
    assert recortar("corta", 20) == "corta"


def test_slug_sin_tildes():
    assert slug("Café AURES · Tostión media") == "cafe-aures-tostion-media"


def test_normalizar_ficha_avisa_si_falta_el_precio_y_limpia_etiquetas():
    f = ficha(precio=None)
    avisos = normalizar_ficha(f)
    assert any("precio" in a for a in avisos)
    assert f.etiquetas == ["hecho en medellín", "velas"]


def test_anuncios_uno_por_angulo_y_dentro_de_limites():
    largos = "x " * 100
    anuncios = normalizar_anuncios([
        Anuncio("oferta", "Solo $85.000", largos, "Comprar", "c"),
        Anuncio("beneficio", "Relaja tu hogar con aroma natural y luz cálida todas las noches", "t", "Ver", "c"),
        Anuncio("oferta", "repetido", "t", "Ver", "c"),
        Anuncio("inventado", "x", "t", "Ver", "c"),
    ])
    assert [a.angulo for a in anuncios] == ["beneficio", "oferta"]
    assert len(anuncios[0].titular) <= 40 and len(anuncios[1].texto) <= 125


def test_pie_de_instagram_tiene_precio_llamado_y_etiquetas():
    pie = pie_de_instagram(ficha(), "La vela que relaja tu hogar")
    assert pie.startswith("La vela que relaja tu hogar")
    assert "$85.000" in pie and "DM" in pie and "biografía" not in pie
    assert "#HechoEnMedellín" in pie and pie.count("#Velas") == 1


class TiendaFalsa:
    def publicar_producto(self, ficha, video):
        return EnTienda("https://tienda.test/products/vela", ["https://cdn.test/vela.png"])


class CatalogoFalso:
    def __init__(self):
        self.recibido = None

    def publicar_producto(self, ficha, en_tienda):
        self.recibido = en_tienda
        return "catalogo/123"


class RedQueFalla:
    def publicar_reel(self, video, pie, portada):
        raise RuntimeError("token vencido")


def test_publicar_encadena_shopify_con_el_catalogo_y_aisla_fallos():
    catalogo = CatalogoFalso()
    r = publicar(ficha(), Path("reel.mp4"), None, ["shopify", "catalogo_meta", "instagram"],
                 TiendaFalsa(), catalogo, RedQueFalla())
    assert [(x.canal, x.ok) for x in r] == [("shopify", True), ("catalogo_meta", True), ("instagram", False)]
    assert catalogo.recibido.url_producto == "https://tienda.test/products/vela"
    assert "token vencido" in r[2].detalle


def test_publicar_sin_precio_no_toca_las_tiendas():
    r = publicar(ficha(precio=None), Path("reel.mp4"), None, ["shopify", "catalogo_meta"],
                 TiendaFalsa(), CatalogoFalso(), None)
    assert all(not x.ok and "precio" in x.detalle for x in r)


def test_canal_no_conectado_da_un_mensaje_claro():
    [r] = publicar(ficha(), Path("reel.mp4"), None, ["shopify"], None, None, None)
    assert not r.ok and "SHOPIFY_TOKEN" in r.detalle


class TiendaEnBorrador:
    def publicar_producto(self, ficha, video):
        return EnTienda("https://tienda.test/products/vela", ["https://cdn.test/vela.png"],
                        "https://tienda.test/admin/products/1")


def test_en_borrador_se_muestra_el_enlace_para_revisar():
    [r] = publicar(ficha(), Path("reel.mp4"), None, ["shopify"], TiendaEnBorrador(), None, None)
    assert r.ok and r.url.endswith("/admin/products/1") and "Borrador" in r.detalle


from camtoshop.dominio.producto import ProductoDeTienda, elegir_para_reel, mensaje_desde_tienda, texto_plano
from camtoshop.dominio.reel_fotos import precio_respaldado


def test_mensaje_desde_tienda_respalda_el_precio():
    p = ProductoDeTienda("vela", "Vela Estrella", texto_plano("<p>Hecha a mano&nbsp;con soya.</p>"),
                         Precio(85000, "COP"), ("https://cdn/x.jpg",))
    mensaje = mensaje_desde_tienda(p)
    assert "Hecha a mano con soya." in mensaje and "<p>" not in mensaje
    assert precio_respaldado(p.precio, mensaje)


def test_elegir_para_reel_descarta_sin_foto_sin_precio_o_borrador():
    ok = ProductoDeTienda("a", "A", "", Precio(10, "USD"), ("u",))
    productos = [ok, ProductoDeTienda("b", "B", "", None, ("u",)), ProductoDeTienda("c", "C", "", Precio(1, "USD"), ()),
                 ProductoDeTienda("d", "D", "", Precio(1, "USD"), ("u",), "DRAFT")] + [ok] * 10
    elegidos = elegir_para_reel(productos)
    assert len(elegidos) == 6 and all(p.handle == "a" for p in elegidos)
    assert [p.handle for p in elegir_para_reel(productos[1:4], incluir_borradores=True)] == ["d"]


def test_producto_de_la_tienda_solo_va_a_las_redes():
    from camtoshop.dominio.publicacion import canales_de_destino
    todos = ["shopify", "catalogo_meta", "instagram"]
    assert canales_de_destino("shopify", todos) == ["instagram"]
    assert canales_de_destino("whatsapp", todos) == todos


def test_el_pie_usa_el_texto_que_vende_el_reel():
    pie = pie_de_instagram(ficha(), "¿Tu casa pide calidez?", ["Regalo que emociona"], "Escríbenos ahora")
    assert "Regalo que emociona" in pie and "Escríbenos ahora" in pie

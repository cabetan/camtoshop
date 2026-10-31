from camtoshop.dominio.comercio import (
    Comercio, LIMITE_DIARIO, codigo_en, comercio_de, normalizar_celular, nuevo_codigo, registrar_uso, vincular,
)
from camtoshop.dominio.conversacion import (
    Chat, CrearDesdeFotos, CrearDesdeVideo, Mensaje, PedirCambio, Publicar, Responder, atender, botones,
    listo_para_aprobar,
)

DIA = "2026-10-30"


def comercio(**cambios):
    return Comercio("c1", "Velas Luz", "a@b.co", **cambios)


def test_normalizar_celular_colombiano():
    assert normalizar_celular("300 123 4567") == "573001234567"
    assert normalizar_celular("+57 300-123-4567") == "573001234567"
    assert normalizar_celular("+1 (201) 510-1873") == "12015101873"


def test_vincular_con_codigo_vigente_y_solo_una_vez():
    a, b = comercio(), Comercio("c2", "Otro", "x@y.co", celulares=["573001234567"])
    codigo = nuevo_codigo(a, ahora=1000)
    assert codigo.startswith("CAMTO-") and codigo_en(f"hola {codigo.lower()}") == codigo[-4:]
    assert vincular([a, b], "573001234567", codigo, ahora=1100) is a
    assert comercio_de("573001234567", [a, b]) is a and b.celulares == []  # se mueve al nuevo dueño
    assert vincular([a, b], "573001234567", codigo, ahora=1200) is None  # el código se usa una vez


def test_codigo_vencido_no_vincula():
    a = comercio()
    codigo = nuevo_codigo(a, ahora=0)
    assert vincular([a], "57300", codigo, ahora=31 * 60) is None


def test_limite_diario():
    a = comercio()
    assert all(registrar_uso(a, DIA) for _ in range(LIMITE_DIARIO))
    assert not registrar_uso(a, DIA)
    assert registrar_uso(a, "2026-10-31")


def tipos(acciones):
    return [type(a).__name__ for a in acciones]


def test_foto_sin_datos_pregunta_una_sola_vez_y_arranca_con_el_precio():
    c, chat = comercio(), Chat("57300")
    assert tipos(atender(chat, Mensaje("imagen", media="m1"), c, DIA)) == ["Responder"]
    assert atender(chat, Mensaje("imagen", media="m2"), c, DIA) == []  # la segunda foto no repite la pregunta
    assert tipos(atender(chat, Mensaje("texto", "Vela de soya"), c, DIA)) == ["Responder"]  # pide el precio
    acciones = atender(chat, Mensaje("texto", "85 mil"), c, DIA)
    assert acciones[0] == CrearDesdeFotos(("m1", "m2"), "Vela de soya 85 mil", "")
    assert chat.estado == "generando" and chat.fotos == []


def test_foto_con_pie_y_precio_arranca_de_una():
    acciones = atender(Chat("57300"), Mensaje("imagen", "Taza artesanal $45.000", media="m1"), comercio(), DIA)
    assert isinstance(acciones[0], CrearDesdeFotos)


def test_sin_precio_tras_preguntar_igual_arranca():
    c, chat = comercio(), Chat("57300")
    atender(chat, Mensaje("imagen", media="m1"), c, DIA)
    atender(chat, Mensaje("texto", "Una taza"), c, DIA)
    assert isinstance(atender(chat, Mensaje("texto", "no sé todavía"), c, DIA)[0], CrearDesdeFotos)


def test_nota_de_voz_con_fotos_arranca():
    c, chat = comercio(), Chat("57300")
    atender(chat, Mensaje("imagen", media="m1"), c, DIA)
    acciones = atender(chat, Mensaje("audio", media="voz1"), c, DIA)
    assert acciones[0] == CrearDesdeFotos(("m1",), "", "voz1")


def test_mientras_genera_no_acepta_otro():
    c, chat = comercio(), Chat("57300", estado="generando")
    assert tipos(atender(chat, Mensaje("imagen", media="m9"), c, DIA)) == ["Responder"]


def test_publicar_solo_con_la_version_vigente():
    c, chat = comercio(), Chat("57300")
    listo_para_aprobar(chat, "p1", "v2")
    viejo = atender(chat, Mensaje("boton", boton="publicar|p1|v1"), c, DIA)
    assert tipos(viejo) == ["Responder"] and chat.estado == "aprobacion"
    ids = [i for i, _ in botones(c, "p1", "v2")]
    assert atender(chat, Mensaje("boton", boton=ids[0]), c, DIA)[1] == Publicar("p1")
    assert tipos(atender(chat, Mensaje("boton", boton=ids[0]), c, DIA)) == ["Responder"]  # no publica dos veces


def test_cambiar_invalida_la_aprobacion():
    c, chat = comercio(), Chat("57300")
    listo_para_aprobar(chat, "p1", "v1")
    atender(chat, Mensaje("boton", boton="cambiar|p1|v1"), c, DIA)
    assert atender(chat, Mensaje("texto", "más calmado"), c, DIA)[0] == PedirCambio("p1", "más calmado")
    assert tipos(atender(chat, Mensaje("boton", boton="publicar|p1|v1"), c, DIA)) == ["Responder"]


def test_video_crea_proyecto_de_video():
    assert isinstance(atender(Chat("57300"), Mensaje("video", media="v1"), comercio(), DIA)[0], CrearDesdeVideo)


def test_respuestas_en_ingles_si_el_comercio_es_en_ingles():
    acciones = atender(Chat("1201"), Mensaje("texto", "hi"), comercio(idioma="en"), DIA)
    assert isinstance(acciones[0], Responder) and acciones[0].texto.startswith("Send me")

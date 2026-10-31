from camtoshop.dominio.agente_diario import (
    Desempeno, aprender, elegir_producto, estilo_de, proponer, texto_de_propuesta,
)
from camtoshop.dominio.comercio import Comercio
from camtoshop.dominio.conversacion import (
    Chat, CrearDesdeProducto, Mensaje, OtraPropuesta, Responder, atender, botones_de_propuesta,
)
from camtoshop.dominio.producto import Precio, ProductoDeTienda

DIA = "2026-10-31"


def producto(handle, estado="ACTIVE", imagenes=("u",), precio=Precio(45000, "COP")):
    return ProductoDeTienda(handle, handle.title(), "", precio, imagenes, estado)


def test_elige_el_que_lleva_mas_tiempo_sin_promoverse():
    productos = [producto("a"), producto("b"), producto("c")]
    assert elegir_producto(productos, {"a": "2026-10-30", "b": "2026-10-01", "c": "2026-09-01"}, DIA).handle == "c"
    assert elegir_producto(productos, {"a": "2026-10-30", "b": "2026-10-01"}, DIA).handle == "c"  # nunca promovido


def test_no_repite_salvo_que_no_haya_otro_y_respeta_lo_excluido():
    assert elegir_producto([producto("a")], {"a": "2026-10-30"}, DIA).handle == "a"
    assert elegir_producto([producto("a"), producto("b")], {}, DIA, excluir=("a",)).handle == "b"
    assert elegir_producto([producto("a")], {}, DIA, excluir=("a",)) is None


def test_no_propone_lo_que_no_sirve_para_un_reel():
    malos = [producto("a", imagenes=()), producto("b", precio=None), producto("c", estado="DRAFT")]
    assert elegir_producto(malos, {}, DIA) is None
    assert elegir_producto(malos, {}, DIA, incluir_borradores=True).handle == "c"


def test_estilos_de_gancho():
    assert estilo_de("¿Qué dice tu ser hoy?") == "pregunta"
    assert estilo_de("Solo $45.000 esta semana") == "precio"
    assert estilo_de("Hecha a mano en Medellín") == "directo"


def buena(gancho, alcance=100, guardados=5):
    return Desempeno(gancho, alcance, me_gusta=5, guardados=guardados)


def test_con_pocos_datos_no_saca_conclusiones():
    assert aprender([]) is None
    assert aprender([buena("¿Cuál?"), buena("¿Otra?")]) is None  # sin con qué comparar
    assert aprender([buena("¿Cuál?"), buena("Directo")]) is None  # uno de cada estilo no alcanza


def test_aprende_el_estilo_que_gana():
    leccion = aprender([buena("¿Cuál?"), buena("¿Otra?"), buena("Directo", guardados=0), buena("Claro", guardados=0)])
    assert leccion.estilo == "pregunta" and leccion.reels == 2 and leccion.tasa == 20 and leccion.tasa_otros == 5


def test_una_ventaja_pequena_no_es_leccion():
    assert aprender([buena("¿Cuál?"), buena("¿Otra?"), buena("Directo"), buena("Claro")]) is None


def test_la_propuesta_lleva_lo_aprendido_y_explica_por_que():
    metricas = [buena("¿Cuál?"), buena("¿Otra?"), buena("Directo", guardados=0), buena("Claro", guardados=0)]
    p = proponer([producto("vela")], {"vela": "2026-10-01"}, metricas, DIA)
    assert "question" in p.pedido and p.dias_sin_promover == 30
    texto = texto_de_propuesta(p, "es")
    assert "*Vela*" in texto and "30 días" in texto and "con pregunta" in texto and "20,0" in texto
    assert "Good morning" in texto_de_propuesta(p, "en")


def montar():
    c = Comercio("c1", "Velas", "a@b.co")
    return c, Chat("57300", propuesta="vela", pedido_propuesta="Open with a question")


def test_hazlo_crea_el_reel_con_lo_aprendido_y_marca_el_producto():
    c, chat = montar()
    boton = botones_de_propuesta(c, "vela")[0][0]
    acciones = atender(chat, Mensaje("boton", boton=boton), c, DIA)
    assert acciones[0] == CrearDesdeProducto("vela", "Open with a question")
    assert chat.estado == "generando" and c.promovidos == {"vela": DIA} and chat.propuesta == ""
    assert isinstance(atender(chat, Mensaje("boton", boton=boton), c, DIA)[0], Responder)  # no crea dos


def test_otro_y_hoy_no():
    c, chat = montar()
    assert atender(chat, Mensaje("boton", boton=botones_de_propuesta(c, "vela")[1][0]), c, DIA) == [OtraPropuesta("vela")]
    assert chat.propuesta == "vela"
    assert isinstance(atender(chat, Mensaje("boton", boton=botones_de_propuesta(c, "vela")[2][0]), c, DIA)[0], Responder)
    assert chat.propuesta == "" and c.promovidos == {}


def test_boton_de_propuesta_vieja_no_hace_nada():
    c, chat = montar()
    acciones = atender(chat, Mensaje("boton", boton=botones_de_propuesta(c, "otra")[0][0]), c, DIA)
    assert isinstance(acciones[0], Responder) and chat.estado == ""

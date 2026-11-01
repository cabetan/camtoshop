from types import SimpleNamespace

from camtoshop.aplicacion.agente_whatsapp import AgenteWhatsApp, version_de


class ProyectoFalso(SimpleNamespace):
    pass


def proyecto(fase="listo", comercio_id="c1"):
    return ProyectoFalso(id="p1", estado={"fase": fase, "comercio_id": comercio_id, "look": "fotos",
                                          "reels": {"fotos": {"archivo": "a.mp4"}}})


def test_solo_publica_la_version_lista_y_del_dueno():
    c = SimpleNamespace(id="c1")
    v = version_de(proyecto())
    assert AgenteWhatsApp._es_vigente(proyecto(), c, v)
    assert not AgenteWhatsApp._es_vigente(proyecto(fase="procesando"), c, v)
    assert not AgenteWhatsApp._es_vigente(proyecto(comercio_id="c2"), c, v)
    assert not AgenteWhatsApp._es_vigente(proyecto(), c, "otra")
    assert not AgenteWhatsApp._es_vigente(None, c, v)


def test_sin_instagram_conectado_publicar_no_queda_muerto(monkeypatch):
    from camtoshop.aplicacion import agente_whatsapp as m
    from camtoshop.dominio.conversacion import Chat

    pr = proyecto()
    enviados, chat = [], Chat(celular="57300", estado="")
    monkeypatch.setattr(AgenteWhatsApp, "wa", SimpleNamespace(texto=lambda c, texto: enviados.append(texto)))
    a = AgenteWhatsApp.__new__(AgenteWhatsApp)
    a._repo = SimpleNamespace(chat=lambda c: chat, guardar_chat=lambda c: None)
    a._servicio = SimpleNamespace(obtener=lambda i: pr, canales_de=lambda c: {}, publicar=lambda *x: [])
    a._ejecutar(m.Publicar("p1", version_de(pr)), "57300", SimpleNamespace(id="c1", idioma="es"))
    assert chat.estado == "aprobacion" and len(enviados) == 1 and "Instagram" in enviados[0]

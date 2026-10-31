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

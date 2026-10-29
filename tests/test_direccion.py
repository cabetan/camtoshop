from camtoshop.dominio.direccion import LOOKS, Propuesta, armar_plan, centros_de_zoom
from camtoshop.dominio.reel import Caja, Palabra, Tramo


def palabras(n, paso=0.5):
    return [Palabra(f"p{i}", i * paso, i * paso + 0.4) for i in range(n)]


def propuesta(**cambios):
    base = dict(texto_portada="hola", textos_detras=[], escenas=[], enfasis=[], cierre=("t", "$1", "ya"))
    base.update(cambios)
    return Propuesta(**base)


def test_respeta_el_maximo_de_textos_detras_del_look():
    ps = palabras(40)
    textos = [(["uno"], 0, 4), (["dos"], 12, 16), (["tres"], 24, 28)]
    assert len(armar_plan(propuesta(textos_detras=textos), ps, LOOKS["directo"], []).textos_detras) == 1
    assert len(armar_plan(propuesta(textos_detras=textos), ps, LOOKS["anuncio"], []).textos_detras) == 2
    assert armar_plan(propuesta(textos_detras=textos), ps, LOOKS["premium"], []).textos_detras == []


def test_texto_detras_dura_entre_1_2_y_3_segundos():
    ps = palabras(40)
    corto, largo = armar_plan(propuesta(textos_detras=[(["a"], 0, 0), (["b"], 10, 30)]), ps,
                              LOOKS["anuncio"], []).textos_detras
    assert abs((corto.fin - corto.inicio) - 1.2) < 1e-9
    assert abs((largo.fin - largo.inicio) - 3.0) < 1e-9


def test_las_escenas_no_tapan_el_gancho_ni_chocan_con_otros_efectos():
    ps = palabras(40)
    plan = armar_plan(propuesta(textos_detras=[(["a"], 8, 10)], escenas=[("x", 0), ("y", 9), ("z", 20)]),
                      ps, LOOKS["anuncio"], [])
    assert [e.prompt for e in plan.escenas] == ["x", "z"]
    assert plan.escenas[0].inicio == 1.5


def test_descarta_indices_fuera_de_rango():
    plan = armar_plan(propuesta(textos_detras=[(["a"], 3, 99)], escenas=[("x", 99)], enfasis=[1, 99]),
                      palabras(10), LOOKS["anuncio"], [])
    assert plan.textos_detras == [] and plan.escenas == []
    assert [p.texto for p in plan.enfasis] == ["p1"]


def test_zoom_alterno_centrado_hacia_el_producto_sin_salirse():
    tramos = [Tramo(0, 1), Tramo(1, 2), Tramo(2, 3)]
    cajas = {1.5: Caja(900, 1700, 1080, 1920)}
    abierto, cerrado, otro = centros_de_zoom(tramos, cajas, LOOKS["directo"])
    assert abierto == (1.0, 540, 960) and otro[0] == 1.0
    zoom, x, y = cerrado
    assert zoom == 1.12
    assert x + 1080 / zoom / 2 <= 1080 and y + 1920 / zoom / 2 <= 1920
    assert x > 540 and y > 960


def test_premium_no_hace_zoom():
    assert all(z == 1.0 for z, _, _ in centros_de_zoom([Tramo(0, 1), Tramo(1, 2)], {}, LOOKS["premium"]))


def test_correcciones_solo_de_ortografia():
    from camtoshop.dominio.direccion import correcciones_validas
    ps = [Palabra("reciclabes", 0, 1), Palabra("vela", 1, 2), Palabra("bonita", 2, 3)]
    assert correcciones_validas(ps, {0: "reciclables", 1: "lámpara", 2: "muy bonita", 9: "x"}) == {0: "reciclables"}

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from camtoshop.adaptadores.director_arte import DirectorMuse, _plan_de
from camtoshop.adaptadores.render_dirigido import TRANSICION, RenderizadorDirigido, colorear
from camtoshop.dominio.estilos import ESTILO_INICIAL, ESTILOS, PULSOS, estilo_de
from camtoshop.dominio.marca import FUENTES, MUSICAS, Marca, tema_de, validar_marca
from camtoshop.dominio.producto import Analisis, Precio
from camtoshop.dominio.reel_fotos import Guion, PuertosFotos, armar_tomas, reel_desde_fotos


def test_hay_al_menos_diez_estilos_distintos():
    assert len(ESTILOS) >= 10
    assert len({(e.transicion, e.texto, e.color, e.ritmo) for e in ESTILOS.values()}) == len(ESTILOS)
    assert len({e.arte for e in ESTILOS.values()}) == len(ESTILOS)


def test_cada_estilo_sugiere_opciones_que_existen():
    for e in ESTILOS.values():
        assert e.fuente in FUENTES and e.musica in MUSICAS and e.musica in PULSOS and e.transicion in TRANSICION


def test_los_estilos_antiguos_pasan_al_catalogo_nuevo():
    assert Marca(estilo="impacto").estilo == "oferta"
    assert estilo_de("limpio").id == "revista"
    assert estilo_de("otro").id == ESTILO_INICIAL
    assert validar_marca({"estilo": "color", "fuente": "barlow", "primario": "#FFD23F", "secundario": "#141414",
                          "musica": "pulso"}).estilo == "estudio"


def test_el_ritmo_cambia_la_duracion_y_los_cortes_caen_en_el_pulso():
    g = Guion("Gancho", ["uno", "dos", "tres"], "Compra")
    lento = armar_tomas(g, 1, 0, Precio(1000, "COP"), ritmo=1.2)
    rapido = armar_tomas(g, 1, 0, Precio(1000, "COP"), ritmo=.7, pulso=.5)
    assert rapido[-1].fin < lento[-1].fin
    assert all(abs(t.fin / .5 - round(t.fin / .5)) < 1e-6 for t in rapido)


def test_el_texto_conserva_mayusculas_y_tildes_cuando_el_estilo_lo_pide():
    t = armar_tomas(Guion("Hecho en Medellín", [], "Compra"), 1, 0, None, mayusculas=False)
    assert " ".join(t[0].lineas) == "Hecho en Medellín"


def test_el_plan_se_lee_aunque_venga_con_texto_alrededor():
    assert _plan_de('```json\n{"planos": ["uno", "dos"]}\n```') == ["uno", "dos"]
    with pytest.raises(ValueError):
        _plan_de('{"planos": []}')


class ClienteFalso:
    def __init__(self):
        self.textos, self.imagenes = 0, 0

    def preguntar(self, *a, **k):
        self.textos += 1
        return json.dumps({"planos": ["a", "b", "c", "d"]})

    def editar_imagen(self, prompt, referencias, destino, tamano):
        self.imagenes += 1
        Image.new("RGB", (64, 96)).save(destino, "PNG")
        return destino


ANALISIS = Analisis("Florero", "", "hogar", [], "", "", ["vase"], "es", 0.0, "")


def test_los_planos_de_un_estilo_no_se_pagan_dos_veces(tmp_path):
    foto = tmp_path / "f.jpg"
    Image.new("RGB", (64, 64)).save(foto)
    c = ClienteFalso()
    g = Guion("G", ["a", "b", "c"], "L")
    for _ in range(2):
        planos = DirectorMuse(c, tmp_path / "p", ESTILOS["noche"], Marca()).planos(ANALISIS, g, foto, None)
    assert len(planos) == 4 and c.textos == 1 and c.imagenes == 4


class Falso:
    def __init__(self, error=False):
        self.error, self.tomas = error, None

    def guion(self, *a):
        return Guion("Gancho", ["uno", "dos", "tres"], "Compra")

    def planos(self, *a):
        if self.error:
            raise RuntimeError("sin cupo")
        return [Path("p.png")] * 4

    def render(self, tomas, fotos, recortes, escenas, voz, destino, nombre=""):
        self.tomas, self.escenas = tomas, escenas


@pytest.mark.parametrize("error,planos", [(False, 4), (True, 0)])
def test_sin_planos_el_reel_sale_igual_con_las_fotos_reales(error, planos):
    f = Falso(error)
    r = reel_desde_fotos(ANALISIS, "", [Path("f.jpg")], [None], None, None, None, Path("r.mp4"),
                         PuertosFotos(f, None, f, None, f, {"ritmo": .8}), rondas=0)
    assert len(f.escenas) == planos and r.reel == Path("r.mp4")
    assert not any(t.tipo == "escena" for t in f.tomas)


@pytest.mark.parametrize("color", ["natural", "calido", "bn", "vivo", "neon", "lavado"])
def test_cada_color_conserva_el_tamano(color):
    assert colorear(Image.new("RGB", (8, 8), (120, 80, 40)), color).size == (8, 8)


@pytest.mark.parametrize("id_estilo", list(ESTILOS))
def test_cada_estilo_pinta_sus_cuadros(id_estilo, tmp_path):
    plano, recorte = tmp_path / "p.png", tmp_path / "r.png"
    Image.new("RGB", (200, 300), (90, 120, 150)).save(plano)
    Image.new("RGBA", (100, 200), (200, 50, 50, 255)).save(recorte)
    m = Marca(estilo=id_estilo, fuente=ESTILOS[id_estilo].fuente)
    render = RenderizadorDirigido(None, [], tema_de(m), None, None, id_estilo, m.primario, "Mi tienda")
    g = Guion("Una frase bastante larga para probar el corte", ["Hecho en Medellín", "dos", "tres"], "Compra hoy")
    tomas = armar_tomas(g, 1, 0, Precio(85000, "COP"), mayusculas=False)
    planos = render._planos(tomas, [plano], [recorte], [plano] * 4, "Florero")
    for n, (p, toma) in enumerate(zip(planos, tomas)):
        a = render._cuadro(p, toma, n, 0.5)
        assert a.shape == (1920, 1080, 3) and np.isfinite(a).all()
        if n:
            assert render._transicion(a, lambda: a, 0).shape == a.shape

import pytest

from camtoshop.dominio.producto import Precio
from camtoshop.dominio.reel_fotos import (
    DURACION, Guion, armar_tomas, dicho_en, limpiar_guion, lineas_de, montos_en, precio_respaldado,
)

FUENTE = "Vela de soya hecha a mano en Medellín, aroma a lavanda. 85 mil pesos."


def guion(**cambios):
    base = dict(gancho="¿Tu casa huele a encierro?",
                beneficios=["Aroma a lavanda", "Hecha a mano", "Envío gratis a todo el país"],
                llamado="Pídela por WhatsApp", escenas=["candle on a nightstand", "bath", "extra"])
    base.update(cambios)
    return Guion(**base)


def test_quita_promesas_que_el_comerciante_no_dijo():
    limpio, avisos = limpiar_guion(guion(), FUENTE)
    assert limpio.beneficios == ["Aroma a lavanda", "Hecha a mano"]
    assert any("Envío gratis" in a for a in avisos)
    assert len(limpio.escenas) == 2


def test_promesa_dicha_se_conserva_sin_importar_tildes():
    assert dicho_en("Envío gratis hoy", "hago envio gratis en Medellín")
    assert not dicho_en("100% orgánica", FUENTE)


def test_recorta_textos_largos():
    limpio, _ = limpiar_guion(guion(gancho="Esta es la vela más bonita que vas a ver en toda tu vida",
                                    beneficios=["Aroma suave que dura muchas horas en tu cuarto"]), FUENTE)
    assert len(limpio.gancho.split()) <= 6
    assert limpio.beneficios == ["Aroma suave que dura"]


def test_gancho_con_promesa_falsa_se_reemplaza():
    limpio, avisos = limpiar_guion(guion(gancho="Envío gratis hoy"), FUENTE)
    assert limpio.gancho == "Aroma a lavanda" and avisos


@pytest.mark.parametrize("texto, monto", [
    ("85 mil", 85000), ("$85.000", 85000), ("85,000 pesos", 85000), ("US$49.90", 49.9),
    ("1,5 millones", 1_500_000), ("precio 120k", 120000),
])
def test_montos_escritos_de_muchas_formas(texto, monto):
    assert monto in montos_en(texto)


def test_precio_solo_si_el_comerciante_lo_dio():
    assert precio_respaldado(Precio(85000, "COP"), FUENTE)
    assert not precio_respaldado(Precio(90000, "COP"), FUENTE)
    assert not precio_respaldado(None, FUENTE)


def test_lineas_parejas_y_maximo_tres():
    assert lineas_de("aroma a lavanda") == ("AROMA A", "LAVANDA")
    assert lineas_de("dura 40 horas") == ("DURA 40 HORAS",)
    assert len(lineas_de("una frase con muchas palabras para partir en pedazos")) <= 3


def test_tomas_en_orden_y_duracion_de_reel():
    limpio, _ = limpiar_guion(guion(beneficios=["Aroma a lavanda", "Hecha a mano", "Dura 40 horas"]), FUENTE)
    tomas = armar_tomas(limpio, fotos=3, escenas=2, precio=Precio(85000, "COP"))
    assert [t.tipo for t in tomas] == ["gancho", "beneficio", "escena", "beneficio", "precio", "cierre"]
    assert tomas[0].inicio == 0 and all(a.fin == b.inicio for a, b in zip(tomas, tomas[1:]))
    assert DURACION[0] <= tomas[-1].fin <= 15
    assert tomas[4].lineas == ("$85.000",)
    assert tomas[0].movimiento != tomas[1].movimiento


def test_sin_precio_no_hay_toma_de_precio_y_fotos_se_repiten():
    tomas = armar_tomas(guion(beneficios=["a", "b", "c"]), fotos=1, escenas=0, precio=None)
    assert "precio" not in [t.tipo for t in tomas]
    assert {t.imagen for t in tomas} == {0}


def test_con_nota_de_voz_dura_lo_que_dura_la_voz():
    tomas = armar_tomas(guion(), fotos=2, escenas=1, precio=Precio(85000, "COP"), duracion_voz=16.0)
    assert abs(tomas[-1].fin - 16.6) < 0.01
    tomas = armar_tomas(guion(), fotos=2, escenas=1, precio=None, duracion_voz=60.0)
    assert tomas[-1].fin <= DURACION[1] + 0.01


def test_sin_fotos_es_un_error():
    with pytest.raises(ValueError):
        armar_tomas(guion(), fotos=0, escenas=0, precio=None)


# --- Caso de uso con adaptadores falsos ------------------------------------------

from pathlib import Path

from camtoshop.dominio.producto import Analisis
from camtoshop.dominio.reel_fotos import PuertosFotos, reel_desde_fotos

ANALISIS = Analisis("Vela", "", "Velas", [], "", "85 mil", ["candle"], "es", 1.0, "")


class GuionistaFalso:
    def __init__(self):
        self.llamadas = []

    def guion(self, analisis, texto, foto, pedido="", anterior=None, problemas=None):
        self.llamadas.append((foto, pedido, problemas))
        if problemas:
            return Guion("Aroma que relaja", ["Aroma a lavanda", "Hecha a mano"], "Pídela ya", ["desk"])
        return Guion("Envío gratis hoy", ["Aroma a lavanda", "Hecha a mano", "Dura 40 horas"], "Pídela", ["desk"])


class Escenografo:
    def __init__(self):
        self.pedidas = []

    def escena(self, descripcion, recorte):
        self.pedidas.append((descripcion, recorte))
        return Path("escena.png")


class Render:
    def __init__(self):
        self.renders = []

    def render(self, tomas, fotos, recortes, escenas, voz, destino, nombre=""):
        self.renders.append(tomas)
        return destino


class RevisorExigente:
    """Rechaza la primera versión y aprueba la corregida."""

    def __init__(self):
        self.vistas = 0

    def revisar(self, reel, guion, precio):
        self.vistas += 1
        return self.vistas > 1, ["Gancho débil"], "Mejorable"


def test_caso_de_uso_completo_con_revision():
    g, e, r = GuionistaFalso(), Escenografo(), Render()
    res = reel_desde_fotos(ANALISIS, FUENTE, ["f0", "f1"], [None, "recorte1"], Precio(85000, "COP"), None, None,
                           Path("reel.mp4"), PuertosFotos(g, e, r, RevisorExigente()), rondas=1)
    assert g.llamadas[0][0] == "f1"  # la mejor foto según el análisis
    assert e.pedidas == [("desk", "recorte1")]  # escena desde el recorte real
    assert len(r.renders) == 2 and g.llamadas[1][2] == ["Gancho débil"]
    assert res.guion.gancho == "Aroma que relaja"
    assert any("Envío gratis" in a or "gancho" in a for a in res.avisos)


def test_sin_recorte_no_hay_escenas_inventadas():
    e, r = Escenografo(), Render()
    reel_desde_fotos(ANALISIS, FUENTE, ["f0"], [None], None, None, None, Path("x.mp4"),
                     PuertosFotos(GuionistaFalso(), e, r))
    assert e.pedidas == [] and "escena" not in [t.tipo for t in r.renders[0]]

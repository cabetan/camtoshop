from pathlib import Path

from camtoshop.dominio.direccion import Propuesta, Revision
from camtoshop.dominio.editar_reel import Puertos, editar_reel, preparar_montaje, dirigir_y_revisar, rehacer
from camtoshop.dominio.direccion import LOOKS
from camtoshop.dominio.reel import (
    Caja, Palabra, Tramo, a_linea_del_reel, al_original, armar_bloques, indices_conservados,
    palabras_del_reel, posicion_subtitulo, tramos_desde_palabras,
)


def frase(*textos, inicio=0.0, paso=0.5, pausas=None):
    """Palabras de 0,4 s separadas por 0,1 s; `pausas` añade silencio antes de un índice."""
    pausas = pausas or {}
    palabras, t = [], inicio
    for i, texto in enumerate(textos):
        t += pausas.get(i, 0.0)
        palabras.append(Palabra(texto, t, t + paso - 0.1))
        t += paso
    return palabras


def test_indices_conservados_limpia_rangos_desordenados_y_fuera_de_limite():
    assert indices_conservados([(5, 3), (4, 6), (8, 99)], total=10) == [3, 4, 5, 6, 8, 9]


def test_quita_la_toma_fallida_con_un_solo_corte():
    # "esta vela perdón me equivoqué esta vela es especial"
    palabras = frase("esta", "vela", "perdón", "me", "equivoqué", "esta", "vela", "es", "especial")
    tramos = tramos_desde_palabras(palabras, [5, 6, 7, 8])
    assert tramos == [Tramo(palabras[5].inicio - 0.08, palabras[8].fin + 0.08)]


def test_el_margen_no_invade_la_palabra_descartada_vecina():
    palabras = [Palabra("uno", 0.0, 0.40), Palabra("dos", 0.42, 0.80), Palabra("tres", 0.82, 1.2)]
    [tramo] = tramos_desde_palabras(palabras, [1])
    assert tramo.inicio == palabras[0].fin
    assert tramo.fin == palabras[2].inicio


def test_recorta_las_pausas_largas():
    palabras = frase("hola", "a", "todos", pausas={2: 1.5})
    tramos = tramos_desde_palabras(palabras, [0, 1, 2])
    assert len(tramos) == 2
    assert sum(t.duracion for t in tramos) < palabras[-1].fin - palabras[0].inicio - 1.0


def test_descarta_islas_demasiado_cortas():
    palabras = [Palabra("eh", 1.0, 1.02), Palabra("bien", 3.0, 3.4)]
    assert tramos_desde_palabras(palabras, [0, 1], margen=0.0) == [Tramo(3.0, 3.4)]


def test_tiempos_se_traducen_en_ambos_sentidos():
    tramos = [Tramo(2.0, 4.0), Tramo(10.0, 11.0)]
    assert a_linea_del_reel(10.5, tramos) == 2.5
    assert a_linea_del_reel(6.0, tramos) is None
    assert al_original(2.5, tramos) == 10.5


def test_palabras_del_reel_quedan_en_la_nueva_linea_de_tiempo():
    palabras = frase("mal", "bien", pausas={1: 3.0})
    tramos = tramos_desde_palabras(palabras, [1])
    [p] = palabras_del_reel(palabras, [1], tramos)
    assert p.texto == "bien"
    assert abs(p.inicio - 0.08) < 1e-9


def test_bloques_cortan_en_puntuacion_y_en_largo():
    bloques = armar_bloques(frase("Hola,", "les", "quiero", "mostrar", "esta", "vela."))
    assert [b.texto for b in bloques] == ["Hola,", "les quiero", "mostrar esta", "vela."]


def test_subtitulo_va_debajo_del_producto_si_cabe():
    y = posicion_subtitulo(Caja(300, 600, 800, 1000), alto_bloque=150)
    assert y == 1030


def test_subtitulo_sube_cuando_el_producto_esta_abajo():
    y = posicion_subtitulo(Caja(300, 1100, 800, 1500), alto_bloque=150)
    assert y + 150 <= 1100


def test_subtitulo_sin_producto_va_al_fondo_de_la_zona_segura():
    assert posicion_subtitulo(None, alto_bloque=150) == 1920 * 0.80 - 150


class TranscriptorFalso:
    def transcribir(self, video, idioma):
        return [(0.0, 5.0, "esta vela perdón esta vela es especial")]


class AlineadorFalso:
    def alinear(self, video, turnos, idioma):
        return frase(*turnos[0][2].split())


class EditorFalso:
    def elegir(self, palabras, idioma):
        return [(3, 6)]


class RastreadorFalso:
    def cajas(self, video):
        return {t / 2: Caja(300, 1100, 800, 1500) for t in range(10)}


class RenderizadorFalso:
    def __init__(self):
        self.llamadas = []

    def render(self, video, tramos, bloques, posiciones, plan, destino):
        self.llamadas.append((tramos, bloques, posiciones, plan))
        return destino


class DirectorFalso:
    def proponer(self, palabras, producto, look, idioma):
        return Propuesta("vela de madres", [(["hecha", "en Medellín"], 0, 3)], [("candle lit", 2)],
                         [1], ("Vela", "$85.000", "Cómprala"))

    def ajustar(self, propuesta, pedido, palabras, producto, look, idioma):
        return Propuesta("vela", [], [], [], propuesta.cierre), "premium"


class RevisorExigente:
    """Rechaza la primera versión y aprueba la segunda."""

    def __init__(self):
        self.vistas = 0

    def revisar(self, reel, propuesta, palabras, look, idioma):
        self.vistas += 1
        if self.vistas == 1:
            corregida = Propuesta("vela", propuesta.textos_detras, [], propuesta.enfasis, propuesta.cierre)
            return Revision(False, ["la escena tapa el precio"], propuesta=corregida)
        return Revision(True, [], "bien")


class IlustradorFalso:
    def portada(self, texto):
        return Path("portada.png")

    def escena(self, prompt):
        return Path(f"{prompt}.png")

    def cierre(self, titulo, precio, llamado):
        return Path("cierre.png")


def test_editar_reel_de_punta_a_punta_con_adaptadores_falsos():
    render = RenderizadorFalso()
    puertos = Puertos(TranscriptorFalso(), AlineadorFalso(), EditorFalso(), RastreadorFalso(),
                      DirectorFalso(), IlustradorFalso(), render)
    r = editar_reel(Path("v.mov"), "es", {}, Path("reel.mp4"), puertos)
    assert " ".join(b.texto for b in r.bloques) == "esta vela es especial"
    assert len(r.tramos) == 1
    [(_, bloques, posiciones, plan)] = render.llamadas
    assert all(y + 150 <= 1100 for y in posiciones)  # nunca tapa el producto
    assert plan.textos_detras[0].lineas == ["HECHA", "EN MEDELLÍN"]
    assert plan.imagen_cierre == Path("cierre.png")


def puertos_falsos(revisor=None):
    return Puertos(TranscriptorFalso(), AlineadorFalso(), EditorFalso(), RastreadorFalso(),
                   DirectorFalso(), IlustradorFalso(), RenderizadorFalso(), revisor)


def test_el_revisor_corrige_y_se_vuelve_a_renderizar():
    p = puertos_falsos(RevisorExigente())
    m = preparar_montaje(Path("v.mov"), "es", p)
    r = dirigir_y_revisar(m, {}, LOOKS["directo"], Path("reel.mp4"), p, rondas=3)
    assert len(p.renderizador.llamadas) == 2
    assert r.plan.escenas == [] and r.propuesta.texto_portada == "vela"
    assert any("tapa el precio" in linea for linea in r.bitacora)
    assert r.bitacora[-1].startswith("Revisión aprobada")


def test_rehacer_aplica_el_pedido_y_cambia_de_look():
    p = puertos_falsos()
    m = preparar_montaje(Path("v.mov"), "es", p)
    primero = dirigir_y_revisar(m, {}, LOOKS["directo"], Path("reel.mp4"), p)
    nuevo = rehacer(m, primero, "más sobrio", {}, Path("reel2.mp4"), p)
    assert nuevo.plan.look.nombre == "premium" and nuevo.plan.textos_detras == []
    assert "más sobrio" in nuevo.bitacora[-1]


class RevisorCaido:
    def revisar(self, reel, propuesta, palabras, look, idioma):
        raise RuntimeError("sin respuesta")


def test_si_la_revision_falla_se_entrega_el_reel_renderizado():
    p = puertos_falsos(RevisorCaido())
    m = preparar_montaje(Path("v.mov"), "es", p)
    r = dirigir_y_revisar(m, {}, LOOKS["directo"], Path("reel.mp4"), p)
    assert r.reel == Path("reel.mp4") and len(p.renderizador.llamadas) == 1
    assert "Revisión no disponible" in r.bitacora[-1]

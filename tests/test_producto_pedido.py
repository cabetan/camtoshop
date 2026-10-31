from types import SimpleNamespace

from camtoshop.dominio.reel_fotos import Guion, PuertosFotos, reel_desde_fotos


def test_la_correccion_conserva_el_pedido():
    pedidos = []

    class Guionista:
        def guion(self, analisis, texto, foto, pedido, anterior=None, problemas=None):
            pedidos.append(pedido)
            return Guion("Solo 45 mil", ["vela"], "Pide", [])

    class Render:
        def render(self, *a):
            pass

    class Revisor:
        def revisar(self, *a):
            return False, ["texto mal"], "revisar"

    analisis = SimpleNamespace(mejor_cuadro_s=0, texto_etiqueta="", nombre="Vela")
    reel_desde_fotos(analisis, "vela 45 mil solo pide", ["f"], [None], None, None, None, "d",
                     PuertosFotos(Guionista(), None, Render(), Revisor()), pedido="Open with the price.", rondas=1)
    assert pedidos == ["Open with the price.", "Open with the price."]


def test_gancho_con_precio_conserva_el_precio_real():
    from camtoshop.dominio.agente_diario import estilo_de
    from camtoshop.dominio.producto import Precio
    from camtoshop.dominio.reel_fotos import gancho_con_precio

    g = gancho_con_precio(Guion("Audífonos JBL negros de diadema?", [], "", []), "Audífonos JBL negros de diadema",
                          Precio(250000, "COP"))
    assert "250" in g.gancho and estilo_de(g.gancho) == "precio" and "?" not in g.gancho

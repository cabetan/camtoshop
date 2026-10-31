from camtoshop.dominio.marca import Marca, contraste, tema_de


def test_el_texto_se_lee_aunque_el_color_de_marca_sea_claro():
    tema = tema_de(Marca(estilo="color", primario="#FFF7D6", secundario="#FFFFFF"))
    assert contraste(tema.texto, tema.fondo) >= 4.5
    assert contraste(tema.acento, tema.fondo) >= 2.5


def test_estilo_limpio_cambia_un_acento_invisible():
    tema = tema_de(Marca(estilo="limpio", primario="#FFEFA0", secundario="#FFFFFF"))
    assert contraste(tema.acento, tema.fondo) >= 2.5


def test_sobre_foto_nunca_queda_un_acento_oscuro():
    assert contraste(tema_de(Marca(primario="#3A0A0A", secundario="#102040")).acento_foto, "#141414") >= 4.5


def test_estilo_impacto_usa_la_foto_de_fondo():
    assert tema_de(Marca()).fondo == ""

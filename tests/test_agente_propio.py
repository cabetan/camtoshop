import json
from pathlib import Path

from camtoshop.aplicacion.servicio import Servicio
from camtoshop.dominio.comercio import Comercio


def proyecto(raiz: Path, nombre: str, comercio="c1", fase="listo", titulo="Vela de soya", publicado=None):
    carpeta = raiz / nombre
    (carpeta / "material").mkdir(parents=True)
    (carpeta / "material" / "foto_1.jpg").write_bytes(b"x")
    estado = {"id": nombre, "fase": fase, "tipo": "fotos", "comercio_id": comercio, "texto": f"{titulo}, 85 mil",
              "analisis": {"nombre": titulo}, "fotos_material": ["foto_1.jpg"], "reels": {}, "pasos": [], "creado": 1,
              "publicaciones": []}
    if publicado:
        estado["publicaciones"] = [{"t": publicado, "resultados": [{"ok": True, "canal": "instagram"}]}]
    (carpeta / "estado.json").write_text(json.dumps(estado))


def montar(tmp_path):
    raiz = tmp_path / "proyectos"
    raiz.mkdir()
    return Servicio(raiz), raiz


def test_un_producto_por_nombre_y_solo_del_comercio(tmp_path):
    s, raiz = montar(tmp_path)
    proyecto(raiz, "20261030-a")
    proyecto(raiz, "20261031-b")
    proyecto(raiz, "20261031-c", comercio="otro", titulo="Ajeno")
    proyecto(raiz, "20261031-d", fase="error", titulo="Fallido")
    propios = s._productos_propios("c1")
    assert list(propios) == ["vela-de-soya"] and propios["vela-de-soya"][1].id == "20261031-b"


def test_lo_publicado_cuenta_como_promovido(tmp_path):
    s, raiz = montar(tmp_path)
    proyecto(raiz, "20261031-a", publicado=1793000000)
    assert "vela-de-soya" in s.promovidos_de(Comercio("c1", "Velas", "a@b.co"))


def test_variantes_del_nombre_son_el_mismo_producto(tmp_path):
    s, raiz = montar(tmp_path)
    proyecto(raiz, "20261031-a", titulo="Florero de cerámica verde con ramas de flores")
    proyecto(raiz, "20261031-b", titulo="Florero de cerámica verde")
    assert list(s._productos_propios("c1")) == ["florero-de-cerámica"]

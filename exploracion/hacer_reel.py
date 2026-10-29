"""Arma el Reel de cada video de prueba (exploración).

Uso: python exploracion/hacer_reel.py directo|anuncio|premium IMG_7568 [IMG_7569 ...]
Usa el análisis de flujo_videos.py (idioma, conceptos para SAM, marca) y guarda en
caché cada respuesta de la API para no pagar dos veces al ajustar el render.
"""

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from camtoshop.adaptadores.alineador_xlsr import AlineadorXLSR  # noqa: E402
from camtoshop.adaptadores.meta_api import ClienteMeta  # noqa: E402
from camtoshop.adaptadores.reel_meta import (  # noqa: E402
    DirectorSpark, EditorSpark, IlustradorMuse, RastreadorSAM, TranscriptorMeta,
)
from camtoshop.adaptadores.render_ffmpeg import RenderizadorFFmpeg  # noqa: E402
from camtoshop.adaptadores.sam_mascaras import mascaras  # noqa: E402
from camtoshop.dominio.direccion import LOOKS, Propuesta  # noqa: E402
from camtoshop.dominio.editar_reel import Puertos, editar_reel  # noqa: E402
from camtoshop.dominio.reel import Caja, Palabra  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
SALIDA = Path(__file__).parent / "salida" / "videos"


class EnCache:
    """Envuelve un adaptador y guarda su respuesta en JSON."""

    def __init__(self, adaptador, archivo: Path, metodo: str, a_json, de_json):
        self._adaptador, self._archivo, self._metodo = adaptador, archivo, metodo
        self._a_json, self._de_json = a_json, de_json

    def __getattr__(self, nombre):
        if nombre != self._metodo:
            return getattr(self._adaptador, nombre)

        def llamar(*args):
            if self._archivo.exists():
                return self._de_json(json.loads(self._archivo.read_text()))
            t = time.time()
            r = getattr(self._adaptador, nombre)(*args)
            print(f"  [{type(self._adaptador).__name__}] {time.time() - t:.1f} s")
            self._archivo.write_text(json.dumps(self._a_json(r), ensure_ascii=False, indent=1))
            return r
        return llamar


def palabras_json(ps):
    return [asdict(p) for p in ps]


def palabras_de_json(d):
    return [Palabra(**p) for p in d]


def main():
    cliente = ClienteMeta()
    alineador = AlineadorXLSR()
    look = LOOKS[sys.argv[1]]
    for nombre in sys.argv[2:]:
        print(f"\n=== {nombre} ({look.nombre}) ===")
        carpeta = SALIDA / nombre
        analisis = json.loads((carpeta / "analisis.json").read_text())
        producto = analisis["producto"]
        idioma = analisis["idioma"]
        clave = [producto["marca"]] if producto["marca"] else None
        video = RAIZ / "videos" / "originales" / f"{nombre}.MOV"
        conceptos = producto["conceptos_sam"] + ["object held in hands"]

        rastreador = EnCache(RastreadorSAM(cliente, conceptos), carpeta / "cajas.json", "cajas",
                             lambda d: {str(k): asdict(v) for k, v in d.items()},
                             lambda d: {float(k): Caja(**v) for k, v in d.items()})
        segmentar = lambda concepto, clip, fuente, salida: mascaras(cliente, concepto, clip, fuente, salida)  # noqa: E731
        puertos = Puertos(
            transcriptor=EnCache(TranscriptorMeta(cliente, clave), carpeta / "turnos.json", "transcribir",
                                 lambda x: x, lambda d: [tuple(x) for x in d]),
            alineador=EnCache(alineador, carpeta / "palabras.json", "alinear", palabras_json, palabras_de_json),
            editor=EnCache(EditorSpark(cliente), carpeta / "edicion.json", "elegir",
                           lambda x: x, lambda d: [tuple(x) for x in d]),
            rastreador=rastreador,
            director=EnCache(DirectorSpark(cliente), carpeta / f"direccion_{look.nombre}.json", "proponer",
                             asdict, lambda d: Propuesta(**d)),
            ilustrador=IlustradorMuse(cliente, carpeta / "catalogo.png", carpeta / "insertos"),
            renderizador=RenderizadorFFmpeg(RAIZ / "videos" / "maestros", segmentar,
                                            ["person", producto["conceptos_sam"][0]]),
        )
        t = time.time()
        r = editar_reel(video, idioma, producto, carpeta / f"reel_{look.nombre}.mp4", puertos, look)
        descartadas = [p.texto for i, p in enumerate(r.palabras) if i not in set(r.conservadas)]
        print(f"  {len(r.palabras)} palabras, {len(descartadas)} descartadas: {' '.join(descartadas)}")
        print(f"  Plan: portada '{r.plan.texto_portada}', textos {[e.lineas for e in r.plan.textos_detras]}, "
              f"{len(r.plan.escenas)} escenas, cierre {r.plan.cierre}")
        print(f"  Reel {r.duracion:.1f} s + cierre; total {time.time() - t:.0f} s -> {r.reel}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Hace la muestra de cada estilo con el florero de la demo, con los mismos adaptadores del producto.

Los planos quedan en una carpeta de trabajo y no se repiten; las muestras van a estatico/demo/estilos.
Uso: .venv/bin/python scripts/hacer_muestras.py carpeta_de_trabajo [estilo ...]
"""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from PIL import Image

from camtoshop.adaptadores.director_arte import DirectorMuse
from camtoshop.adaptadores.meta_api import ClienteMeta
from camtoshop.adaptadores.render_dirigido import RenderizadorDirigido
from camtoshop.dominio.estilos import ESTILOS, PULSOS
from camtoshop.dominio.marca import Marca, tema_de
from camtoshop.dominio.producto import Analisis, Precio
from camtoshop.dominio.reel_fotos import Guion, armar_tomas

ESTATICO = RAIZ / "camtoshop" / "web" / "estatico" / "demo"
MUSICA = RAIZ / "camtoshop" / "assets" / "musica"
ANALISIS = Analisis("Florero de cerámica", "", "decoración", ["cerámica", "hecho para flores frescas"], "", "",
                    ["vase"], "es", 0.0, "")
GUIONES = {"es": Guion("Tu mesa pedía esto", ["Cerámica de verdad", "Para flores frescas", "Una pieza que se nota"], "Pídelo por DM"),
           "en": Guion("Your table asked for this", ["Real ceramic", "Made for fresh flowers", "A piece people notice"], "Order by DM")}
PRECIO = Precio(200000, "COP")


def muestra(id_estilo: str, trabajo: Path, foto: Path, recorte: Path):
    estilo = ESTILOS[id_estilo]
    marca = Marca(estilo=id_estilo, fuente=estilo.fuente, primario="#FFD23F", secundario="#141414", musica=estilo.musica)
    planos = DirectorMuse(ClienteMeta(), trabajo, estilo, marca, "Camtoshop").planos(ANALISIS, GUIONES["es"], foto, recorte)
    for idioma, guion in GUIONES.items():
        render = RenderizadorDirigido(None, [], tema_de(marca), None, MUSICA / f"{marca.musica}.m4a", estilo, marca.primario, "Camtoshop")
        tomas = armar_tomas(guion, 1, 0, PRECIO, ritmo=estilo.ritmo, pulso=PULSOS[marca.musica], mayusculas=False)
        completo = trabajo / id_estilo / f"reel_{idioma}.mp4"
        render.render(tomas, [foto], [recorte], planos, None, completo, ANALISIS.nombre)
        salida = ESTATICO / "estilos" / idioma
        salida.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(completo), "-vf", "scale=540:960", "-c:v", "libx264",
                        "-crf", "27", "-preset", "slow", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart",
                        str(salida / f"{id_estilo}.mp4")], check=True)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "1.2", "-i", str(completo), "-frames:v", "1",
                        "-vf", "scale=360:640", "-q:v", "5", str(salida / f"{id_estilo}.jpg")], check=True)
    print("listo", id_estilo, flush=True)


if __name__ == "__main__":
    trabajo = Path(sys.argv[1])
    trabajo.mkdir(parents=True, exist_ok=True)
    recorte = ESTATICO / "producto.png"
    foto = trabajo / "florero.jpg"
    original = Image.open(recorte).convert("RGBA")
    fondo = Image.new("RGBA", original.size, (255, 255, 255, 255))
    fondo.alpha_composite(original)
    fondo.convert("RGB").save(foto, quality=92)
    with ThreadPoolExecutor(max_workers=3) as hilos:
        for f in [hilos.submit(muestra, e, trabajo, foto, recorte) for e in sys.argv[2:] or ESTILOS]:
            f.result()

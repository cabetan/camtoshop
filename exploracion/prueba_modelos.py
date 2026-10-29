"""Prueba rápida de los modelos de Meta antes de construir (exploración, desechable).

1. Muse Image genera una foto "de celular" de un producto.
2. Muse Spark identifica el producto y propone el concepto para SAM.
3. SAM 3.1 encuentra el producto en la imagen y en un video corto.
4. Muse Spark ve el video.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from camtoshop.adaptadores.meta_api import ClienteMeta  # noqa: E402

SALIDA = Path(__file__).parent / "salida"
SALIDA.mkdir(exist_ok=True)

ESQUEMA_PRODUCTO = {
    "type": "object",
    "properties": {
        "nombre": {"type": "string"},
        "concepto_sam": {"type": "string", "description": "Short English noun phrase naming the product, 1-4 words"},
        "atributos": {"type": "array", "items": {"type": "string"}},
        "categoria": {"type": "string"},
    },
    "required": ["nombre", "concepto_sam", "atributos", "categoria"],
    "additionalProperties": False,
}


def cronometro(nombre, fn):
    t = time.time()
    r = fn()
    print(f"[{nombre}] {time.time() - t:.1f} s")
    return r


def main():
    meta = ClienteMeta()

    foto = SALIDA / "producto.png"
    if not foto.exists():
        cronometro("Muse Image", lambda: meta.generar_imagen(
            "Amateur smartphone photo, vertical, of a hand holding a matte blue ceramic coffee mug "
            "with a small white logo, in a small Latin American shop, natural light, slightly messy background",
            foto, "1024x1536"))

    info = json.loads(cronometro("Muse Spark imagen", lambda: meta.preguntar(
        "muse-spark-1.3",
        [meta.parte_texto("You are cataloguing a product for an online store. Identify the main product held "
                          "or shown. Answer in JSON. 'nombre' and 'atributos' in Spanish; 'concepto_sam' in English."),
         meta.parte_imagen(foto)],
        esquema=ESQUEMA_PRODUCTO)))
    print(json.dumps(info, ensure_ascii=False, indent=2))

    cajas = cronometro("SAM imagen", lambda: meta.segmentar(info["concepto_sam"], foto))
    print("SAM imagen:", cajas)

    video = SALIDA / "producto.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(foto), "-vf",
                    "scale=720:1080,zoompan=z='min(zoom+0.003,1.3)':d=150:s=720x1080:fps=30",
                    "-t", "5", "-pix_fmt", "yuv420p", str(video)], check=True)

    cuadros = cronometro("SAM video", lambda: meta.segmentar(info["concepto_sam"], video))
    print(f"SAM video: {len(cuadros)} cuadros con producto; primero: {next(iter(cuadros.items()), None)}")

    print(cronometro("Muse Spark video", lambda: meta.preguntar(
        "muse-spark-1.3",
        [meta.parte_texto("Describe in Spanish, in two sentences, what product appears and how the camera moves."),
         meta.parte_video(video)])))


if __name__ == "__main__":
    main()

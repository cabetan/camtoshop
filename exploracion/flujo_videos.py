"""Flujo de prueba con videos reales (exploración).

Por cada video:
1. Muse Spark ve el video con audio: identifica el producto, lee la etiqueta,
   separa las tomas, elige la mejor y el mejor instante para la foto.
2. SAM 3.1 sigue el producto a lo largo del video (versión a 6 cuadros/s).
3. Se extrae el mejor cuadro del original en 4K, SAM recorta el producto y
   Muse Image lo convierte en foto de catálogo de estudio.

Uso: python exploracion/flujo_videos.py IMG_7568 [IMG_7569 ...]
Espera los videos en videos/proxy/<nombre>.mp4, <nombre>_sam.mp4 y videos/originales/<nombre>.MOV.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from camtoshop.adaptadores.meta_api import ClienteMeta  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
VIDEOS = RAIZ / "videos"
SALIDA = Path(__file__).parent / "salida" / "videos"

ESQUEMA_ANALISIS = {
    "type": "object",
    "properties": {
        "producto": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string"},
                "marca": {"type": "string"},
                "conceptos_sam": {"type": "array", "items": {"type": "string"},
                                  "description": "3 short English noun phrases for the product, from specific to generic"},
                "categoria": {"type": "string"},
                "atributos": {"type": "array", "items": {"type": "string"}},
                "texto_etiqueta": {"type": "string", "description": "Text read on the label or packaging, empty if none"},
                "precio_mencionado": {"type": "string"},
            },
            "required": ["nombre", "marca", "conceptos_sam", "categoria", "atributos", "texto_etiqueta", "precio_mencionado"],
            "additionalProperties": False,
        },
        "idioma": {"type": "string"},
        "tomas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "inicio_s": {"type": "number"},
                    "fin_s": {"type": "number"},
                    "texto": {"type": "string"},
                    "conservar": {"type": "boolean"},
                    "motivo": {"type": "string"},
                },
                "required": ["inicio_s", "fin_s", "texto", "conservar", "motivo"],
                "additionalProperties": False,
            },
        },
        "mejor_cuadro_s": {"type": "number", "description": "Second where the whole product is most clearly visible"},
        "gancho_reel": {"type": "string"},
    },
    "required": ["producto", "idioma", "tomas", "mejor_cuadro_s", "gancho_reel"],
    "additionalProperties": False,
}

INSTRUCCION = (
    "You are the editor of a small online store. A merchant filmed this vertical video selling one product. "
    "Watch the frames and listen to the audio. "
    "1) Identify the product; read any brand or label text exactly as printed. "
    "2) Split the speech into takes (consecutive spoken segments, with start/end seconds). When the speaker "
    "repeats or restarts a sentence, keep only the best, most fluent take and mark the others conservar=false "
    "with the reason. Transcribe each take in its original language. "
    "3) Give the second where the whole product is most clearly visible and sharp, for a catalog photo. "
    "4) Write a short hook for an Instagram Reel in the video's language. "
    "'nombre', 'categoria', 'atributos' and 'motivo' in Spanish; 'conceptos_sam' in English."
)

RESPALDO_SAM = "object held in hands"

PROMPT_CATALOGO = (
    "Professional e-commerce studio product photo of exactly this product, centered on a seamless soft white "
    "background, soft diffused studio lighting, subtle natural shadow. Keep the product identical: same shape, "
    "colors, logo, label text and proportions. Remove hands and any background."
)


def cronometro(nombre, fn):
    t = time.time()
    r = fn()
    print(f"  [{nombre}] {time.time() - t:.1f} s")
    return r


def extraer_cuadro(video: Path, segundo: float, destino: Path):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{segundo:.2f}", "-i", str(video),
                    "-frames:v", "1", "-vf", "scale=1080:-2", "-q:v", "2", str(destino)], check=True)


def recortar(imagen: Path, caja, destino: Path, margen: float = 0.08):
    dims = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0",
                           str(imagen)], capture_output=True, text=True, check=True).stdout.strip()
    ancho, alto = map(int, dims.split(","))
    mx, my = int((caja.x2 - caja.x1) * margen), int((caja.y2 - caja.y1) * margen)
    x1, y1 = max(0, caja.x1 - mx), max(0, caja.y1 - my)
    x2, y2 = min(ancho, caja.x2 + mx), min(alto, caja.y2 + my)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(imagen),
                    "-vf", f"crop={x2 - x1}:{y2 - y1}:{x1}:{y1}", str(destino)], check=True)


def procesar(meta: ClienteMeta, nombre: str):
    print(f"\n=== {nombre} ===")
    carpeta = SALIDA / nombre
    carpeta.mkdir(parents=True, exist_ok=True)
    proxy, proxy_sam = VIDEOS / "proxy" / f"{nombre}.mp4", VIDEOS / "proxy" / f"{nombre}_sam.mp4"
    original = VIDEOS / "originales" / f"{nombre}.MOV"

    analisis = json.loads(cronometro("Muse Spark video+audio", lambda: meta.preguntar(
        "muse-spark-1.3", [meta.parte_texto(INSTRUCCION), meta.parte_video(proxy)], esquema=ESQUEMA_ANALISIS)))
    (carpeta / "analisis.json").write_text(json.dumps(analisis, ensure_ascii=False, indent=2))
    print(json.dumps(analisis, ensure_ascii=False, indent=2))

    foto = carpeta / "cuadro.jpg"
    extraer_cuadro(original, analisis["mejor_cuadro_s"], foto)
    # SAM no siempre reconoce productos raros por su nombre: se prueba de lo
    # específico a lo genérico y se usa el primer concepto que encuentre algo.
    caja, concepto = None, None
    for candidato in analisis["producto"]["conceptos_sam"] + [RESPALDO_SAM]:
        cajas = cronometro(f"SAM imagen '{candidato}'", lambda: meta.segmentar(candidato, foto))
        caja = max((c for lista in cajas.values() for c in lista),
                   key=lambda c: (c.x2 - c.x1) * (c.y2 - c.y1), default=None)
        if caja:
            concepto = candidato
            break
    if caja is None:
        print("  SAM no encontró el producto en el cuadro; uso el cuadro completo")
        recorte = foto
    else:
        recorte = carpeta / "recorte.jpg"
        recortar(foto, caja, recorte)
    if concepto:
        cuadros = cronometro("SAM video", lambda: meta.segmentar(concepto, proxy_sam))
        con_producto = sum(1 for c in cuadros.values() if c)
        print(f"  SAM siguió '{concepto}' en {con_producto} de {len(cuadros)} cuadros")
    else:
        cuadros, con_producto = {}, 0
    cronometro("Muse Image catálogo", lambda: meta.editar_imagen(
        PROMPT_CATALOGO, [recorte], carpeta / "catalogo.png", "1024x1024"))
    return {"nombre": nombre, "concepto": concepto, "cuadros": len(cuadros), "con_producto": con_producto}


def main():
    meta = ClienteMeta()
    resumen = [procesar(meta, n) for n in sys.argv[1:]]
    print("\nResumen:", json.dumps(resumen, ensure_ascii=False))


if __name__ == "__main__":
    main()

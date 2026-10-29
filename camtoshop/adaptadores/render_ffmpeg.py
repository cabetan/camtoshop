"""Render del Reel con ffmpeg: cortes con zoom, voz limpia a -14 LUFS, efectos del plan y subtítulos.

Pasos: maestro 1080x1920 (una vez) -> corte con zoom alterno y audio limpio -> clips de efectos
(texto detrás del sujeto, escenas, portada, cierre) -> composición final con subtítulos.

Este ffmpeg no trae libass, así que los subtítulos se dibujan con Pillow como
imágenes transparentes y se superponen como una sola pista de video.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from camtoshop.adaptadores import efectos
from camtoshop.dominio.direccion import Efecto, Plan
from camtoshop.dominio.reel import Bloque, Tramo

ANCHO, ALTO, FPS = efectos.ANCHO, efectos.ALTO, efectos.FPS
FUENTE = efectos.NEGRA
# Limpieza de voz antes de nivelar: quita retumbe grave y ruido de fondo.
VOZ = "highpass=f=80,afftdn=nr=12:nf=-30,loudnorm=I=-14:TP=-1.5:LRA=11"
# El HLG del iPhone se ve bien como SDR, pero en escenas claras la piel queda pálida:
# se bajan medios y altas luces, se recupera color y se calienta un poco la piel.
COLOR_HLG = ("curves=all='0/0 0.25/0.19 0.5/0.41 0.75/0.66 1/0.92',"
             "eq=saturation=1.3:contrast=1.08,colorbalance=rm=0.04:bm=-0.04")
# Si entre dos bloques hay menos que esto, el anterior se queda en pantalla.
HUECO_MAXIMO = 0.4
# Duración del salto de tamaño de cada palabra al aparecer.
POP = 0.08

# (concepto, clip, tamaño del clip, tamaño de salida) -> {cuadro: máscara}
Segmentador = Callable[[str, Path, tuple[int, int], tuple[int, int]], dict[int, np.ndarray]]


class RenderizadorFFmpeg:
    def __init__(self, cache: Path, segmentar: Segmentador, conceptos_sujeto: list[str]):
        self._cache = cache
        self._segmentar = segmentar
        self._conceptos = conceptos_sujeto

    def maestro(self, video: Path) -> Path:
        """Copia vertical 1080x1920 a 30 cuadros/s; decodificar 4K HEVC una sola vez ahorra minutos."""
        destino = self._cache / f"{video.stem}_1080.mp4"
        if not destino.exists():
            self._cache.mkdir(parents=True, exist_ok=True)
            hdr = "arib-std-b67" in subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=color_transfer",
                 "-of", "csv=p=0", str(video)], capture_output=True, text=True).stdout
            filtro = f"scale={ANCHO}:{ALTO}:force_original_aspect_ratio=increase,crop={ANCHO}:{ALTO},fps={FPS}"
            if hdr:
                filtro += "," + COLOR_HLG
            _ffmpeg(["-hwaccel", "videotoolbox", "-i", str(video), "-map", "0:v:0", "-map", "0:a:0",
                     "-vf", filtro + ",format=yuv420p", "-c:v", "libx264", "-preset", "fast", "-crf", "17",
                     "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
                     "-c:a", "aac", "-b:a", "192k", "-ar", "48000", str(destino)])
        return destino

    def render(self, video: Path, tramos: list[Tramo], bloques: list[Bloque],
               posiciones: list[float], plan: Plan, destino: Path) -> Path:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            corte = self._cortar(self.maestro(video), tramos, plan, tmp / "corte.mp4")
            duracion = sum(t.duracion for t in tramos)

            capas: list[tuple[Path, float, float]] = []  # (clip, inicio, fin)
            for i, efecto in enumerate(plan.textos_detras):
                capas.append((self._texto_detras(corte, efecto, tmp / f"detras{i}.mp4"), efecto.inicio, efecto.fin))
            for i, escena in enumerate(plan.escenas):
                if escena.imagen:
                    clip = efectos.imagen_en_movimiento(escena.imagen, escena.fin - escena.inicio, tmp / f"escena{i}.mp4")
                    capas.append((clip, escena.inicio, escena.fin))
            if plan.imagen_portada:
                imagen = efectos.portada(plan.imagen_portada, plan.texto_portada, tmp / "portada.png")
                capas.append((efectos.imagen_en_movimiento(imagen, plan.look.segundos_portada, tmp / "portada.mp4",
                                                           acercar=0.05), 0.0, plan.look.segundos_portada))
            cierre = None
            if plan.imagen_cierre:
                tarjeta = efectos.ajustar_sin_recortar(plan.imagen_cierre, tmp / "cierre.png")
                cierre = efectos.imagen_en_movimiento(tarjeta, plan.look.segundos_cierre,
                                                      tmp / "cierre.mp4", acercar=0.04)

            # Sin subtítulos encima del texto gigante ni de la portada: competirían.
            ocultar = [Efecto(e.inicio, e.fin) for e in plan.textos_detras]
            ocultar.append(Efecto(0.0, plan.look.segundos_portada))
            subtitulos = self._subtitulos(bloques, posiciones, plan, duracion, ocultar, tmp)
            self._componer(corte, capas, subtitulos, cierre, duracion, plan, destino)
        return destino

    # --- Pasos ------------------------------------------------------------

    def _cortar(self, fuente: Path, tramos: list[Tramo], plan: Plan, destino: Path) -> Path:
        partes, etiquetas = [], []
        for i, t in enumerate(tramos):
            zoom, cx, cy = plan.centros_zoom[i] if i < len(plan.centros_zoom) else (1.0, ANCHO / 2, ALTO / 2)
            encuadre = ""
            if zoom > 1.0:
                w, h = ANCHO / zoom, ALTO / zoom
                encuadre = f",crop={w:.0f}:{h:.0f}:{cx - w / 2:.0f}:{cy - h / 2:.0f},scale={ANCHO}:{ALTO}:flags=lanczos"
            fundido = min(0.01, t.duracion / 4)
            partes.append(f"[0:v]trim={t.inicio:.3f}:{t.fin:.3f},setpts=PTS-STARTPTS{encuadre},setsar=1[v{i}]")
            partes.append(f"[0:a]atrim={t.inicio:.3f}:{t.fin:.3f},asetpts=PTS-STARTPTS,"
                          f"afade=t=in:d={fundido:.3f},afade=t=out:st={t.duracion - fundido:.3f}:d={fundido:.3f}[a{i}]")
            etiquetas.append(f"[v{i}][a{i}]")
        partes.append(f"{''.join(etiquetas)}concat=n={len(tramos)}:v=1:a=1[vc][ac]")
        partes.append(f"[ac]{VOZ},aresample=48000[aout]")
        _ffmpeg(["-i", str(fuente), "-filter_complex", ";".join(partes), "-map", "[vc]", "-map", "[aout]",
                 "-c:v", "libx264", "-preset", "fast", "-crf", "17", "-c:a", "aac", "-b:a", "192k", str(destino)])
        return destino

    def _texto_detras(self, corte: Path, efecto, destino: Path) -> Path:
        carpeta = destino.parent / (destino.stem + "_fuente")
        carpeta.mkdir()
        dur = efecto.fin - efecto.inicio
        _ffmpeg(["-ss", f"{efecto.inicio:.3f}", "-i", str(corte), "-t", f"{dur:.3f}", "-vf", f"fps={FPS}",
                 str(carpeta / "%04d.png")])
        cuadros = sorted(carpeta.glob("*.png"))
        # SAM recibe una copia liviana del mismo tramo; las máscaras vuelven al tamaño del Reel.
        liviano = destino.parent / (destino.stem + "_sam.mp4")
        _ffmpeg(["-ss", f"{efecto.inicio:.3f}", "-i", str(corte), "-t", f"{dur:.3f}", "-an",
                 "-vf", f"scale=540:960,fps={FPS}", "-c:v", "libx264", "-crf", "23", str(liviano)])
        sujeto: dict[int, np.ndarray] = {}
        for concepto in self._conceptos:
            for n, m in self._segmentar(concepto, liviano, (540, 960), (ANCHO, ALTO)).items():
                sujeto[n] = sujeto.get(n, np.zeros_like(m)) | m
        return efectos.texto_detras(cuadros, sujeto, efecto.lineas, destino)

    def _componer(self, corte: Path, capas, subtitulos: Path, cierre: Path | None, duracion: float,
                  plan: Plan, destino: Path) -> None:
        entradas = ["-i", str(corte)]
        partes, base = [], "[0:v]"
        for k, (clip, inicio, fin) in enumerate(capas, start=1):
            entradas += ["-i", str(clip)]
            partes.append(f"[{k}:v]setpts=PTS-STARTPTS+{inicio:.3f}/TB[c{k}]")
            partes.append(f"{base}[c{k}]overlay=enable='between(t,{inicio:.3f},{fin:.3f})':eof_action=pass[b{k}]")
            base = f"[b{k}]"
        s = len(capas) + 1
        entradas += ["-f", "concat", "-safe", "0", "-i", str(subtitulos)]
        partes.append(f"[{s}:v]fps={FPS},format=rgba[sub]")
        partes.append(f"{base}[sub]overlay=0:0:format=auto:shortest=1,format=yuv420p,setsar=1[vs]")
        total = duracion
        if cierre:
            entradas += ["-i", str(cierre)]
            partes.append(f"[{s + 1}:v]setsar=1,format=yuv420p[fin]")
            partes.append("[vs][fin]concat=n=2:v=1:a=0[vout]")
            total += plan.look.segundos_cierre
        else:
            partes.append("[vs]null[vout]")
        partes.append(f"[0:a]apad,atrim=0:{total:.3f}[aout]")
        destino.parent.mkdir(parents=True, exist_ok=True)
        _ffmpeg(entradas + ["-filter_complex", ";".join(partes), "-map", "[vout]", "-map", "[aout]",
                            "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-profile:v", "high",
                            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(destino)])

    # --- Subtítulos -------------------------------------------------------

    def _subtitulos(self, bloques: list[Bloque], posiciones: list[float], plan: Plan, duracion: float,
                    ocultar: list[Efecto], carpeta: Path) -> Path:
        """Una imagen por estado (bloque + palabra activa, con salto opcional) y una lista ffconcat."""
        vacia = carpeta / "vacia.png"
        Image.new("RGBA", (ANCHO, ALTO)).save(vacia)
        eventos: list[tuple[float, Path]] = [(0.0, vacia)]
        visibles = [(b, y) for b, y in zip(bloques, posiciones)
                    if not any(b.inicio < o.fin and o.inicio < b.fin for o in ocultar)]
        for n, (bloque, y) in enumerate(visibles):
            for k, palabra in enumerate(bloque.palabras):
                inicio = bloque.inicio if k == 0 else palabra.inicio
                normal = carpeta / f"b{n:03d}_{k}.png"
                self._dibujar(bloque, k, y, plan, 1.0).save(normal)
                if plan.look.pop:
                    salto = carpeta / f"b{n:03d}_{k}_pop.png"
                    self._dibujar(bloque, k, y, plan, 1.12).save(salto)
                    eventos += [(inicio, salto), (inicio + POP, normal)]
                else:
                    eventos.append((inicio, normal))
            siguiente = visibles[n + 1][0].inicio if n + 1 < len(visibles) else duracion
            if siguiente - bloque.fin > HUECO_MAXIMO:
                eventos.append((bloque.fin + 0.1, vacia))
        eventos.append((duracion, vacia))
        eventos.sort(key=lambda e: e[0])

        lineas = ["ffconcat version 1.0"]
        for (t, imagen), (t_sig, _) in zip(eventos, eventos[1:]):
            if t_sig - t > 0.001:
                lineas += [f"file '{imagen}'", f"duration {t_sig - t:.3f}"]
        lineas.append(f"file '{vacia}'")  # el demuxer ignora la duración del último archivo
        lista = carpeta / "subtitulos.txt"
        lista.write_text("\n".join(lineas))
        return lista

    def _dibujar(self, bloque: Bloque, activa: int, y: float, plan: Plan, salto: float) -> Image.Image:
        premium = plan.look.nombre == "premium"
        tamano = 74 if premium else 96
        imagen = Image.new("RGBA", (ANCHO, ALTO))
        lienzo = ImageDraw.Draw(imagen)
        fuentes = []
        for i, p in enumerate(bloque.palabras):
            escala = (salto if i == activa else 1.0) * (1.12 if p in plan.enfasis and not premium else 1.0)
            fuentes.append(ImageFont.truetype(str(FUENTE), round(tamano * escala)))
        textos = [p.texto.upper() for p in bloque.palabras]
        espacio = fuentes[0].getlength(" ")
        anchos = [f.getlength(t) for f, t in zip(fuentes, textos)]
        x = (ANCHO - sum(anchos) - espacio * (len(textos) - 1)) / 2
        for i, (texto, ancho, fuente) in enumerate(zip(textos, anchos, fuentes)):
            enfatizada = bloque.palabras[i] in plan.enfasis
            if premium:
                color = "#E8C77A" if enfatizada else ("white" if i == activa else "#E6E6E6")
            else:
                color = efectos.AMARILLO if (i == activa or enfatizada) else "white"
            # Las palabras más grandes se alinean por abajo con las demás.
            ajuste = tamano - fuente.size
            lienzo.text((x, y + ajuste), texto, font=fuente, fill=color,
                        stroke_width=6 if premium else 9, stroke_fill="black")
            x += ancho + espacio
        return imagen


def _ffmpeg(argumentos: list[str]) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *argumentos], check=True)

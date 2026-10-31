"""Render del Reel desde fotos: el producto real recortado con SAM se mueve por capas sobre su propia foto.

Cada cuadro se compone en Pillow (fondo, texto gigante, producto encima) y entra crudo a ffmpeg,
así el movimiento es suave y no tiembla como con zoompan. El texto queda detrás del producto,
como en el Reel hablado. Lo que genera Muse Image (escenas de uso) se marca en pantalla.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from camtoshop.adaptadores.efectos import ALTO, ANCHO, FPS, NEGRA, TIPOGRAFIAS, dibujar_lineas, fuente_que_cabe
from camtoshop.dominio.marca import Marca, Tema, tema_de
from camtoshop.dominio.reel_fotos import Toma

Segmentar = Callable[[str, Path, tuple[int, int], tuple[int, int]], dict[int, np.ndarray]]
LADO_MAXIMO = 1600
ESCALA_TEXTO = {"gancho": 0.95, "beneficio": 0.8, "escena": 0.7, "precio": 1.0, "cierre": 0.75}
POP = 0.22  # segundos de entrada del texto
LOGO = (260, 120)  # caja máxima del logo, arriba al centro, donde Instagram no pone botones


def _suave(p: float) -> float:
    return p * p * (3 - 2 * p)


def _cubrir(foto: Image.Image, ancho: int = ANCHO, alto: int = ALTO) -> Image.Image:
    escala = max(ancho / foto.width, alto / foto.height)
    foto = foto.resize((round(foto.width * escala), round(foto.height * escala)), Image.LANCZOS)
    x, y = (foto.width - ancho) // 2, (foto.height - alto) // 2
    return foto.crop((x, y, x + ancho, y + alto))


def _mover(base: Image.Image, escala: float, dx: float = 0, dy: float = 0) -> Image.Image:
    """Acerca `base` (del tamaño del Reel) alrededor del centro y la desplaza dx, dy píxeles."""
    a = 1 / escala
    c = ANCHO / 2 - ANCHO * a / 2 + dx
    f = ALTO / 2 - ALTO * a / 2 + dy
    return base.transform((ANCHO, ALTO), Image.AFFINE, (a, 0, c, 0, a, f), Image.BICUBIC)


def _camino(movimiento: str, p: float) -> tuple[float, float, float]:
    """(escala, dx, dy) del fondo según el movimiento de la toma."""
    q = _suave(p)
    if movimiento == "acercar":
        return 1.04 + 0.08 * q, 0, 0
    if movimiento == "alejar":
        return 1.12 - 0.08 * q, 0, 0
    lado = -1 if movimiento == "izquierda" else 1
    return 1.1, lado * (q - 0.5) * 50, 0


def _capa_texto(lineas: tuple[str, ...], y: float, escala: float, colores: tuple[str, ...], tipografia: str,
                sombra: bool = True) -> tuple[Image.Image, float]:
    capa = Image.new("RGBA", (ANCHO, ALTO))
    dibujar_lineas(ImageDraw.Draw(capa), list(lineas), y, escala, colores, sombra=sombra, tipografia=tipografia)
    caja = capa.getbbox()
    return capa, (caja[3] if caja else y)


def _degradado(alto_px: int, arriba: bool) -> Image.Image:
    """Sombra negra suave en un borde para que el texto se lea sobre cualquier foto."""
    banda = np.linspace(170, 0, alto_px) if arriba else np.linspace(0, 190, alto_px)
    alfa = np.zeros((ALTO, ANCHO), np.uint8)
    if arriba:
        alfa[:alto_px] = banda[:, None]
    else:
        alfa[-alto_px:] = banda[:, None]
    capa = Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 0))
    capa.putalpha(Image.fromarray(alfa))
    return capa


def _audio(voz: Path | None, musica: Path | None, total: float) -> list[str]:
    """Entradas y mapeo de audio: la música baja sola cuando hay voz, y siempre cierra suave."""
    limpia = f"highpass=f=80,afftdn,loudnorm=I=-14:TP=-1.5,apad,atrim=0:{total}"
    pista = f"atrim=0:{total},afade=t=in:d=0.2,afade=t=out:st={max(0, total - 1.2)}:d=1.2"
    if voz and musica:
        return ["-i", str(voz), "-stream_loop", "-1", "-i", str(musica), "-filter_complex",
                f"[1:a]{limpia},asplit=2[voz][llave];[2:a]{pista},volume=0.28[fondo];"
                "[fondo][llave]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[bajo];"
                "[voz][bajo]amix=inputs=2:duration=first:normalize=0[a]", "-map", "[a]"]
    if musica:
        return ["-stream_loop", "-1", "-i", str(musica), "-filter:a", f"{pista},loudnorm=I=-15:TP=-1.5",
                "-map", "1:a"]
    if voz:
        return ["-i", str(voz), "-filter:a", limpia, "-map", "1:a"]
    return ["-f", "lavfi", "-t", f"{total}", "-i", "anullsrc=r=48000:cl=stereo", "-map", "1:a"]


class RenderizadorFotos:
    def __init__(self, segmentar: Segmentar, conceptos: list[str], tema: Tema | None = None,
                 logo: Path | None = None, musica: Path | None = None):
        self._segmentar = segmentar
        self._conceptos = conceptos
        self._tema = tema or tema_de(Marca())
        self._logo = logo
        self._musica = musica

    # --- Recortes con SAM -------------------------------------------------------

    def preparar(self, foto: Path, carpeta: Path) -> Path:
        """Copia liviana y derecha (EXIF aplicado) de la foto, de máximo 1600 px."""
        from PIL import ImageOps
        destino = carpeta / f"{foto.stem}_lista.jpg"
        if not destino.exists():
            imagen = ImageOps.exif_transpose(Image.open(foto)).convert("RGB")
            imagen.thumbnail((LADO_MAXIMO, LADO_MAXIMO), Image.LANCZOS)
            imagen.save(destino, quality=92)
        return destino

    def recorte(self, foto: Path, carpeta: Path) -> Path | None:
        """PNG con transparencia del producto, o None si SAM no lo encuentra."""
        destino = carpeta / f"{foto.stem}_recorte.png"
        if destino.exists():
            return destino
        imagen = Image.open(foto).convert("RGB")
        for concepto in self._conceptos:
            mascara = self._segmentar(concepto, foto, imagen.size, imagen.size).get(0)
            if mascara is None or mascara.sum() < imagen.width * imagen.height * 0.01:
                continue
            alfa = Image.fromarray(mascara * 255).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.5))
            producto = imagen.copy()
            producto.putalpha(alfa)
            caja = alfa.getbbox()
            margen = int(max(caja[2] - caja[0], caja[3] - caja[1]) * 0.03)
            producto.crop((max(0, caja[0] - margen), max(0, caja[1] - margen),
                           min(imagen.width, caja[2] + margen), min(imagen.height, caja[3] + margen))).save(destino)
            return destino
        return None

    # --- Render -----------------------------------------------------------------

    def render(self, tomas: list[Toma], fotos: list[Path], recortes: list[Path | None], escenas: list[Path],
               voz: Path | None, destino: Path, nombre: str = "") -> Path:
        total = tomas[-1].fin
        cuadros = round(total * FPS)
        entrada = ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{ANCHO}x{ALTO}", "-r", str(FPS), "-i", "-"]
        audio = _audio(voz, self._musica, total)
        logo = self._logo_listo()
        proceso = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", *entrada, *audio, "-map", "0:v",
             "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "128k", "-t", f"{total}", "-movflags", "+faststart", str(destino)],
            stdin=subprocess.PIPE)
        try:
            n = 0
            for toma in tomas:
                pintor = self._pintor(toma, fotos, recortes, escenas, nombre)
                fin = min(cuadros, round(toma.fin * FPS))
                while n < fin:
                    t = n / FPS - toma.inicio
                    cuadro = pintor(t)
                    if logo is not None:
                        cuadro.paste(logo, ((ANCHO - logo.width) // 2, 56), logo)
                    proceso.stdin.write(cuadro.tobytes())
                    n += 1
        finally:
            proceso.stdin.close()
            if proceso.wait() != 0:
                raise RuntimeError("ffmpeg no pudo codificar el Reel desde fotos")
        return destino

    def _logo_listo(self) -> Image.Image | None:
        if not self._logo or not self._logo.exists():
            return None
        logo = Image.open(self._logo).convert("RGBA")
        logo.thumbnail(LOGO, Image.LANCZOS)
        return logo

    def _colores(self, destacado: bool = True) -> tuple[str, ...]:
        t = self._tema
        return (t.texto, t.acento, t.texto) if destacado else (t.acento,)

    def _fondo(self, foto: Image.Image, oscuro: float) -> Image.Image:
        if self._tema.fondo:
            return Image.new("RGB", (ANCHO, ALTO), self._tema.fondo)
        fondo = _cubrir(foto).filter(ImageFilter.GaussianBlur(28))
        return ImageEnhance.Brightness(ImageEnhance.Color(fondo).enhance(1.25)).enhance(oscuro)

    def _pintor(self, toma: Toma, fotos, recortes, escenas, nombre) -> Callable[[float], Image.Image]:
        if toma.tipo == "escena":
            return self._pintor_escena(toma, escenas[toma.imagen])
        foto = Image.open(fotos[toma.imagen]).convert("RGB")
        recorte = recortes[toma.imagen]
        if toma.tipo in {"precio", "cierre"} and recorte is None:
            recorte = next((r for r in recortes if r is not None), None)
        if recorte is None:
            return self._pintor_plano(toma, foto)
        return self._pintor_capas(toma, foto, Image.open(recorte).convert("RGBA"), nombre)

    def _pintor_capas(self, toma: Toma, foto: Image.Image, producto: Image.Image, nombre: str):
        """Fondo: la misma foto desenfocada y apagada. Encima, texto gigante y el producto real."""
        oscuro = 0.42 if toma.tipo == "cierre" else 0.62
        fondo = self._fondo(foto, oscuro)
        tipografia, sombra_texto = self._tema.fuente, not self._tema.fondo
        ruta_fuente = TIPOGRAFIAS[tipografia][0]
        precio = toma.tipo == "precio"
        cierre = toma.tipo == "cierre"
        escala_texto = ESCALA_TEXTO[toma.tipo]
        if precio:
            texto, abajo = _capa_texto(toma.lineas, ALTO * 0.66, escala_texto, self._colores(False), tipografia, sombra_texto)
            zona = (ALTO * 0.12, ALTO * 0.64)
        elif cierre:
            texto, abajo = _capa_texto(toma.lineas, ALTO * 0.60, escala_texto, self._colores(), tipografia, sombra_texto)
            if nombre:
                fuente = fuente_que_cabe(nombre.upper(), ruta_fuente, 70, ANCHO * 0.8)
                d = ImageDraw.Draw(texto)
                d.text(((ANCHO - fuente.getlength(nombre.upper())) / 2, abajo + 40), nombre.upper(),
                       font=fuente, fill=self._tema.texto)
            zona = (ALTO * 0.16, ALTO * 0.56)
        else:
            texto, abajo = _capa_texto(toma.lineas, ALTO * 0.09, escala_texto, self._colores(), tipografia, sombra_texto)
            zona = (max(ALTO * 0.24, abajo - ALTO * 0.04), ALTO * 0.94)  # el producto apenas roza el texto
        alto_zona = zona[1] - zona[0]
        base = min(ANCHO * 0.9 / producto.width, alto_zona / producto.height)
        texto_arriba = not (precio or cierre)

        def pintar(t: float) -> Image.Image:
            p = min(1.0, max(0.0, t / toma.duracion))
            escala, dx, dy = _camino(toma.movimiento, p)
            cuadro = _mover(fondo, escala, dx * 0.6, dy).convert("RGBA")
            entrada = min(1.0, t / POP)
            capa = texto
            if entrada < 1:
                capa = texto.copy()
                capa.putalpha(capa.getchannel("A").point(lambda a: int(a * entrada)))
                capa = capa.transform(capa.size, Image.AFFINE, (1, 0, 0, 0, 1, -(1 - _suave(entrada)) * 40))
            if texto_arriba:
                cuadro.alpha_composite(capa)
            # El producto se mueve distinto que el fondo: parallax suave.
            e = base * (0.97 + 0.05 * _suave(p)) * (1.0 if entrada >= 1 else 0.94 + 0.06 * _suave(entrada))
            prod = producto.resize((max(1, round(producto.width * e)), max(1, round(producto.height * e))), Image.BICUBIC)
            x = (ANCHO - prod.width) / 2 - dx * 0.35
            y = zona[0] + (alto_zona - prod.height) / 2 + (0 if not texto_arriba else alto_zona * 0.04)
            sombra = Image.new("RGBA", prod.size, (0, 0, 0, 0))
            sombra.putalpha(prod.getchannel("A").point(lambda a: int(a * 0.45)).filter(ImageFilter.GaussianBlur(18)))
            cuadro.alpha_composite(sombra, (round(x + 10), round(y + 24)))
            cuadro.alpha_composite(prod, (round(x), round(y)))
            if not texto_arriba:
                cuadro.alpha_composite(capa)
            return cuadro.convert("RGB")
        return pintar

    def _pintor_plano(self, toma: Toma, foto: Image.Image):
        """Sin recorte: la foto llena el cuadro y el texto va arriba sobre una sombra."""
        base = _cubrir(foto)
        sombra = _degradado(int(ALTO * 0.42), arriba=True)
        acento = self._tema.acento_foto
        texto, _ = _capa_texto(toma.lineas, ALTO * 0.08, ESCALA_TEXTO[toma.tipo],
                               (acento,) if toma.tipo == "precio" else ("white", acento, "white"), self._tema.fuente)

        def pintar(t: float) -> Image.Image:
            p = min(1.0, max(0.0, t / toma.duracion))
            cuadro = _mover(base, *_camino(toma.movimiento, p)).convert("RGBA")
            cuadro.alpha_composite(sombra)
            entrada = min(1.0, t / POP)
            capa = texto if entrada >= 1 else Image.blend(Image.new("RGBA", texto.size), texto, entrada)
            cuadro.alpha_composite(capa)
            return cuadro.convert("RGB")
        return pintar

    def _pintor_escena(self, toma: Toma, escena: Path):
        """Escena de uso hecha con Muse Image desde el recorte real; se marca como generada."""
        base = _cubrir(Image.open(escena).convert("RGB"))
        sombra = _degradado(int(ALTO * 0.45), arriba=False)
        texto, _ = _capa_texto(toma.lineas, ALTO * 0.70, ESCALA_TEXTO["escena"],
                               ("white", self._tema.acento_foto, "white"), self._tema.fuente)
        marca = Image.new("RGBA", (ANCHO, ALTO))
        fuente = ImageFont.truetype(str(NEGRA), 30)
        ImageDraw.Draw(marca).text((40, ALTO - 70), "AI SCENE · MUSE IMAGE", font=fuente, fill=(255, 255, 255, 150))

        def pintar(t: float) -> Image.Image:
            p = min(1.0, max(0.0, t / toma.duracion))
            cuadro = _mover(base, *_camino(toma.movimiento, p)).convert("RGBA")
            cuadro.alpha_composite(sombra)
            entrada = min(1.0, t / POP)
            capa = texto if entrada >= 1 else Image.blend(Image.new("RGBA", texto.size), texto, entrada)
            cuadro.alpha_composite(capa)
            cuadro.alpha_composite(marca)
            return cuadro.convert("RGB")
        return pintar

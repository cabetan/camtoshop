"""Montaje de los Reels dirigidos: planos fotografiados, cortados como pide cada estilo.

Los primeros planos son los de Muse Image (o las fotos reales si no los hay). El precio y el cierre
siempre muestran el producto real recortado con SAM, para que el Reel termine en lo que se compra.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from camtoshop.adaptadores.efectos import ALTO, ANCHO, FPS, NEGRA, TIPOGRAFIAS, fuente_que_cabe
from camtoshop.adaptadores.render_fotos import RenderizadorFotos, _audio, _degradado, _suave
from camtoshop.dominio.estilos import Estilo, estilo_de
from camtoshop.dominio.marca import OSCURO, contraste, legible_sobre
from camtoshop.dominio.reel_fotos import Toma

AIRE = 1.14  # el plano se carga más grande que el cuadro para que la cámara se pueda mover
TAMANO = {"barlow": 1.35, "playfair": 1.0, "poppins": .92, "caveat": 1.35}  # igualan el tamaño aparente
TRANSICION = {"disolver": 14, "empuje": 10, "telon": 10, "flash": 4, "corte": 0}
BARRA = 250
CREMA = (246, 240, 228)


def colorear(foto: Image.Image, color: str) -> Image.Image:
    """El tratamiento de color del estilo, aplicado una vez a cada plano."""
    if color == "natural":
        return foto
    a = np.asarray(foto, np.float32) / 255
    gris = a @ np.array([.2126, .7152, .0722], np.float32)
    saturar = lambda f: gris[..., None] + (a - gris[..., None]) * f
    curva = lambda x, f: np.clip(.5 + (x - .5) * f, 0, 1)
    if color == "bn":
        a = np.repeat(curva(gris, 1.3)[..., None], 3, 2)
    elif color == "calido":
        a = curva(saturar(1.05), 1.06) * np.array([1.06, 1, .88], np.float32)
    elif color == "vivo":
        a = curva(saturar(1.22), 1.08)
    elif color == "neon":
        a = curva(saturar(1.3), 1.14)
    elif color == "lavado":
        a = .07 + saturar(.8) * .86 * np.array([1.04, 1, .92], np.float32)
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))


def _cargar(foto: Image.Image) -> Image.Image:
    e = max(ANCHO / foto.width, ALTO / foto.height) * AIRE
    return foto.resize((round(foto.width * e), round(foto.height * e)), Image.LANCZOS)


@dataclass
class Plano:
    base: Image.Image | None  # None en las tomas con fondo fijo
    capas: Callable[[float], Image.Image | None]  # el texto en cada instante
    ia: bool = False
    fondo: Image.Image | None = None  # precio y cierre
    producto: Image.Image | None = None
    zona: tuple[float, float] = (0, 0)
    polaroid: Image.Image | None = None  # la tarjeta, con su leyenda


class RenderizadorDirigido(RenderizadorFotos):
    def __init__(self, segmentar, conceptos, tema, logo, musica, estilo: Estilo | str, primario: str = "#141414",
                 comercio: str = ""):
        super().__init__(segmentar, conceptos, tema, logo, musica)
        self._estilo = estilo_de(estilo) if isinstance(estilo, str) else estilo
        self._primario = primario
        self._comercio = comercio
        self._fuente_ruta = TIPOGRAFIAS[tema.fuente][0]
        self._rng = np.random.default_rng(1)
        self._granos = [self._rng.normal(0, self._estilo.grano or 1, (ALTO // 2, ANCHO // 2)).astype(np.float32)
                        for _ in range(6)] if self._estilo.grano else []
        x, y = np.linspace(-1, 1, ANCHO, dtype=np.float32), np.linspace(-1, 1, ALTO, dtype=np.float32)
        self._vineta = np.clip(1 - (x[None, :] ** 2 * .85 + y[:, None] ** 2) * self._estilo.vineta, 0, 1)[..., None]
        self._velo = Image.alpha_composite(_degradado(620, arriba=False), _degradado(420, arriba=True)) \
            if self._estilo.texto in {"pie", "portada"} else Image.new("RGBA", (ANCHO, ALTO))
        self._marca_ia = Image.new("RGBA", (ANCHO, ALTO))
        ImageDraw.Draw(self._marca_ia).text((40, ALTO - 70), "AI SCENE · MUSE IMAGE",
                                            font=ImageFont.truetype(str(NEGRA), 30), fill=(255, 255, 255, 150))

    # --- Texto --------------------------------------------------------------------

    def _f(self, tamano: float, ruta: Path | None = None) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(str(ruta or self._fuente_ruta), round(tamano * TAMANO[self._tema.fuente]))

    def _texto(self, toma: Toma) -> str:
        texto = " ".join(toma.lineas)
        return texto.upper() if self._estilo.mayusculas else texto

    @staticmethod
    def _partir(texto: str, fuente, ancho: float) -> list[str]:
        lineas, actual = [], ""
        for palabra in texto.split():
            prueba = f"{actual} {palabra}".strip()
            if fuente.getlength(prueba) > ancho and actual:
                lineas.append(actual)
                actual = palabra
            else:
                actual = prueba
        return lineas + ([actual] if actual else [])

    def _sombreado(self, dibujar: Callable[[ImageDraw.ImageDraw, object], None]) -> Image.Image:
        sombra, capa = Image.new("RGBA", (ANCHO, ALTO)), Image.new("RGBA", (ANCHO, ALTO))
        dibujar(ImageDraw.Draw(sombra), (0, 0, 0, 255))
        dibujar(ImageDraw.Draw(capa), None)
        return Image.alpha_composite(Image.alpha_composite(self._velo, sombra.filter(ImageFilter.GaussianBlur(12))), capa)

    def _pie(self, texto: str, y_centro: float = 1440, tamano: float = 88) -> Image.Image:
        fuente = self._f(tamano)
        lineas = self._partir(texto, fuente, 800)
        alto = fuente.size * 1.2
        y0 = y_centro - alto * len(lineas) / 2

        def dibujar(d, relleno):
            for n, l in enumerate(lineas):
                d.text((ANCHO / 2 - 30 - fuente.getlength(l) / 2, y0 + n * alto), l, font=fuente, fill=relleno or CREMA)
        return self._sombreado(dibujar)

    def _gigante(self, toma: Toma) -> Image.Image:
        """Cada línea sobre su propia franja: el color de marca también puede estar en el plano."""
        fuente = self._f(112)
        lineas = self._partir(self._texto(toma), fuente, 860)[:3]
        colores = ("#FFFFFF", self._tema.acento_foto, "#FFFFFF")
        capa = Image.new("RGBA", (ANCHO, ALTO))
        d = ImageDraw.Draw(capa)
        alto = round(fuente.size * 1.22)
        y = 250
        for l, color in zip(lineas, colores):
            ancho = fuente.getlength(l)
            x = (ANCHO - ancho) / 2
            d.rectangle((x - 28, y, x + ancho + 28, y + alto), fill=OSCURO)
            d.text((x, y + fuente.size * .06), l, font=fuente, fill=color)
            y += alto
        return capa

    def _portada(self, toma: Toma, nombre: str) -> Image.Image:
        cabecera = fuente_que_cabe((self._comercio or nombre).upper(), self._fuente_ruta, 170, ANCHO * .86)
        fuente = self._f(84)
        lineas = self._partir(self._texto(toma), fuente, 760)
        y0 = 1420 - len(lineas) * fuente.size * 1.18

        def dibujar(d, relleno):
            t = (self._comercio or nombre).upper()
            d.text(((ANCHO - cabecera.getlength(t)) / 2, 170), t, font=cabecera, fill=relleno or "#FFFFFF")
            d.rectangle((70, y0 - 28, 230, y0 - 22), fill=relleno or "#FFFFFF")
            for n, l in enumerate(lineas):
                d.text((70, y0 + n * fuente.size * 1.18), l, font=fuente, fill=relleno or "#FFFFFF")
        return self._sombreado(dibujar)

    def _historia(self, toma: Toma) -> Image.Image:
        fuente = self._f(64)
        lineas = self._partir(self._texto(toma), fuente, 760)
        alto = fuente.size + 34
        capa = Image.new("RGBA", (ANCHO, ALTO))
        d = ImageDraw.Draw(capa)
        y = 900 - len(lineas) * alto / 2
        for l in lineas:
            ancho = fuente.getlength(l)
            x = (ANCHO - ancho) / 2 - 30
            d.rounded_rectangle((x - 30, y, x + ancho + 30, y + alto), 22, fill=(255, 255, 255, 255))
            d.text((x, y + 8), l, font=fuente, fill=OSCURO)
            y += alto - 2
        return capa.rotate(-2.5, Image.BICUBIC)

    def _palabras(self, toma: Toma) -> list[Image.Image]:
        """Una capa por palabra: el texto se escribe solo, golpe a golpe."""
        palabras = self._texto(toma).split()
        fuente = self._f(112)
        lineas = self._partir(" ".join(palabras), fuente, 820)
        alto = fuente.size * 1.14
        y0 = 800 - len(lineas) * alto / 2
        capas = []
        for hasta in range(1, len(palabras) + 1):
            quedan = hasta

            def dibujar(d, relleno, quedan=quedan):
                resto = quedan
                for n, l in enumerate(lineas):
                    trozo = l.split()
                    visible = " ".join(trozo[:resto])
                    d.text((ANCHO / 2 - 30 - fuente.getlength(l) / 2, y0 + n * alto), visible, font=fuente, fill=relleno or "#FFFFFF")
                    resto = max(0, resto - len(trozo))
            capas.append(self._sombreado(dibujar))
        return capas

    def _cinemascope(self, toma: Toma) -> Image.Image:
        """Letras separadas, como en un título de película."""
        fuente = self._f(44)
        abierta = lambda l: sum(fuente.getlength(c) + 12 for c in l)
        lineas, actual = [], ""
        for palabra in self._texto(toma).split():
            prueba = f"{actual}   {palabra}".strip()
            if abierta(prueba) > 880 and actual:
                lineas.append(actual)
                actual = palabra
            else:
                actual = prueba
        lineas.append(actual)
        capa = Image.new("RGBA", (ANCHO, ALTO))
        d = ImageDraw.Draw(capa)
        y = ALTO - BARRA - 40 - len(lineas) * fuente.size * 1.4
        for l in lineas:
            x = (ANCHO - abierta(l)) / 2
            for c in l:
                d.text((x, y), c, font=fuente, fill=(255, 255, 255, 255))
                x += fuente.getlength(c) + 12
            y += fuente.size * 1.4
        return capa

    def _tarjeta(self, toma: Toma) -> Image.Image:
        tarjeta = Image.new("RGBA", (880, 1190), (250, 247, 240, 255))
        d = ImageDraw.Draw(tarjeta)
        fuente = self._f(70)
        lineas = self._partir(self._texto(toma), fuente, 780)[:2]
        for n, l in enumerate(lineas):
            d.text(((880 - fuente.getlength(l)) / 2, 1030 + n * fuente.size * .95), l, font=fuente, fill=(40, 36, 32, 255))
        return tarjeta

    def _animar(self, capa: Image.Image, modo: str = "subir") -> Callable[[float], Image.Image]:
        def en(t: float) -> Image.Image:
            p = min(1.0, max(0.0, (t - .08) / .3))
            if p >= 1:
                return capa
            c = capa.copy()
            c.putalpha(c.getchannel("A").point(lambda a: int(a * p)))
            if modo == "subir":
                c = c.transform(c.size, Image.AFFINE, (1, 0, 0, 0, 1, -(1 - _suave(p)) * 24))
            else:
                e = 1 / (1.14 - .14 * _suave(p))
                c = c.transform(c.size, Image.AFFINE, (e, 0, ANCHO / 2 * (1 - e), 0, e, ALTO * .3 * (1 - e)), Image.BICUBIC)
            return c
        return en

    def _capas(self, toma: Toma, nombre: str) -> Callable[[float], Image.Image | None]:
        modo = self._estilo.texto
        if modo == "polaroid":
            return lambda t: None
        if modo == "palabra":
            capas = self._palabras(toma)
            paso = max(.12, min(.3, toma.duracion * .6 / max(1, len(capas))))
            return lambda t: capas[min(len(capas) - 1, int(max(0, t) / paso))] if capas else None
        if modo == "gigante":
            return self._animar(self._gigante(toma), "golpe")
        if modo == "portada":
            return self._animar(self._portada(toma, nombre))
        if modo == "historia":
            return self._animar(self._historia(toma), "golpe")
        if modo == "cinemascope":
            return self._animar(self._cinemascope(toma))
        return self._animar(self._pie(self._texto(toma)))

    # --- Precio y cierre: el producto real ---------------------------------------------

    def _lamina(self, ultimo: Image.Image | None) -> Image.Image:
        if self._tema.fondo or ultimo is None:
            return Image.new("RGB", (ANCHO, ALTO), self._tema.fondo or OSCURO)
        apagado = ultimo.resize((ANCHO, ALTO)).filter(ImageFilter.GaussianBlur(26)).convert("RGBA")
        apagado.alpha_composite(Image.new("RGBA", (ANCHO, ALTO), (0, 0, 0, 90)))
        return apagado.convert("RGB")

    def _color_lamina(self) -> tuple[str, str]:
        """(texto, acento) sobre la lámina del precio."""
        return (self._tema.texto, self._tema.acento) if self._tema.fondo else ("#FFFFFF", self._tema.acento_foto)

    def _logo_para(self, fondo: Image.Image) -> Image.Image | None:
        logo = self._logo_listo_grande()
        if logo is None:
            return None
        color = "#%02x%02x%02x" % fondo.resize((1, 1)).getpixel((0, 0))[:3]
        transparente = logo.getchannel("A").getextrema()[0] < 16
        visibles = np.asarray(logo)[np.asarray(logo)[..., 3] > 128][:, :3]
        tono = "#%02x%02x%02x" % tuple(int(v) for v in visibles.mean(0)) if len(visibles) else "#000000"
        if transparente and contraste(tono, color) < 2.2:  # un logo oscuro sobre fondo oscuro se vuelve claro
            plano = Image.new("RGBA", logo.size, legible_sobre(color))
            plano.putalpha(logo.getchannel("A"))
            return plano
        return logo

    def _logo_listo_grande(self) -> Image.Image | None:
        if not self._logo or not self._logo.exists():
            return None
        logo = Image.open(self._logo).convert("RGBA")
        logo.thumbnail((520, 300), Image.LANCZOS)
        return logo

    def _plano_precio(self, toma: Toma, lamina: Image.Image, producto: Image.Image | None) -> Plano:
        texto, acento = self._color_lamina()
        fuente = fuente_que_cabe(toma.lineas[0], self._fuente_ruta, 170, ANCHO * .8)
        capa = Image.new("RGBA", (ANCHO, ALTO))
        ImageDraw.Draw(capa).text(((ANCHO - fuente.getlength(toma.lineas[0])) / 2, 1190), toma.lineas[0], font=fuente, fill=acento)
        return Plano(None, self._animar(capa, "golpe"), fondo=lamina, producto=producto, zona=(230, 1150))

    def _plano_cierre(self, toma: Toma, lamina: Image.Image, producto: Image.Image | None, nombre: str,
                      precio: str) -> Plano:
        texto, acento = self._color_lamina()
        capa = Image.new("RGBA", (ANCHO, ALTO))
        d = ImageDraw.Draw(capa)
        logo = self._logo_para(lamina)
        if logo is not None:
            capa.alpha_composite(logo, ((ANCHO - logo.width) // 2, 980))
            y = 1010 + logo.height
        else:
            corto = (self._comercio or " ".join(nombre.split()[:4])).upper()
            marca = fuente_que_cabe(corto, self._fuente_ruta, 110, ANCHO * .78)
            d.text(((ANCHO - marca.getlength(corto)) / 2, 1000), corto, font=marca, fill=texto)
            y = 1140
        fuente = self._f(70)
        for l in self._partir(self._texto(toma), fuente, 800)[:2]:
            d.text(((ANCHO - fuente.getlength(l)) / 2, y), l, font=fuente, fill=acento)
            y += fuente.size * 1.2
        if precio:
            f2 = self._f(62)
            d.text(((ANCHO - f2.getlength(precio)) / 2, y + 6), precio, font=f2, fill=texto)
        return Plano(None, self._animar(capa), fondo=lamina, producto=producto, zona=(240, 950))

    # --- Cuadros ------------------------------------------------------------------------

    def _encuadre(self, base: Image.Image, movimiento: str, p: float, t: float) -> Image.Image:
        fuerza, q = self._estilo.movimiento, _suave(p)
        ancho, alto = base.size
        z = {"acercar": 1 - .09 * fuerza * q, "alejar": 1 - .09 * fuerza * (1 - q)}.get(movimiento, .95)
        if self._estilo.golpe:
            z *= 1 - .1 * (1 - _suave(min(1.0, t / .25)))
        dx = {"izquierda": -1, "derecha": 1}.get(movimiento, 0) * (.5 - q) * (ancho / AIRE) * .1 * fuerza
        dy = 0.0
        if self._estilo.temblor:
            dx += 7 * np.sin(t * 2.7) + 4 * np.sin(t * 6.1)
            dy += 8 * np.sin(t * 2.1 + 1) + 3 * np.sin(t * 5.3)
        w, h = ANCHO * z, ALTO * z
        return base.transform((ANCHO, ALTO), Image.AFFINE, (z, 0, (ancho - w) / 2 + dx, 0, z, (alto - h) / 2 + dy),
                              Image.BICUBIC)

    def _foto_polaroid(self, plano: Plano, imagen: Image.Image, n: int) -> Image.Image:
        lienzo = plano.polaroid.copy()
        lienzo.paste(imagen.resize((800, 1000), Image.BILINEAR).crop((0, 0, 800, 990)), (40, 40))
        fondo = Image.new("RGBA", (ANCHO, ALTO), (30, 27, 24, 255))
        fondo.paste(imagen.resize((ANCHO, ALTO), Image.BILINEAR).filter(ImageFilter.GaussianBlur(20)).point(lambda v: v // 2))
        giro = lienzo.rotate(2.5 if n % 2 else -2.5, Image.BICUBIC, expand=True)
        sombra = Image.new("RGBA", giro.size, (0, 0, 0, 0))
        sombra.putalpha(giro.getchannel("A").point(lambda a: a // 2))
        fondo.alpha_composite(sombra, ((ANCHO - giro.width) // 2 + 12, 262))
        fondo.alpha_composite(giro, ((ANCHO - giro.width) // 2, 250))
        return fondo.convert("RGB")

    def _cuadro(self, plano: Plano, toma: Toma, n: int, t: float) -> np.ndarray:
        p = min(1.0, max(0.0, t / toma.duracion))
        if plano.fondo is not None:
            cuadro = plano.fondo.convert("RGBA")
            if plano.producto is not None:
                alto = plano.zona[1] - plano.zona[0]
                e = min(ANCHO * .84 / plano.producto.width, alto / plano.producto.height) * (.95 + .07 * _suave(p))
                prod = plano.producto.resize((max(1, round(plano.producto.width * e)), max(1, round(plano.producto.height * e))), Image.BICUBIC)
                x, y = (ANCHO - prod.width) // 2, round(plano.zona[0] + (alto - prod.height) / 2 - 10 * np.sin(p * 3.14))
                sombra = Image.new("RGBA", prod.size, (0, 0, 0, 0))
                sombra.putalpha(prod.getchannel("A").point(lambda a: int(a * .4)).filter(ImageFilter.GaussianBlur(20)))
                cuadro.alpha_composite(sombra, (x + 8, y + 26))
                cuadro.alpha_composite(prod, (x, y))
            a = np.asarray(cuadro.convert("RGB"), np.float32)
        else:
            imagen = self._encuadre(plano.base, toma.movimiento, p, t)
            if plano.polaroid is not None:
                imagen = self._foto_polaroid(plano, imagen, n)
            a = np.asarray(imagen, np.float32) * self._vineta
        if self._estilo.barras:
            a[:BARRA], a[-BARRA:] = 0, 0
        capa = plano.capas(t)
        if capa is not None:
            b = np.asarray(capa, np.float32)
            m = b[..., 3:] / 255
            a = a * (1 - m) + b[..., :3] * m
        if plano.ia:
            b = np.asarray(self._marca_ia, np.float32)
            m = b[..., 3:] / 255
            a = a * (1 - m) + b[..., :3] * m
        return a

    def _transicion(self, a: np.ndarray, previo: Callable[[], np.ndarray], k: int) -> np.ndarray:
        """Mezcla el cuadro `a` con el plano anterior, `k` cuadros después del corte."""
        modo = self._estilo.transicion
        largo = TRANSICION[modo]
        if k >= largo:
            return a
        q = _suave((k + 1) / (largo + 1))
        if modo == "disolver":
            return a * q + previo() * (1 - q)
        if modo == "flash":
            return a + 255 * (1 - (k + 1) / (largo + 1))
        if modo == "empuje":
            corrido = round(ANCHO * (1 - q))
            salida = np.empty_like(a)
            salida[:, :ANCHO - corrido] = previo()[:, corrido:] if corrido else previo()
            salida[:, ANCHO - corrido:] = a[:, :corrido] if corrido else a[:, :0]
            return salida
        color = np.array(Image.new("RGB", (1, 1), self._primario).getpixel((0, 0)), np.float32)
        salida = previo().copy() if q < .5 else a.copy()
        borde = round(ANCHO * (q * 2 if q < .5 else (q - .5) * 2))
        if q < .5:
            salida[:, :borde] = color
        else:
            salida[:, borde:] = color
        return salida

    def _planos(self, tomas: list[Toma], fotos, recortes, planos, nombre: str) -> list[Plano]:
        salida: list[Plano] = []
        ultimo, n = None, 0
        recorte = next((r for r in recortes if r is not None), None)
        producto = Image.open(recorte).convert("RGBA") if recorte else None
        lamina = None
        precio = next((t.lineas[0] for t in tomas if t.tipo == "precio"), "")
        for toma in tomas:
            if toma.tipo in {"precio", "cierre"}:
                lamina = lamina or self._lamina(ultimo)
                if toma.tipo == "precio":
                    salida.append(self._plano_precio(toma, lamina, producto))
                else:
                    salida.append(self._plano_cierre(toma, lamina, producto, nombre, precio))
                continue
            ia = n < len(planos)
            ruta = planos[n] if ia else fotos[toma.imagen]
            n += 1
            ultimo = colorear(Image.open(ruta).convert("RGB"), self._estilo.color)
            salida.append(Plano(_cargar(ultimo), self._capas(toma, nombre), ia,
                                polaroid=self._tarjeta(toma) if self._estilo.texto == "polaroid" else None))
        return salida

    def render(self, tomas: list[Toma], fotos: list[Path], recortes: list[Path | None], escenas: list[Path],
               voz: Path | None, destino: Path, nombre: str = "") -> Path:
        total = tomas[-1].fin
        planos = self._planos(tomas, fotos, recortes, escenas, nombre)
        entrada = ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{ANCHO}x{ALTO}", "-r", str(FPS), "-i", "-"]
        proceso = subprocess.Popen(
            ["ffmpeg", "-y", "-loglevel", "error", *entrada, *_audio(voz, self._musica, total), "-map", "0:v",
             "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", "-t", f"{total}", "-movflags", "+faststart", str(destino)],
            stdin=subprocess.PIPE)
        try:
            cuadros = round(total * FPS)
            for k in range(cuadros):
                s = k / FPS
                n = next((i for i, x in enumerate(tomas) if s < x.fin), len(tomas) - 1)
                toma = tomas[n]
                t = s - toma.inicio
                a = self._cuadro(planos[n], toma, n, t)
                if n:
                    anterior = tomas[n - 1]
                    a = self._transicion(a, lambda: self._cuadro(planos[n - 1], anterior, n - 1, anterior.duracion + t),
                                         round(t * FPS))
                if self._granos:
                    grano = Image.fromarray(self._granos[k % 6]).resize((ANCHO, ALTO), Image.BILINEAR)
                    a = a + np.asarray(grano)[..., None]
                proceso.stdin.write(np.clip(a, 0, 255).astype(np.uint8).tobytes())
        finally:
            proceso.stdin.close()
            if proceso.wait() != 0:
                raise RuntimeError("ffmpeg no pudo codificar el Reel dirigido")
        return destino

"""Servicio de aplicación: arma los adaptadores reales, corre el flujo de un proyecto y guarda su estado.

Cada proyecto vive en su carpeta (datos/proyectos/<id>/) con el video original, los resultados y
un estado.json que la app web consulta para mostrar el progreso y la bitácora del agente.
Los pasos que no dependen entre sí corren en paralelo.
"""

from __future__ import annotations

import json
import shutil
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from camtoshop.adaptadores import cache
from camtoshop.adaptadores.alineador_xlsr import AlineadorXLSR
from camtoshop.adaptadores.config import canal_conectado, secreto
from camtoshop.adaptadores.meta_api import ClienteMeta
from camtoshop.adaptadores.meta_comercio import CatalogoMeta, InstagramReels
from camtoshop.adaptadores.producto_meta import AnalizadorSpark, FotografoMuse, PublicistaMuse, RedactorSpark
from camtoshop.adaptadores.reel_meta import (
    DirectorSpark, EditorSpark, IlustradorMuse, RastreadorSAM, RevisorSpark, TranscriptorMeta,
)
from camtoshop.adaptadores.render_ffmpeg import RenderizadorFFmpeg
from camtoshop.adaptadores.sam_mascaras import mascaras
from camtoshop.adaptadores.shopify import TiendaShopify, token_por_credenciales
from camtoshop.dominio.anuncios import normalizar_anuncios
from camtoshop.dominio.direccion import LOOK_POR_DEFECTO, LOOKS, Propuesta, armar_plan, centros_de_zoom
from camtoshop.dominio.editar_reel import Montaje, Puertos, ResultadoReel, dirigir_y_revisar, preparar_montaje, rehacer
from camtoshop.dominio.producto import Analisis, Ficha, Precio, Texto, normalizar_ficha, precio_valido
from camtoshop.dominio.publicacion import pie_de_instagram, publicar

RAIZ = Path(__file__).resolve().parents[2]
DATOS = RAIZ / "datos" / "proyectos"
IDIOMAS_FICHA = ["en", "es"]  # inglés primero; siempre se agrega el idioma del video


def ficha_a_json(f: Ficha) -> dict:
    d = asdict(f)
    d["precio_texto"] = f.precio.texto() if f.precio else ""
    return d


def ficha_de_json(d: dict) -> Ficha:
    precio = Precio(**d["precio"]) if d.get("precio") else None
    return Ficha(d["idioma"], {k: Texto(**v) for k, v in d["textos"].items()}, precio, d["marca"],
                 d["categoria"], d.get("etiquetas", []), d.get("imagenes", []))


class Adelantado:
    """Rastreador cuyo resultado ya se está calculando en otro hilo."""

    def __init__(self, futuro):
        self._futuro = futuro

    def cajas(self, video: Path):
        return self._futuro.result()


class Proyecto:
    """Estado persistente de un video procesado."""

    def __init__(self, carpeta: Path):
        self.carpeta = carpeta
        self.id = carpeta.name
        self._cerrojo = threading.Lock()
        archivo = carpeta / "estado.json"
        self.estado = json.loads(archivo.read_text()) if archivo.exists() else {
            "id": self.id, "fase": "en_cola", "progreso": 0, "pasos": [], "error": "", "reels": {},
            "look": LOOK_POR_DEFECTO, "publicaciones": [], "creado": time.time(),
        }

    def guardar(self, **cambios):
        with self._cerrojo:
            self.estado.update(cambios)
            temporal = self.carpeta / "estado.tmp"
            temporal.write_text(json.dumps(self.estado, ensure_ascii=False, indent=1))
            temporal.replace(self.carpeta / "estado.json")

    def paso(self, texto: str, progreso: int | None = None):
        with self._cerrojo:
            self.estado["pasos"].append({"t": round(time.time() - self.estado["creado"], 1), "texto": texto})
        self.guardar(**({"progreso": progreso} if progreso is not None else {}))

    def ruta(self, nombre: str) -> Path:
        return self.carpeta / nombre

    def relativa(self, ruta: Path) -> str:
        return str(Path(ruta).relative_to(self.carpeta))

    @property
    def video(self) -> Path:
        return next(self.carpeta.glob("original.*"))


class Servicio:
    def __init__(self, datos: Path = DATOS):
        self._datos = datos
        datos.mkdir(parents=True, exist_ok=True)
        self._cliente = None
        self._alineador = None
        self._montajes: dict[str, Montaje] = {}
        self._reels: dict[str, ResultadoReel] = {}
        # Un proyecto a la vez: el render usa toda la máquina.
        self._cola = ThreadPoolExecutor(max_workers=1)

    # --- Infraestructura ----------------------------------------------------

    @property
    def cliente(self) -> ClienteMeta:
        if self._cliente is None:
            self._cliente = ClienteMeta()
        return self._cliente

    @property
    def alineador(self) -> AlineadorXLSR:
        if self._alineador is None:
            self._alineador = AlineadorXLSR()
        return self._alineador

    def _puertos(self, pr: Proyecto, analisis: Analisis, foto: Path) -> Puertos:
        c, t = self.cliente, pr.ruta("trabajo")
        t.mkdir(exist_ok=True)
        return Puertos(
            transcriptor=cache.turnos(TranscriptorMeta(c, [analisis.marca] if analisis.marca else None),
                                      t / "turnos.json"),
            alineador=cache.palabras(self.alineador, t / "palabras.json"),
            editor=cache.rangos(EditorSpark(c), t / "edicion.json"),
            rastreador=cache.cajas(RastreadorSAM(c, analisis.conceptos_sam + ["object held in hands"],
                                                 fuente=t / "liviano.mp4" if (t / "liviano.mp4").exists() else None),
                                   t / "cajas.json"),
            director=DirectorSpark(c),
            ilustrador=IlustradorMuse(c, foto, t / "insertos"),
            renderizador=self._renderizador(analisis),
            revisor=RevisorSpark(c),
        )

    def _renderizador(self, analisis: Analisis) -> RenderizadorFFmpeg:
        c = self.cliente
        return RenderizadorFFmpeg(
            RAIZ / "videos" / "maestros",
            lambda concepto, clip, fuente, salida: mascaras(c, concepto, clip, fuente, salida),
            ["person", analisis.conceptos_sam[0], "object held in hands"])

    # --- Proyectos ----------------------------------------------------------

    def crear(self, nombre_archivo: str, contenido) -> Proyecto:
        identificador = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        carpeta = self._datos / identificador
        carpeta.mkdir(parents=True)
        extension = Path(nombre_archivo).suffix.lower() or ".mov"
        with (carpeta / f"original{extension}").open("wb") as destino:
            shutil.copyfileobj(contenido, destino, length=8 * 1024 * 1024)
        pr = Proyecto(carpeta)
        pr.guardar(nombre_archivo=nombre_archivo)
        self._cola.submit(self._procesar, pr)
        return pr

    def obtener(self, identificador: str) -> Proyecto | None:
        carpeta = self._datos / identificador
        return Proyecto(carpeta) if (carpeta / "estado.json").exists() else None

    def listar(self) -> list[dict]:
        proyectos = [Proyecto(c).estado for c in sorted(self._datos.iterdir(), reverse=True)
                     if (c / "estado.json").exists()]
        return [{k: p.get(k) for k in ("id", "fase", "progreso", "creado", "nombre_archivo", "analisis")}
                for p in proyectos]

    def canales(self) -> dict[str, bool]:
        return {canal: canal_conectado(canal) for canal in ("shopify", "catalogo_meta", "instagram")}

    # --- Flujo completo -------------------------------------------------------

    def _procesar(self, pr: Proyecto):
        try:
            pr.guardar(fase="procesando")
            video = pr.video
            with ThreadPoolExecutor(max_workers=3) as hilos:
                pr.paso("Preparando el video en 1080p", 3)
                maestro = hilos.submit(self._renderizador_basico().maestro, video)

                if pr.estado.get("analisis"):  # reintento: el análisis ya se pagó
                    analisis = Analisis(**pr.estado["analisis"])
                else:
                    pr.paso("Muse Spark mira y escucha el video", 5)
                    analisis = AnalizadorSpark(self.cliente, pr.ruta("trabajo")).analizar(video)
                pr.guardar(analisis=asdict(analisis))
                pr.paso(f"Producto: {analisis.nombre}" + (f" · {analisis.marca}" if analisis.marca else ""), 12)

                pr.paso("SAM 3.1 recorta el producto y Muse Image hace las fotos de catálogo", 15)
                fotos = FotografoMuse(self.cliente, pr.ruta("fotos")).fotos(video, analisis)
                pr.guardar(fotos=[pr.relativa(f) for f in fotos])
                pr.paso("Fotos de catálogo listas", 25)

                p = self._puertos(pr, analisis, fotos[0])
                # El rastreo con SAM no depende de la transcripción: corre en paralelo y el
                # montaje lo recoge cuando lo necesita.
                rastreo = hilos.submit(p.rastreador.cajas, video)
                p.rastreador = Adelantado(rastreo)
                montaje = preparar_montaje(video, analisis.idioma, p, lambda t: pr.paso(t))
                self._montajes[pr.id] = montaje
                pr.paso(f"Edición: {len(montaje.palabras) - len(montaje.conservadas)} palabras fuera, "
                        f"{montaje.duracion:.0f} s de mensaje limpio", 45)

                transcripcion = " ".join(w.texto for w in montaje.del_reel)
                ficha_f = hilos.submit(self._ficha, pr, analisis, transcripcion, fotos)
                maestro.result()
                reel = self._dirigir(pr, analisis, montaje, LOOKS[pr.estado["look"]], p)
                ficha = ficha_f.result()
                self._anuncios(pr, ficha, fotos[0])
            pr.guardar(fase="listo", progreso=100)
            pr.paso("Listo para publicar")
        except Exception as e:  # el error se muestra en la app en vez de perderse en un hilo
            pr.guardar(fase="error", error=f"{e}", detalle_error=traceback.format_exc()[-2000:])

    def reintentar(self, pr: Proyecto):
        pr.guardar(fase="en_cola", error="", detalle_error="")
        self._cola.submit(self._procesar, pr)

    def _renderizador_basico(self) -> RenderizadorFFmpeg:
        return RenderizadorFFmpeg(RAIZ / "videos" / "maestros", lambda *a: {}, [])

    def _ficha(self, pr: Proyecto, analisis: Analisis, transcripcion: str, fotos: list[Path]) -> Ficha:
        pr.paso("Muse Spark escribe la ficha del producto en inglés y español")
        ficha = RedactorSpark(self.cliente).ficha(analisis, transcripcion, IDIOMAS_FICHA)
        ficha.imagenes = [str(f) for f in fotos]
        avisos = normalizar_ficha(ficha)
        pr.guardar(ficha=ficha_a_json(ficha), avisos=avisos)
        return ficha

    def _dirigir(self, pr: Proyecto, analisis: Analisis, montaje: Montaje, look, p: Puertos) -> ResultadoReel:
        destino = pr.ruta(f"reel_{look.nombre}.mp4")
        progreso = iter(range(50, 90, 6))
        r = dirigir_y_revisar(montaje, asdict(analisis), look, destino, p,
                              lambda t: pr.paso(t, next(progreso, 90)))
        self._reels[pr.id] = r
        self._guardar_reel(pr, r)
        return r

    def _guardar_reel(self, pr: Proyecto, r: ResultadoReel):
        reels = dict(pr.estado.get("reels", {}))
        reels[r.plan.look.nombre] = {"archivo": pr.relativa(r.reel), "bitacora": r.bitacora,
                                     "duracion": round(r.duracion + r.plan.look.segundos_cierre, 1),
                                     "propuesta": asdict(r.propuesta)}
        pr.guardar(reels=reels, look=r.plan.look.nombre)

    def _anuncios(self, pr: Proyecto, ficha: Ficha, foto: Path):
        pr.paso("Muse Spark escribe 3 anuncios y Muse Image diseña cada pieza", 92)
        publicista = PublicistaMuse(self.cliente, pr.ruta("anuncios"))
        anuncios = normalizar_anuncios(publicista.anuncios(ficha, foto))
        salida = []
        for a in anuncios:
            a.imagenes = {f: publicista.creativo(a, foto, f) for f in ("feed",)}
            d = asdict(a)
            d["imagenes"] = {k: pr.relativa(v) for k, v in a.imagenes.items()}
            salida.append(d)
        pr.guardar(anuncios=salida)

    # --- Acciones posteriores ---------------------------------------------------

    def _contexto(self, pr: Proyecto) -> tuple[Analisis, Montaje, Puertos]:
        analisis = Analisis(**pr.estado["analisis"])
        p = self._puertos(pr, analisis, pr.ruta(pr.estado["fotos"][0]))
        montaje = self._montajes.get(pr.id) or preparar_montaje(pr.video, analisis.idioma, p)
        self._montajes[pr.id] = montaje
        return analisis, montaje, p

    def cambiar_look(self, pr: Proyecto, nombre: str):
        if nombre in pr.estado.get("reels", {}):
            pr.guardar(look=nombre)  # ya existe: solo se muestra
            return

        def tarea():
            try:
                pr.guardar(fase="procesando", progreso=50)
                analisis, montaje, p = self._contexto(pr)
                self._dirigir(pr, analisis, montaje, LOOKS[nombre], p)
                pr.guardar(fase="listo", progreso=100)
            except Exception as e:
                pr.guardar(fase="error", error=str(e), detalle_error=traceback.format_exc()[-2000:])
        self._cola.submit(tarea)

    def pedir_cambio(self, pr: Proyecto, pedido: str):
        def tarea():
            try:
                pr.guardar(fase="procesando", progreso=50)
                analisis, montaje, p = self._contexto(pr)
                anterior = self._reels.get(pr.id) or self._reel_guardado(pr, montaje, p)
                destino = pr.ruta(f"reel_pedido_{int(time.time())}.mp4")
                r = rehacer(montaje, anterior, pedido, asdict(analisis), destino, p, lambda t: pr.paso(t))
                self._reels[pr.id] = r
                self._guardar_reel(pr, r)
                pr.guardar(fase="listo", progreso=100)
            except Exception as e:
                pr.guardar(fase="error", error=str(e), detalle_error=traceback.format_exc()[-2000:])
        self._cola.submit(tarea)

    def _reel_guardado(self, pr: Proyecto, montaje: Montaje, p: Puertos) -> ResultadoReel:
        """Reconstruye el último Reel desde el estado (por ejemplo, tras reiniciar el servidor)."""
        look = LOOKS[pr.estado["look"]]
        guardado = pr.estado["reels"][look.nombre]
        propuesta = Propuesta(**guardado["propuesta"])
        plan = armar_plan(propuesta, montaje.del_reel, look, centros_de_zoom(montaje.tramos, montaje.cajas, look))
        return ResultadoReel(pr.ruta(guardado["archivo"]), montaje, propuesta, plan, [], guardado["bitacora"])

    def editar_ficha(self, pr: Proyecto, cambios: dict) -> dict:
        ficha = ficha_de_json(pr.estado["ficha"])
        idioma = cambios.get("idioma", ficha.idioma)
        if idioma in ficha.textos:
            t = ficha.textos[idioma]
            for campo in ("titulo", "descripcion"):
                if campo in cambios:
                    setattr(t, campo, cambios[campo])
            if "puntos" in cambios:
                t.puntos = cambios["puntos"]
        if "precio" in cambios or "moneda" in cambios:
            monto = float(cambios.get("precio") or (ficha.precio.monto if ficha.precio else 0))
            ficha.precio = precio_valido(monto, cambios.get("moneda") or (ficha.precio.moneda if ficha.precio else "USD"))
        avisos = normalizar_ficha(ficha)
        pr.guardar(ficha=ficha_a_json(ficha), avisos=avisos)
        return pr.estado["ficha"]

    def publicar(self, pr: Proyecto, canales: list[str]) -> list[dict]:
        ficha = ficha_de_json(pr.estado["ficha"])
        reel = pr.ruta(pr.estado["reels"][pr.estado["look"]]["archivo"])
        # Publicar en vivo es una decisión explícita: sin CAMTOSHOP_EN_VIVO=si todo queda en borrador.
        borrador = (secreto("CAMTOSHOP_EN_VIVO") or "").lower() != "si"
        tienda = None
        if canal_conectado("shopify"):
            dominio = secreto("SHOPIFY_TIENDA")
            token = secreto("SHOPIFY_TOKEN") or token_por_credenciales(
                dominio, secreto("SHOPIFY_CLIENT_ID"), secreto("SHOPIFY_CLIENT_SECRET"))
            tienda = TiendaShopify(dominio, token, borrador=borrador)
        catalogo = CatalogoMeta(secreto("META_CATALOGO_ID"), secreto("META_TOKEN"),
                                secreto("SHOPIFY_DOMINIO_PUBLICO") or "", borrador=borrador) \
            if canal_conectado("catalogo_meta") else None
        red = InstagramReels(secreto("IG_USUARIO_ID"), secreto("IG_TOKEN") or secreto("META_TOKEN")) \
            if canal_conectado("instagram") else None
        gancho = (pr.estado.get("analisis") or {}).get("gancho", "")
        resultados = [asdict(r) for r in publicar(ficha, reel, None, canales, tienda, catalogo, red, gancho)]
        pr.guardar(publicaciones=pr.estado.get("publicaciones", []) + [{"t": time.time(), "resultados": resultados}])
        return resultados

    def pie(self, pr: Proyecto) -> str:
        return pie_de_instagram(ficha_de_json(pr.estado["ficha"]), (pr.estado.get("analisis") or {}).get("gancho", ""))

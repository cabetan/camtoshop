"""Servicio de aplicación: arma los adaptadores reales, corre el flujo de un proyecto y guarda su estado.

Cada proyecto vive en su carpeta (datos/proyectos/<id>/) con el video original, los resultados y
un estado.json que la app web consulta para mostrar el progreso y la bitácora del agente.
Los pasos que no dependen entre sí corren en paralelo.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

import requests

from camtoshop.adaptadores import cache
from camtoshop.adaptadores.alineador_xlsr import AlineadorXLSR
from camtoshop.adaptadores.config import canal_conectado, secreto
from camtoshop.adaptadores.fotos_meta import AnalizadorFotosSpark, EscenografoMuse, GuionistaSpark, RevisorFotosSpark
from camtoshop.adaptadores.meta_api import ClienteMeta
from camtoshop.adaptadores.meta_comercio import CatalogoMeta, InstagramReels
from camtoshop.adaptadores.producto_meta import AnalizadorSpark, FotografoMuse, PublicistaMuse, RedactorSpark
from camtoshop.adaptadores.reel_meta import (
    DirectorSpark, EditorSpark, IlustradorMuse, RastreadorSAM, RevisorSpark, TranscriptorMeta,
)
from camtoshop.adaptadores.render_ffmpeg import RenderizadorFFmpeg
from camtoshop.adaptadores.render_fotos import RenderizadorFotos
from camtoshop.adaptadores.repo_comercios import RepoComercios
from camtoshop.adaptadores.sam_mascaras import mascaras
from camtoshop.adaptadores.shopify import TiendaShopify, token_por_credenciales
from camtoshop.dominio.agente_diario import Desempeno
from camtoshop.dominio.anuncios import normalizar_anuncios
from camtoshop.dominio.comercio import Comercio
from camtoshop.dominio.direccion import LOOK_POR_DEFECTO, LOOKS, Propuesta, armar_plan, centros_de_zoom
from camtoshop.dominio.editar_reel import Montaje, Puertos, ResultadoReel, dirigir_y_revisar, preparar_montaje, rehacer
from camtoshop.dominio.producto import (
    Analisis, Ficha, Precio, ProductoDeTienda, Texto, apto_para_reel, elegir_para_reel, mensaje_desde_tienda,
    normalizar_ficha, precio_valido,
)
from camtoshop.dominio.publicacion import pie_de_instagram, publicar
from camtoshop.dominio.reel_fotos import Guion, PuertosFotos, precio_respaldado, reel_desde_fotos

RAIZ = Path(__file__).resolve().parents[2]
DATOS = RAIZ / "datos" / "proyectos"
IDIOMAS_FICHA = ["en", "es"]  # inglés primero; siempre se agrega el idioma del video
FORMATOS_FOTO = {".jpg", ".jpeg", ".png", ".webp", ".heic"}
LOOK_FOTOS = "fotos"


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

    # Quien quiera enterarse cuando un proyecto termina (por ejemplo, el agente de WhatsApp).
    al_terminar = None

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
        if cambios.get("fase") in {"listo", "error"} and Proyecto.al_terminar:
            threading.Thread(target=Proyecto.al_terminar, args=(self,), daemon=True).start()

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
        self.repo_comercios = RepoComercios(datos.parent)
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

    def crear(self, nombre_archivo: str, contenido, extra: dict | None = None) -> Proyecto:
        identificador = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        carpeta = self._datos / identificador
        carpeta.mkdir(parents=True)
        extension = Path(nombre_archivo).suffix.lower() or ".mov"
        with (carpeta / f"original{extension}").open("wb") as destino:
            shutil.copyfileobj(contenido, destino, length=8 * 1024 * 1024)
        pr = Proyecto(carpeta)
        pr.guardar(nombre_archivo=nombre_archivo, **(extra or {}))
        self._cola.submit(self._procesar, pr)
        return pr

    def crear_desde_fotos(self, fotos: list[tuple[str, object]], texto: str,
                          voz: tuple[str, object] | None = None, origen: str = "fotos",
                          extra: dict | None = None) -> Proyecto:
        """Proyecto sin video: fotos del producto, lo que escribió el comerciante y, si quiere, una nota de voz."""
        identificador = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        carpeta = self._datos / identificador
        (carpeta / "material").mkdir(parents=True)
        nombres = []
        for n, (nombre, contenido) in enumerate(fotos):
            destino = carpeta / "material" / f"foto_{n + 1}{Path(nombre).suffix.lower() or '.jpg'}"
            with destino.open("wb") as f:
                shutil.copyfileobj(contenido, f)
            nombres.append(destino.name)
        if voz:
            with (carpeta / "material" / f"voz{Path(voz[0]).suffix.lower() or '.m4a'}").open("wb") as f:
                shutil.copyfileobj(voz[1], f)
        pr = Proyecto(carpeta)
        pr.guardar(tipo="fotos", origen=origen, texto=texto, fotos_material=nombres, look=LOOK_FOTOS,
                   nombre_archivo=f"{len(nombres)} foto" + ("s" if len(nombres) > 1 else ""), **(extra or {}))
        self._cola.submit(self._procesar_fotos, pr)
        return pr

    # --- La tienda como origen ------------------------------------------------------

    def _tienda(self, borrador: bool = True) -> TiendaShopify:
        dominio = secreto("SHOPIFY_TIENDA")
        token = secreto("SHOPIFY_TOKEN") or token_por_credenciales(
            dominio, secreto("SHOPIFY_CLIENT_ID"), secreto("SHOPIFY_CLIENT_SECRET"))
        return TiendaShopify(dominio, token, borrador=borrador)

    def productos_de_tienda(self) -> list[dict]:
        if not canal_conectado("shopify"):
            raise RuntimeError("Shopify no está conectado.")
        return [{**asdict(p), "precio_texto": p.precio.texto() if p.precio else "", "apto": apto_para_reel(p)}
                for p in self._tienda().productos()]

    def reels_desde_tienda(self, handles: list[str]) -> list[str]:
        """Un proyecto por producto elegido (máximo 6). Cada Reel queda para aprobar, nada se publica solo."""
        elegidos = [p for p in self._tienda().productos() if p.handle in set(handles)]
        return [self._reel_de_producto(p).id for p in elegir_para_reel(elegidos, incluir_borradores=True)]

    def _reel_de_producto(self, producto: ProductoDeTienda, extra: dict | None = None) -> Proyecto:
        fotos = []
        for n, url in enumerate(producto.imagenes[:6]):
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            fotos.append((f"tienda_{n + 1}.jpg", io.BytesIO(r.content)))
        pr = self.crear_desde_fotos(fotos, mensaje_desde_tienda(producto), origen="shopify", extra=extra)
        pr.guardar(handle_tienda=producto.handle, nombre_archivo=producto.titulo)
        return pr

    # --- Lo que necesita el agente diario ---------------------------------------------

    def productos_de(self, comercio: Comercio) -> list[ProductoDeTienda]:
        tienda = self._destinos(comercio, True)[0]
        return tienda.productos() if tienda else []

    def reel_de_producto(self, comercio: Comercio, handle: str, celular: str, pedido: str) -> Proyecto:
        producto = next((p for p in self.productos_de(comercio) if p.handle == handle), None)
        if producto is None:
            raise RuntimeError("Ese producto ya no está en la tienda")
        return self._reel_de_producto(producto, {"comercio_id": comercio.id, "celular": celular,
                                                 "pedido_guion": pedido})

    def desempeno_de(self, comercio: Comercio) -> list[Desempeno]:
        """Resultados reales de los Reels recientes. Un Reel sin métricas todavía simplemente no cuenta."""
        red = self._destinos(comercio, True)[2]
        if red is None:
            return []
        salida = []
        for reel in red.reels_recientes():
            try:
                m = red.metricas(reel["id"])
            except RuntimeError:
                continue
            salida.append(Desempeno((reel.get("caption") or "").split("\n")[0], m.get("reach", 0), m.get("likes", 0),
                                    m.get("comments", 0), m.get("shares", 0), m.get("saved", 0)))
        return salida

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
        self._cola.submit(self._procesar_fotos if pr.estado.get("tipo") == "fotos" else self._procesar, pr)

    # --- Reel desde fotos ---------------------------------------------------------

    def _render_fotos(self, analisis: Analisis | None = None) -> RenderizadorFotos:
        c = self.cliente
        conceptos = (analisis.conceptos_sam if analisis else []) + ["product"]
        return RenderizadorFotos(lambda concepto, img, fuente, salida: mascaras(c, concepto, img, fuente, salida),
                                 conceptos)

    def _puertos_fotos(self, pr: Proyecto, analisis: Analisis) -> PuertosFotos:
        c = self.cliente
        return PuertosFotos(GuionistaSpark(c), EscenografoMuse(c, pr.ruta("trabajo") / "escenas"),
                            self._render_fotos(analisis), RevisorFotosSpark(c))

    def _voz(self, pr: Proyecto) -> Path | None:
        return next(pr.ruta("material").glob("voz.*"), None)

    def _procesar_fotos(self, pr: Proyecto):
        try:
            pr.guardar(fase="procesando")
            trabajo = pr.ruta("trabajo")
            trabajo.mkdir(exist_ok=True)
            render = self._render_fotos()
            fotos = [render.preparar(pr.ruta("material") / n, trabajo) for n in pr.estado["fotos_material"]]
            texto = pr.estado.get("texto", "")
            voz, duracion_voz = self._voz(pr), None
            if voz:
                pr.paso("Muse Voice Transcribe escucha la nota de voz", 4)
                turnos = TranscriptorMeta(self.cliente).transcribir(voz, "es")
                dicho = " ".join(t for _, _, t in turnos)
                duracion_voz = turnos[-1][1] if turnos else None
                texto = f"{texto}\n{dicho}".strip()
                pr.guardar(texto_voz=dicho)

            if pr.estado.get("analisis"):
                analisis = Analisis(**pr.estado["analisis"])
            else:
                pr.paso(f"Muse Spark mira {len(fotos)} foto(s) y lee el mensaje", 8)
                analisis = AnalizadorFotosSpark(self.cliente).analizar(fotos, texto)
            pr.guardar(analisis=asdict(analisis))
            pr.paso(f"Producto: {analisis.nombre}" + (f" · {analisis.marca}" if analisis.marca else ""), 15)
            principal = fotos[int(analisis.mejor_cuadro_s)] if int(analisis.mejor_cuadro_s) < len(fotos) else fotos[0]

            with ThreadPoolExecutor(max_workers=3) as hilos:
                catalogo_f = hilos.submit(FotografoMuse(self.cliente, pr.ruta("fotos")).fotos_de_imagen,
                                          principal, analisis)
                ficha_f = hilos.submit(self._ficha, pr, analisis, texto, [])
                pr.paso("SAM 3.1 recorta el producto real en cada foto", 20)
                render = self._render_fotos(analisis)
                recortes = list(hilos.map(lambda f: render.recorte(f, trabajo), fotos))
                pr.paso(f"Producto recortado en {sum(r is not None for r in recortes)} de {len(fotos)} fotos", 35)
                ficha = ficha_f.result()
                if ficha.precio and not precio_respaldado(ficha.precio, texto):
                    ficha.precio = None  # el precio solo sale del comerciante
                    pr.guardar(ficha=ficha_a_json(ficha),
                               avisos=pr.estado.get("avisos", []) + ["Falta el precio: escríbelo en la ficha."])
                catalogo = catalogo_f.result()
                ficha.imagenes = [str(f) for f in catalogo]
                pr.guardar(fotos=[pr.relativa(f) for f in catalogo], ficha=ficha_a_json(ficha))
                pr.paso("Fotos de catálogo listas", 45)

            r = reel_desde_fotos(analisis, texto, fotos, recortes, ficha.precio, voz, duracion_voz,
                                 pr.ruta("reel_fotos.mp4"), self._puertos_fotos(pr, analisis),
                                 lambda t: pr.paso(t), pedido=pr.estado.get("pedido_guion", ""), rondas=1)
            self._guardar_reel_fotos(pr, r)
            self._anuncios(pr, ficha, catalogo[0])
            pr.guardar(fase="listo", progreso=100)
            pr.paso("Listo para publicar")
        except Exception as e:
            pr.guardar(fase="error", error=f"{e}", detalle_error=traceback.format_exc()[-2000:])

    def _guardar_reel_fotos(self, pr: Proyecto, r):
        reels = dict(pr.estado.get("reels", {}))
        reels[LOOK_FOTOS] = {"archivo": pr.relativa(r.reel), "bitacora": r.bitacora,
                             "duracion": round(r.tomas[-1].fin, 1), "guion": asdict(r.guion)}
        pr.guardar(reels=reels, look=LOOK_FOTOS, avisos=pr.estado.get("avisos", []) + r.avisos)

    def _cambio_fotos(self, pr: Proyecto, pedido: str):
        trabajo = pr.ruta("trabajo")
        analisis = Analisis(**pr.estado["analisis"])
        render = self._render_fotos(analisis)
        fotos = [render.preparar(pr.ruta("material") / n, trabajo) for n in pr.estado["fotos_material"]]
        recortes = [render.recorte(f, trabajo) for f in fotos]
        ficha = ficha_de_json(pr.estado["ficha"])
        texto = "\n".join(x for x in (pr.estado.get("texto", ""), pr.estado.get("texto_voz", "")) if x)
        voz = self._voz(pr)
        duracion = None
        if voz:
            duracion = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                             "-of", "csv=p=0", str(voz)], capture_output=True, text=True).stdout or 0) or None
        anterior = Guion(**pr.estado["reels"][LOOK_FOTOS]["guion"])
        r = reel_desde_fotos(analisis, texto, fotos, recortes, ficha.precio, voz, duracion,
                             pr.ruta(f"reel_fotos_{int(time.time())}.mp4"), self._puertos_fotos(pr, analisis),
                             lambda t: pr.paso(t), pedido=pedido, anterior=anterior, rondas=0)
        self._guardar_reel_fotos(pr, r)

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
                if pr.estado.get("tipo") == "fotos":
                    self._cambio_fotos(pr, pedido)
                    pr.guardar(fase="listo", progreso=100)
                    return
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

    def _destinos(self, comercio: Comercio | None, borrador: bool):
        """(tienda, catálogo, red) donde publica el comercio: sus cuentas, o las del servidor si es la demo."""
        if comercio is None or comercio.demo:
            tienda = self._tienda(borrador) if canal_conectado("shopify") else None
            catalogo = CatalogoMeta(secreto("META_CATALOGO_ID"), secreto("META_TOKEN"),
                                    secreto("SHOPIFY_DOMINIO_PUBLICO") or "", borrador=borrador) \
                if canal_conectado("catalogo_meta") else None
            red = InstagramReels(secreto("IG_USUARIO_ID"), secreto("IG_TOKEN") or secreto("META_TOKEN")) \
                if canal_conectado("instagram") else None
            return tienda, catalogo, red
        con, repo = comercio.conexiones, self.repo_comercios
        meta, shopify = repo.token(comercio.id, "meta"), repo.token(comercio.id, "shopify")
        tienda = TiendaShopify(con.shopify_tienda, shopify, borrador=borrador) if con.shopify_tienda and shopify else None
        catalogo = CatalogoMeta(con.catalogo_id, meta, borrador=borrador) if con.catalogo_id and meta else None
        red = InstagramReels(con.instagram_id, meta) if con.instagram_id and meta else None
        return tienda, catalogo, red

    def canales_de(self, comercio: Comercio | None) -> dict[str, bool]:
        if comercio is None or comercio.demo:
            return self.canales()
        tienda, catalogo, red = self._destinos(comercio, True)
        return {"shopify": tienda is not None, "catalogo_meta": catalogo is not None, "instagram": red is not None}

    def publicar(self, pr: Proyecto, canales: list[str], comercio: Comercio | None = None) -> list[dict]:
        ficha = ficha_de_json(pr.estado["ficha"])
        reel = pr.ruta(pr.estado["reels"][pr.estado["look"]]["archivo"])
        # Publicar en vivo es una decisión explícita: sin CAMTOSHOP_EN_VIVO=si todo queda en borrador.
        borrador = (secreto("CAMTOSHOP_EN_VIVO") or "").lower() != "si"
        if comercio is None and pr.estado.get("comercio_id"):
            comercio = self.repo_comercios.obtener(pr.estado["comercio_id"])
        tienda, catalogo, red = self._destinos(comercio, borrador)
        gancho = (pr.estado.get("analisis") or {}).get("gancho", "")
        resultados = [asdict(r) for r in publicar(ficha, reel, None, canales, tienda, catalogo, red, gancho)]
        pr.guardar(publicaciones=pr.estado.get("publicaciones", []) + [{"t": time.time(), "resultados": resultados}])
        return resultados

    def pie(self, pr: Proyecto) -> str:
        return pie_de_instagram(ficha_de_json(pr.estado["ficha"]), (pr.estado.get("analisis") or {}).get("gancho", ""))

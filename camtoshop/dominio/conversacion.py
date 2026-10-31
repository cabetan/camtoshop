"""Conversación por WhatsApp con un comercio: qué hacer con cada mensaje que llega a la línea.

Reglas de los auditores: responder enseguida, máximo dos preguntas (qué es y cuánto vale),
nada se publica sin el botón «Publicar» sobre ESA versión del Reel, y cualquier cambio invalida
la aprobación anterior. Estas funciones solo deciden; el servicio hace lo que deciden.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from camtoshop.dominio.comercio import Comercio, registrar_uso
from camtoshop.dominio.reel_fotos import montos_en

MAX_FOTOS = 8

TEXTOS = {
    "es": {
        "desconocido": "¡Hola! Soy Camtoshop 📸 Para crear contenido con tus fotos, registra tu negocio en {portal} "
                       "y vincula este número con el código que te da el portal.",
        "vinculado": "¡Listo, {nombre}! Este número quedó vinculado. Mándame fotos de un producto y dime qué es y "
                     "cuánto vale.",
        "ayuda": "Mándame de 1 a 8 fotos de un producto y dime qué es y cuánto vale. Ejemplo: «Vela de soya, "
                 "lavanda, 85 mil». Si prefieres, cuéntamelo en una nota de voz.",
        "que_es": "📸 ¡Buena foto! ¿Qué es y cuánto vale? (Puedes mandar más fotos o una nota de voz.)",
        "precio": "¿Y cuánto vale? Escríbelo en números, por ejemplo «85 mil».",
        "recibido": "¡Recibido! 🎬 En unos 3 minutos te mando el Reel para que lo apruebes.",
        "ocupado": "Sigo trabajando en tu Reel anterior; en cuanto esté te lo mando.",
        "limite": "Por hoy ya hiciste {n} Reels, que es el máximo diario. ¡Mañana seguimos!",
        "aprobar": "Aquí está tu Reel ✨\n\n{pie}\n\n¿Lo publico?",
        "cual_cambio": "¿Qué le cambio? Por ejemplo: «más calmado», «otro gancho» o «el precio es 90 mil».",
        "otra_version": "Ese botón es de una versión anterior. Usa los botones del último Reel que te mandé.",
        "publicando": "Publicando… 🚀",
        "descartado": "Listo, lo descarté. Cuando quieras, mándame otro producto.",
        "error": "Uy, algo falló creando tu Reel: {error}. ¿Lo intentamos otra vez con otras fotos?",
        "hoy_no": "Listo, hoy descansamos. Mañana te propongo otra cosa ☀️",
        "sin_otro": "No tengo otro producto para proponerte hoy. Mándame una foto y hacemos uno nuevo.",
    },
    "en": {
        "desconocido": "Hi! I'm Camtoshop 📸 To turn your photos into content, sign up at {portal} and link this "
                       "number with the code the portal gives you.",
        "vinculado": "Done, {nombre}! This number is linked. Send me photos of a product and tell me what it is "
                     "and its price.",
        "ayuda": "Send me 1 to 8 photos of a product and tell me what it is and its price. Example: «Soy candle, "
                 "lavender, $25». A voice note works too.",
        "que_es": "📸 Nice photo! What is it and how much is it? (You can send more photos or a voice note.)",
        "precio": "And the price? Write it in numbers, e.g. «$25».",
        "recibido": "Got it! 🎬 In about 3 minutes I'll send you the Reel to approve.",
        "ocupado": "I'm still working on your previous Reel; I'll send it as soon as it's ready.",
        "limite": "You've made {n} Reels today, the daily maximum. See you tomorrow!",
        "aprobar": "Here's your Reel ✨\n\n{pie}\n\nShall I publish it?",
        "cual_cambio": "What should I change? e.g. «calmer», «another hook» or «the price is $30».",
        "otra_version": "That button belongs to an older version. Use the buttons on the latest Reel I sent.",
        "publicando": "Publishing… 🚀",
        "descartado": "Done, discarded. Send me another product whenever you like.",
        "error": "Oops, something failed while making your Reel: {error}. Shall we try again with other photos?",
        "hoy_no": "Sure, we'll rest today. I'll suggest something else tomorrow ☀️",
        "sin_otro": "I don't have another product to suggest today. Send me a photo and we'll make a new one.",
    },
}
BOTONES = {"es": ("Publicar", "Cambiar", "Descartar"), "en": ("Publish", "Change", "Discard")}
BOTONES_PROPUESTA = {"es": ("Hazlo", "Otro producto", "Hoy no"), "en": ("Make it", "Another one", "Not today")}


@dataclass
class Mensaje:
    tipo: str  # texto | imagen | audio | video | boton
    texto: str = ""  # texto o pie de foto
    media: str = ""  # id del archivo en WhatsApp
    boton: str = ""  # id del botón tocado


@dataclass
class Chat:
    celular: str
    fotos: list[str] = field(default_factory=list)
    voz: str = ""
    texto: str = ""
    preguntas: int = 0
    estado: str = ""  # "" | datos | generando | aprobacion | cambio
    proyecto: str = ""
    version: str = ""
    propuesta: str = ""  # producto que el agente diario propuso y sigue sin respuesta
    pedido_propuesta: str = ""  # lo aprendido de las métricas, para el guion de ese Reel


@dataclass(frozen=True)
class Responder:
    texto: str


@dataclass(frozen=True)
class CrearDesdeFotos:
    fotos: tuple[str, ...]
    texto: str
    voz: str


@dataclass(frozen=True)
class CrearDesdeVideo:
    video: str
    texto: str


@dataclass(frozen=True)
class CrearDesdeProducto:
    producto: str
    pedido: str


@dataclass(frozen=True)
class OtraPropuesta:
    producto: str


@dataclass(frozen=True)
class Publicar:
    proyecto: str


@dataclass(frozen=True)
class PedirCambio:
    proyecto: str
    pedido: str


def t(comercio: Comercio | None, clave: str, **datos) -> str:
    idioma = comercio.idioma if comercio and comercio.idioma in TEXTOS else "es"
    return TEXTOS[idioma][clave].format(**datos)


def boton_id(accion: str, proyecto: str, version: str) -> str:
    return f"{accion}|{proyecto}|{version}"


def botones(comercio: Comercio, proyecto: str, version: str) -> list[tuple[str, str]]:
    """(id, título) de los tres botones de aprobación, atados a esta versión del Reel."""
    titulos = BOTONES.get(comercio.idioma, BOTONES["es"])
    return [(boton_id(a, proyecto, version), titulo) for a, titulo in zip(("publicar", "cambiar", "descartar"), titulos)]


def botones_de_propuesta(comercio: Comercio, producto: str) -> list[tuple[str, str]]:
    titulos = BOTONES_PROPUESTA.get(comercio.idioma, BOTONES_PROPUESTA["es"])
    return [(boton_id(a, producto, ""), titulo) for a, titulo in zip(("hazlo", "otro", "hoy_no"), titulos)]


def _responder_propuesta(chat: Chat, accion: str, producto: str, comercio: Comercio, dia: str) -> list:
    if producto != chat.propuesta:
        return [Responder(t(comercio, "otra_version"))]
    if chat.estado == "generando":
        return [Responder(t(comercio, "ocupado"))]
    if accion == "otro":
        return [OtraPropuesta(producto)]
    pedido, chat.propuesta, chat.pedido_propuesta = chat.pedido_propuesta, "", ""
    if accion == "hoy_no":
        return [Responder(t(comercio, "hoy_no"))]
    if not registrar_uso(comercio, dia):
        return [Responder(t(comercio, "limite", n=comercio.usos.get(dia, 0)))]
    comercio.promovidos[producto] = dia
    chat.estado = "generando"
    return [CrearDesdeProducto(producto, pedido), Responder(t(comercio, "recibido"))]


def _arrancar(chat: Chat, comercio: Comercio, dia: str) -> list:
    if not registrar_uso(comercio, dia):
        chat.fotos, chat.voz, chat.texto, chat.preguntas, chat.estado = [], "", "", 0, ""
        return [Responder(t(comercio, "limite", n=comercio.usos.get(dia, 0)))]
    accion = CrearDesdeFotos(tuple(chat.fotos), chat.texto.strip(), chat.voz)
    chat.fotos, chat.voz, chat.texto, chat.preguntas, chat.estado = [], "", "", 0, "generando"
    return [accion, Responder(t(comercio, "recibido"))]


def atender(chat: Chat, msg: Mensaje, comercio: Comercio, dia: str) -> list:
    """Decide qué hacer con un mensaje de un comercio registrado. Modifica `chat`."""
    if msg.tipo == "boton":
        accion, proyecto, version = (msg.boton.split("|") + ["", "", ""])[:3]
        if accion in {"hazlo", "otro", "hoy_no"}:
            return _responder_propuesta(chat, accion, proyecto, comercio, dia)
        if proyecto != chat.proyecto or version != chat.version or chat.estado != "aprobacion":
            return [Responder(t(comercio, "otra_version"))]
        if accion == "publicar":
            chat.estado = ""
            return [Publicar(proyecto), Responder(t(comercio, "publicando"))]
        if accion == "cambiar":
            chat.estado = "cambio"
            return [Responder(t(comercio, "cual_cambio"))]
        chat.estado, chat.version = "", ""
        return [Responder(t(comercio, "descartado"))]

    if chat.estado == "generando":
        return [Responder(t(comercio, "ocupado"))]

    if msg.tipo == "texto" and chat.estado == "cambio" and msg.texto.strip():
        chat.estado, chat.version = "generando", ""  # la aprobación anterior ya no vale
        return [PedirCambio(chat.proyecto, msg.texto.strip()), Responder(t(comercio, "recibido"))]

    if msg.tipo == "video":
        if not registrar_uso(comercio, dia):
            return [Responder(t(comercio, "limite", n=comercio.usos.get(dia, 0)))]
        chat.estado = "generando"
        return [CrearDesdeVideo(msg.media, msg.texto), Responder(t(comercio, "recibido"))]

    if msg.tipo == "imagen":
        if chat.estado in {"aprobacion", "cambio"}:  # producto nuevo: el anterior queda sin aprobar
            chat.estado, chat.version = "", ""
        if len(chat.fotos) < MAX_FOTOS:
            chat.fotos.append(msg.media)
        if msg.texto:
            chat.texto += " " + msg.texto
        if montos_en(chat.texto):
            return _arrancar(chat, comercio, dia)
        chat.estado = "datos"
        return [Responder(t(comercio, "que_es"))] if len(chat.fotos) == 1 else []

    if msg.tipo == "audio":
        chat.voz = msg.media
        if chat.fotos:
            return _arrancar(chat, comercio, dia)  # la nota de voz trae qué es y cuánto vale
        return [Responder(t(comercio, "ayuda"))]

    if msg.tipo == "texto" and chat.fotos:
        chat.texto += " " + msg.texto
        if montos_en(chat.texto) or chat.preguntas >= 1:
            return _arrancar(chat, comercio, dia)  # sin precio tras preguntar una vez: el Reel sale sin precio
        chat.preguntas += 1
        return [Responder(t(comercio, "precio"))]

    return [Responder(t(comercio, "ayuda"))]


def listo_para_aprobar(chat: Chat, proyecto: str, version: str) -> None:
    """El Reel terminó: desde ahora solo los botones de esta versión publican."""
    chat.proyecto, chat.version, chat.estado = proyecto, version, "aprobacion"


def fallo(chat: Chat) -> None:
    chat.estado = ""

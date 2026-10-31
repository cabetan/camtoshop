"""Comercios: quién usa Camtoshop, desde qué celulares escribe y a qué cuentas publica.

Un comercio se registra en el portal, conecta sus cuentas y vincula sus celulares. Para vincular
un celular, el portal le da un código y el comercio lo manda a la línea de WhatsApp desde ese
celular: así se prueba que el número es suyo sin que Camtoshop tenga que escribirle primero.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field

VIGENCIA_CODIGO = 30 * 60  # segundos
LIMITE_DIARIO = 15  # Reels por comercio y día: protege los créditos y frena abusos
_CODIGO = re.compile(r"\bCAMTO[- ]?(\d{4})\b", re.I)


@dataclass
class Conexiones:
    """Identificadores públicos de las cuentas conectadas. Los tokens viven aparte, cifrados."""
    instagram_id: str = ""
    instagram_usuario: str = ""
    pagina_id: str = ""
    pagina_nombre: str = ""
    catalogo_id: str = ""
    shopify_tienda: str = ""

    def canales(self) -> dict[str, bool]:
        return {"instagram": bool(self.instagram_id), "catalogo_meta": bool(self.catalogo_id),
                "shopify": bool(self.shopify_tienda)}


@dataclass
class Comercio:
    id: str
    nombre: str
    correo: str
    celulares: list[str] = field(default_factory=list)
    codigos: dict[str, float] = field(default_factory=dict)  # código → vence (epoch)
    conexiones: Conexiones = field(default_factory=Conexiones)
    usos: dict[str, int] = field(default_factory=dict)  # "AAAA-MM-DD" → Reels pedidos
    promovidos: dict[str, str] = field(default_factory=dict)  # producto → último día que se promovió
    ultima_propuesta: str = ""  # día de la última propuesta del agente diario
    idioma: str = "es"
    demo: bool = False  # la cuenta propia de Camtoshop: publica con las credenciales del servidor


def normalizar_celular(texto: str, pais: str = "57") -> str:
    """Solo dígitos con indicativo: «300 123 4567» → «573001234567». WhatsApp manda los números así."""
    digitos = re.sub(r"\D", "", texto or "")
    if len(digitos) == 10 and pais == "57" and digitos.startswith("3"):
        digitos = pais + digitos
    return digitos


def nuevo_codigo(comercio: Comercio, ahora: float) -> str:
    """Código para vincular un celular. Se guarda con su vencimiento y se limpian los vencidos."""
    comercio.codigos = {c: v for c, v in comercio.codigos.items() if v > ahora}
    codigo = f"{secrets.randbelow(9000) + 1000}"
    while codigo in comercio.codigos:
        codigo = f"{secrets.randbelow(9000) + 1000}"
    comercio.codigos[codigo] = ahora + VIGENCIA_CODIGO
    return f"CAMTO-{codigo}"


def codigo_en(texto: str) -> str | None:
    m = _CODIGO.search(texto or "")
    return m.group(1) if m else None


def vincular(comercios: list[Comercio], celular: str, texto: str, ahora: float) -> Comercio | None:
    """Si el texto trae un código vigente de algún comercio, el celular queda vinculado a ese comercio.

    Un celular pertenece a un solo comercio: si ya estaba en otro, se mueve.
    """
    codigo = codigo_en(texto)
    if not codigo:
        return None
    dueno = next((c for c in comercios if c.codigos.get(codigo, 0) > ahora), None)
    if dueno is None:
        return None
    for c in comercios:
        if celular in c.celulares and c is not dueno:
            c.celulares.remove(celular)
    if celular not in dueno.celulares:
        dueno.celulares.append(celular)
    del dueno.codigos[codigo]
    return dueno


def comercio_de(celular: str, comercios: list[Comercio]) -> Comercio | None:
    return next((c for c in comercios if celular in c.celulares), None)


def registrar_uso(comercio: Comercio, dia: str, limite: int = LIMITE_DIARIO) -> bool:
    """Cuenta un Reel pedido hoy; False si el comercio ya llegó a su límite diario."""
    if comercio.usos.get(dia, 0) >= limite:
        return False
    comercio.usos = {d: n for d, n in comercio.usos.items() if d >= dia[:8]}  # solo el mes en curso
    comercio.usos[dia] = comercio.usos.get(dia, 0) + 1
    return True

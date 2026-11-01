"""Los estilos de Reel: cada uno es una dirección de arte y un montaje, no un cambio de color.

`arte` es el pedido que recibe el director creativo (en inglés, porque va a los modelos); el resto
le dice al render cómo cortar, mover, colorear y escribir. Escoger un estilo sugiere su letra y música,
y el comercio las puede cambiar.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Estilo:
    id: str
    arte: str  # dirección de arte de los planos
    ritmo: float  # 1 es el tiempo normal; menos de 1 corta más rápido
    transicion: str  # disolver | corte | flash | empuje | telon
    texto: str  # pie | gigante | portada | historia | polaroid | palabra | cinemascope
    color: str  # natural | calido | bn | vivo | lavado | neon
    fondo: str  # marca | claro | plano: sobre qué sale el producto real con el precio
    fuente: str
    musica: str
    mayusculas: bool = False
    grano: float = 0.0
    vineta: float = 0.0
    barras: bool = False
    temblor: bool = False  # cámara en mano
    golpe: bool = False  # cada plano entra con un zoom seco
    movimiento: float = 1.0  # cuánto se mueve la cámara


ESTILOS = {e.id: e for e in (
    Estilo("cine", "A short film at dusk. Low warm directional light, deep shadows, a lived-in real location, "
           "long lens compression, the light changes from shot to shot as evening falls.",
           1.15, "disolver", "pie", "calido", "plano", "playfair", "elegante", grano=3, vineta=.38),
    Estilo("revista", "A high-fashion magazine editorial. Bold graphic composition, hard sculpted studio light, "
           "seamless paper backdrops, strong diagonal shadows, a stylist's precise props.",
           1.0, "empuje", "portada", "natural", "claro", "playfair", "cinematica"),
    Estilo("estudio", "A flagship product launch film. The product alone on seamless color sweeps in the brand "
           "colors, perfect reflections, rim light, dramatic angles and pure geometry.",
           .85, "telon", "gigante", "vivo", "marca", "poppins", "pulso", mayusculas=True, golpe=True),
    Estilo("noche", "A rain-soaked city at night. Colored neon light in the brand colors spilling over the product, "
           "wet asphalt reflections, haze, deep blacks, cyberpunk atmosphere without any readable signs.",
           .8, "flash", "palabra", "neon", "plano", "barlow", "pulso", mayusculas=True, grano=2, vineta=.45),
    Estilo("macro", "Extreme macro cinematography. Fill the frame with the real textures, stitching, grain and "
           "finish of the product, razor thin focus, slow raking light, only details until the last shot.",
           1.25, "disolver", "pie", "natural", "plano", "playfair", "elegante", vineta=.3, movimiento=1.6),
    Estilo("hogar", "An honest moment shot on a phone by a friend. Morning window light, a real messy-enough home, "
           "coffee, hands just out of frame, nothing styled, believable and warm.",
           .95, "corte", "historia", "natural", "plano", "poppins", "tarde", temblor=True),
    Estilo("oferta", "A loud retail campaign. Saturated solid backgrounds in the brand colors, the product huge and "
           "tilted, flying shadows, confetti-like geometric shapes, pure energy.",
           .7, "flash", "gigante", "vivo", "marca", "barlow", "energia", mayusculas=True, golpe=True),
    Estilo("analogo", "Found 35mm film from a summer trip. Direct on-camera flash, sun flares, faded colors, "
           "a beach, a car seat or a picnic blanket, imperfect framing and real nostalgia.",
           1.05, "corte", "polaroid", "lavado", "plano", "caveat", "tarde", grano=9, vineta=.25, movimiento=.5),
    Estilo("surreal", "Surreal advertising in the style of an art photo book. The product monumental like a building "
           "in impossible landscapes: salt flats, floating above clouds, on a staircase in the desert, soft dream light.",
           1.1, "disolver", "palabra", "natural", "plano", "playfair", "cinematica", vineta=.2, movimiento=1.3),
    Estilo("monocromo", "A black and white luxury campaign. Extreme contrast, a single hard shaft of light, "
           "architecture and shadow, silence, the elegance of an old perfume film.",
           1.1, "disolver", "cinemascope", "bn", "plano", "barlow", "cinematica", mayusculas=True, grano=5,
           vineta=.3, barras=True),
)}
PULSOS = {"energia": 60 / 124, "calida": 60 / 84, "elegante": 60 / 66, "pulso": 60 / 110, "tarde": 60 / 92,
          "cinematica": 1.0}  # segundos por golpe de cada pista propia
ESTILO_INICIAL = "cine"
ANTIGUOS = {"impacto": "oferta", "color": "estudio", "limpio": "revista"}  # comercios de antes del catálogo


def estilo_de(id_estilo: str) -> Estilo:
    return ESTILOS.get(ANTIGUOS.get(id_estilo, id_estilo)) or ESTILOS[ESTILO_INICIAL]

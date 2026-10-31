#!/usr/bin/env python3
"""Compone las pistas de Camtoshop desde cero: son nuestras, sin licencias de terceros.

Cada pista son ocho compases que empalman exacto, porque el render las repite si el Reel dura más.
Uso: .venv/bin/python scripts/hacer_musica.py
"""

import subprocess
import tempfile
from pathlib import Path

import numpy as np

SR = 44100
DESTINO = Path(__file__).resolve().parents[1] / "camtoshop" / "assets" / "musica"
RNG = np.random.default_rng(7)


def hz(nota: int) -> float:
    return 440 * 2 ** ((nota - 69) / 12)


def tono(f: float, seg: float, armonicos=(1, .5, .25), ataque=.01, caida=3.0) -> np.ndarray:
    t = np.arange(int(seg * SR)) / SR
    onda = sum(a * np.sin(2 * np.pi * f * (n + 1) * t) for n, a in enumerate(armonicos))
    return onda * np.minimum(t / ataque, 1) * np.exp(-caida * t) * np.minimum((seg - t) / .02, 1)


def bombo(seg=.28):
    t = np.arange(int(seg * SR)) / SR
    return np.sin(2 * np.pi * (50 * t + 28 * (1 - np.exp(-30 * t)))) * np.exp(-9 * t)


def ruido(seg, caida, alto=True):
    n = RNG.standard_normal(int(seg * SR))
    if alto:
        n = np.diff(n, prepend=0)
    return n * np.exp(-caida * np.arange(len(n)) / SR) * .3


def sumar(pista, sonido, seg, gan=1.0):
    i = int(seg * SR) % len(pista)
    fin = min(len(sonido), len(pista) - i)
    pista[i:i + fin] += sonido[:fin] * gan
    pista[:len(sonido) - fin] += sonido[fin:] * gan  # lo que sobra cae al inicio: el empalme no se oye


def eco(p, seg, gan):
    return p + gan * np.roll(p, int(seg * SR)) + gan ** 2 * np.roll(p, int(2 * seg * SR))


def sala(p, seg=1.4, mezcla=.22):
    n = int(seg * SR)
    cola = RNG.standard_normal(n) * np.exp(-5 * np.arange(n) / n * 2)
    cola /= np.sqrt((cola ** 2).sum())
    largo = len(p)
    return p + mezcla * np.fft.irfft(np.fft.rfft(p) * np.fft.rfft(cola, largo), largo)


def energia():
    bpm, compases = 124, 8
    negra = 60 / bpm
    pista, medios, bajo = (np.zeros(int(negra * 4 * compases * SR)) for _ in range(3))
    acordes = [(45, 60, 64, 69), (41, 60, 65, 69), (48, 60, 64, 67), (43, 59, 62, 67)]  # Am F C G
    for c in range(compases):
        raiz, *notas = acordes[c % 4]
        ini = c * 4 * negra
        for b in range(4):
            sumar(pista, bombo(), ini + b * negra, .95)
            sumar(pista, ruido(.08, 60), ini + (b + .5) * negra, .35)
            if b % 2:
                sumar(pista, ruido(.2, 22, False), ini + b * negra, .4)
        for paso in (0, .75, 1.5, 2.5, 3, 3.5):
            sumar(bajo, tono(hz(raiz), .28, (1, .35, .1), .005, 5), ini + paso * negra, .55)
        for paso in (.5, 1.5, 2.25, 3.25):
            for n in notas:
                sumar(medios, tono(hz(n + 12), .22, (1, .6, .35, .2), .004, 12), ini + paso * negra, .13)
        sumar(medios, tono(hz(notas[-1] + 24), .3, (1, .3), .004, 9), ini + 3.75 * negra, .12)
    return pista + bajo + sala(eco(medios, negra * .75, .3), mezcla=.15)


def calida():
    bpm, compases = 84, 8
    negra = 60 / bpm
    pista, teclas, bajo = (np.zeros(int(negra * 4 * compases * SR)) for _ in range(3))
    acordes = [(48, 64, 67, 71, 74), (45, 60, 64, 67, 71), (50, 60, 65, 69, 72), (43, 59, 62, 65, 69)]  # Cmaj9 Am9 Dm9 G9
    for c in range(compases):
        raiz, *notas = acordes[c % 4]
        ini = c * 4 * negra
        sumar(pista, bombo(.35), ini, .7)
        sumar(pista, bombo(.35), ini + 2.5 * negra, .55)
        for b in (1, 3):
            sumar(pista, ruido(.18, 20, False), ini + b * negra, .22)
        for corchea in range(8):
            demora = .035 if corchea % 2 else 0  # el tresillo perezoso le da el aire relajado
            sumar(pista, ruido(.05, 70), ini + corchea * negra / 2 + demora, .16)
        sumar(bajo, tono(hz(raiz), negra * 1.8, (1, .3), .02, 1.2), ini, .5)
        sumar(bajo, tono(hz(raiz + 7), negra, (1, .3), .02, 2), ini + 2.5 * negra, .35)
        for n in notas:
            sumar(teclas, tono(hz(n), negra * 3, (1, .4, .05), .012, 1.3), ini + .02 * (n % 3), .15)
            sumar(teclas, tono(hz(n), negra * 1.4, (1, .4, .05), .012, 2), ini + 2.5 * negra, .09)
    return pista + bajo + sala(teclas, mezcla=.3)


def elegante():
    bpm, compases = 66, 8
    negra = 60 / bpm
    pista, piano, colchon = (np.zeros(int(negra * 4 * compases * SR)) for _ in range(3))
    acordes = [(40, 55, 59, 64, 67), (36, 55, 60, 64, 72), (43, 55, 62, 67, 71), (38, 54, 62, 66, 69)]  # Em C G D
    for c in range(compases):
        raiz, *notas = acordes[c % 4]
        ini = c * 4 * negra
        sumar(colchon, tono(hz(raiz + 12), negra * 4.5, (1, .2), 1.2, .2), ini, .16)
        for n in notas[:3]:
            sumar(colchon, tono(hz(n), negra * 4.5, (1, .15), 1.5, .2), ini, .06)
        for i, n in enumerate(notas + notas[::-1][1:3] + notas[:1]):
            sumar(piano, tono(hz(n + 12), negra * 2.5, (1, .28, .1, .04), .006, 1.6), ini + i * negra / 2, .17)
    return pista + sala(colchon, 2, .3) + sala(piano, 2, .4)


def exportar(nombre, pista):
    estereo = np.stack([pista, np.roll(pista, 90)], 1)
    estereo = estereo / np.abs(estereo).max() * .89
    with tempfile.NamedTemporaryFile(suffix=".f32") as crudo:
        estereo.astype("<f4").tofile(crudo.name)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", crudo.name,
                        "-c:a", "aac", "-b:a", "160k", str(DESTINO / f"{nombre}.m4a")], check=True)


if __name__ == "__main__":
    DESTINO.mkdir(parents=True, exist_ok=True)
    for nombre, pista in (("energia", energia()), ("calida", calida()), ("elegante", elegante())):
        exportar(nombre, pista)
        print(nombre, f"{len(pista) / SR:.1f} s")

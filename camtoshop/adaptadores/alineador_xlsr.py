"""Alineación forzada palabra por palabra con wav2vec2 XLSR-53 (pesos abiertos de Meta).

Muse Voice Transcribe da el texto por turnos; este adaptador fija el inicio y el
fin de cada palabra sobre el audio real.
"""

from __future__ import annotations

import subprocess
import unicodedata
import wave
from pathlib import Path

import numpy as np
import torch
from torchaudio.functional import forced_align, merge_tokens
from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

from camtoshop.dominio.reel import Palabra

MODELOS = {
    "es": "jonatasgrosman/wav2vec2-large-xlsr-53-spanish",
    "en": "jonatasgrosman/wav2vec2-large-xlsr-53-english",
}
MUESTREO = 16000
# Holgura alrededor de cada turno: Voice Transcribe a veces corta el borde de la primera sílaba.
HOLGURA = 0.25


def leer_audio(video: Path) -> np.ndarray:
    crudo = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(video), "-map", "0:a:0", "-ac", "1",
                            "-ar", str(MUESTREO), "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(crudo, dtype=np.int16).astype(np.float32) / 32768.0


def escribir_wav(audio: np.ndarray, destino: Path) -> Path:
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(MUESTREO)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
    return destino


class AlineadorXLSR:
    def __init__(self):
        self._cargados: dict[str, tuple[Wav2Vec2ForCTC, Wav2Vec2Processor]] = {}

    def _modelo(self, idioma: str):
        if idioma not in self._cargados:
            nombre = MODELOS.get(idioma[:2], MODELOS["en"])
            modelo = Wav2Vec2ForCTC.from_pretrained(nombre).eval()
            self._cargados[idioma] = (modelo, Wav2Vec2Processor.from_pretrained(nombre))
        return self._cargados[idioma]

    def alinear(self, video: Path, turnos: list[tuple[float, float, str]], idioma: str) -> list[Palabra]:
        audio = leer_audio(video)
        modelo, procesador = self._modelo(idioma)
        vocab = procesador.tokenizer.get_vocab()
        palabras: list[Palabra] = []
        for inicio, fin, texto in turnos:
            a = max(0.0, inicio - HOLGURA)
            b = min(len(audio) / MUESTREO, fin + HOLGURA)
            palabras += self._alinear_turno(audio[int(a * MUESTREO):int(b * MUESTREO)], a, texto.split(),
                                            modelo, procesador, vocab)
        return palabras

    def _alinear_turno(self, audio, desfase, textos, modelo, procesador, vocab) -> list[Palabra]:
        fichas = [_fichas(t, vocab) for t in textos]
        objetivo, duenos = [], []
        for i, f in enumerate(fichas):
            if not f:
                continue
            if objetivo:
                objetivo.append(vocab["|"])
                duenos.append(None)
            objetivo += f
            duenos += [i] * len(f)

        entrada = procesador(audio, sampling_rate=MUESTREO, return_tensors="pt").input_values
        with torch.inference_mode():
            emisiones = torch.log_softmax(modelo(entrada).logits, dim=-1)
        segundos_por_cuadro = len(audio) / MUESTREO / emisiones.shape[1]

        tiempos: dict[int, list[float]] = {}
        if objetivo and len(objetivo) <= emisiones.shape[1]:
            alineacion, puntajes = forced_align(emisiones, torch.tensor([objetivo], dtype=torch.int32),
                                                blank=procesador.tokenizer.pad_token_id)
            for ficha, dueno in zip(merge_tokens(alineacion[0], puntajes[0].exp()), duenos):
                if dueno is None:
                    continue
                t0, t1 = desfase + ficha.start * segundos_por_cuadro, desfase + ficha.end * segundos_por_cuadro
                previo = tiempos.get(dueno)
                tiempos[dueno] = [previo[0], t1] if previo else [t0, t1]

        return _rellenar(textos, tiempos, desfase, desfase + len(audio) / MUESTREO)


def _fichas(texto: str, vocab: dict[str, int]) -> list[int]:
    limpio = unicodedata.normalize("NFC", texto.lower())
    salida = []
    for c in limpio:
        for variante in (c, c.upper()):
            if variante in vocab and variante not in ("|", "<pad>", "<s>", "</s>", "<unk>"):
                salida.append(vocab[variante])
                break
    return salida


def _rellenar(textos: list[str], tiempos: dict[int, list[float]], inicio: float, fin: float) -> list[Palabra]:
    """Las palabras sin sonido alineable ("$50", "85.000") se reparten entre sus vecinas."""
    salida = []
    for i, texto in enumerate(textos):
        if i in tiempos:
            t0, t1 = tiempos[i]
        else:
            antes = max((tiempos[j][1] for j in tiempos if j < i), default=inicio)
            despues = min((tiempos[j][0] for j in tiempos if j > i), default=fin)
            t0, t1 = antes, max(despues, antes + 0.1)
        salida.append(Palabra(texto, round(t0, 3), round(t1, 3)))
    return salida

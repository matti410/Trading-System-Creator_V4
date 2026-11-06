"""
Le funzioni di prova dell'ottimizzatore (docs/82 §4): funzioni matematiche con il minimo noto, classiche nella
letteratura sugli algoritmi di ottimizzazione. Servono a collaudarlo e a tararlo prima del mercato, mai sul mercato.

Tutte hanno il minimo globale uguale a 0. Si minimizzano; l'ottimizzatore massimizza, per questo `obiettivo` cambia segno.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Sequence

from .ottimizzatore import Reale, Spazio


def sphere(x: Sequence[float]) -> float:
    """Una sola valle liscia, minimo in 0. La prova più facile."""
    return sum(v * v for v in x)


def rastrigin(x: Sequence[float]) -> float:
    """Una griglia regolare di minimi locali, minimo globale in 0: qui ci si incastra."""
    return 10.0 * len(x) + sum(v * v - 10.0 * math.cos(2.0 * math.pi * v) for v in x)


def rosenbrock(x: Sequence[float]) -> float:
    """Una valle stretta e curva, minimo in 1: si trova la valle, è difficile percorrerla."""
    return sum(100.0 * (x[i + 1] - x[i] ** 2) ** 2 + (1.0 - x[i]) ** 2 for i in range(len(x) - 1))


def ackley(x: Sequence[float]) -> float:
    """Quasi piatta lontano dal centro, tanti minimi locali, un buco in 0."""
    n = len(x)
    quadrati = sum(v * v for v in x) / n
    coseni = sum(math.cos(2.0 * math.pi * v) for v in x) / n
    return -20.0 * math.exp(-0.2 * math.sqrt(quadrati)) - math.exp(coseni) + 20.0 + math.e


@dataclass(frozen=True)
class FunzioneProva:
    funzione: Callable[[Sequence[float]], float]
    limite: float       # ogni coordinata sta fra -limite e +limite
    passo: float        # il passo della griglia
    minimo_x: float     # la coordinata del minimo globale, uguale per tutte


FUNZIONI = {
    "sphere": FunzioneProva(sphere, 5.12, 0.01, 0.0),
    "rastrigin": FunzioneProva(rastrigin, 5.12, 0.01, 0.0),
    "rosenbrock": FunzioneProva(rosenbrock, 2.048, 0.001, 1.0),
    "ackley": FunzioneProva(ackley, 32.768, 0.001, 0.0),
}


def spazio_prova(nome: str, dimensioni: int) -> Spazio:
    """Lo spazio di una funzione di prova: `dimensioni` reali con i limiti e il passo della tabella."""
    f = FUNZIONI[nome]
    return Spazio([Reale(f"x{i}", -f.limite, f.limite, f.passo) for i in range(dimensioni)])


def obiettivo(funzione: Callable[[Sequence[float]], float], nomi: Sequence[str]) -> Callable[[dict], float]:
    """Da funzione da minimizzare su una lista a funzione da massimizzare su un punto."""
    nomi = list(nomi)
    return lambda punto: -funzione([punto[n] for n in nomi])

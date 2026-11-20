"""Cuantización por intervalos de los atributos de ventana (D7)."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from . import config
from .errores import ErrorConfiguracion, ErrorDatos

log = logging.getLogger(__name__)


class Discretizador:
    """Cortes por percentiles ajustados solo con ventanas de entrenamiento con actividad.

    Símbolo 0 = ventana sin actividad. Los demás codifican el nivel de cada atributo:
    1 + sum(nivel_i * L**i), con L = len(cortes) + 1 niveles por atributo.
    """

    def __init__(self, cortes=config.CORTES, atributos=config.ATRIBUTOS):
        self.cortes = tuple(float(c) for c in cortes)
        if not self.cortes or any(not 0 < c < 1 for c in self.cortes) or any(a >= b for a, b in zip(self.cortes, self.cortes[1:])):
            raise ErrorConfiguracion(f"Los cortes deben ser percentiles crecientes en (0, 1): {self.cortes}")
        self.atributos = list(atributos)
        self.niveles = len(self.cortes) + 1
        self.M = 1 + self.niveles ** len(self.atributos)
        self.limites_: dict[str, np.ndarray] | None = None

    def ajustar(self, v_entrenamiento: pd.DataFrame) -> "Discretizador":
        activas = v_entrenamiento[v_entrenamiento["n"] > 0]
        if activas.empty:
            raise ErrorDatos("No hay ventanas de entrenamiento con actividad para ajustar los cortes")
        faltan = [a for a in self.atributos if a not in activas.columns]
        if faltan:
            raise ErrorDatos(f"Faltan atributos en las ventanas: {faltan}")
        self.limites_ = {}
        for a in self.atributos:
            x = activas[a].to_numpy(dtype=float)
            if not np.isfinite(x).all():
                raise ErrorDatos(f"{a} tiene valores no finitos en ventanas con actividad")
            self.limites_[a] = np.quantile(x, self.cortes)
            if len(np.unique(self.limites_[a])) < len(self.cortes):
                # Con muchos empates algún nivel queda vacío: el símbolo pierde resolución, no es un error.
                log.warning("%s: cortes repetidos %s, algún nivel queda vacío", a, np.round(self.limites_[a], 4).tolist())
        return self

    def niveles_de(self, v: pd.DataFrame) -> np.ndarray:
        if self.limites_ is None:
            raise RuntimeError("Discretizador sin ajustar: llama a ajustar() primero")
        cols = [np.searchsorted(self.limites_[a], v[a].to_numpy(dtype=float), side="left") for a in self.atributos]
        return np.stack(cols, axis=1)

    def transformar(self, v: pd.DataFrame) -> np.ndarray:
        niv = self.niveles_de(v)
        base = self.niveles ** np.arange(len(self.atributos))
        sim = 1 + niv @ base
        return np.where(v["n"].to_numpy() > 0, sim, 0).astype(np.int64)

    def describir(self, simbolo: int) -> str:
        if simbolo == 0:
            return "sin actividad"
        nombres = ["bajo", "medio", "alto"] if self.niveles == 3 else [f"n{i}" for i in range(self.niveles)]
        r, partes = simbolo - 1, []
        for a in self.atributos:
            partes.append(f"{a.split('_', 1)[1]}={nombres[r % self.niveles]}")
            r //= self.niveles
        return ", ".join(partes)

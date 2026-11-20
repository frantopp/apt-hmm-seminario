"""Modelos de referencia RF y XGBoost bajo las mismas condiciones que el HMM (D13)."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.utils.class_weight import compute_sample_weight

from . import config
from .errores import ErrorDatos

log = logging.getLogger(__name__)


def caracteristicas(v: pd.DataFrame, niveles: np.ndarray, representacion: str, k: int) -> np.ndarray:
    """Matriz de atributos por ventana, con las k ventanas previas de la misma secuencia.

    - continuo: los cuatro atributos (0 si no hay actividad), log(1+n) e indicador de inactividad.
    - discreto: los niveles de cada atributo que usa el símbolo del HMM (misma información
      que el símbolo, sin expandirlo a 82 columnas) e indicador de inactividad.
    v debe estar ordenado por (secuencia, w).
    """
    inactiva = (v["n"].to_numpy() == 0).astype(np.float32)[:, None]
    if representacion == "continuo":
        base = np.c_[v[config.ATRIBUTOS].fillna(0).to_numpy(np.float32), np.log1p(v["n"].to_numpy(np.float32)), inactiva]
    elif representacion == "discreto":
        base = np.c_[np.where(inactiva > 0, -1, niveles).astype(np.float32), inactiva]
    else:
        raise ValueError(representacion)
    seq = v["secuencia"].to_numpy()
    bloques = [base]
    for lag in range(1, k + 1):
        x = np.zeros_like(base)
        x[lag:] = base[:-lag]
        misma = np.zeros(len(seq), bool)
        misma[lag:] = seq[lag:] == seq[:-lag]
        x[~misma] = 0
        bloques.append(x)
    return np.hstack(bloques)


class Clasificador:
    """Envuelve RF o XGBoost y devuelve probabilidades para los N estados aunque falte alguno."""

    def __init__(self, tipo: str, profundidad, semilla: int = config.SEMILLA, arboles: int | None = None,
                 tasa: float = 0.1, n_jobs: int = -1, smote_fraccion: float = 0.1):
        if tipo not in ("RF", "XGB"):
            raise ValueError(f"Tipo de clasificador desconocido: {tipo}")
        self.tipo, self.profundidad, self.semilla = tipo, profundidad, semilla
        self.arboles = arboles or (200 if tipo == "RF" else 300)
        self.tasa, self.n_jobs, self.smote_fraccion = tasa, n_jobs, smote_fraccion
        self.smote_aplicado: bool | None = None

    def ajustar(self, X: np.ndarray, y: np.ndarray, balance: str) -> "Clasificador":
        if len(X) != len(y) or len(y) == 0:
            raise ErrorDatos("Entrenamiento vacío o con X e y de distinto largo")
        w = None
        if balance == "pesos":
            w = compute_sample_weight("balanced", y)
        elif balance == "smote":
            X, y, self.smote_aplicado = smote(X, y, self.semilla, self.smote_fraccion)
        elif balance != "original":
            raise ValueError(f"Tratamiento del desbalance desconocido: {balance}")
        self.clases_ = np.unique(y)
        if len(self.clases_) < 2:
            raise ErrorDatos(f"El entrenamiento tiene una sola clase ({config.ETAPAS[int(self.clases_[0])]})")
        y_idx = np.searchsorted(self.clases_, y)
        if self.tipo == "RF":
            self.m = RandomForestClassifier(n_estimators=self.arboles, max_depth=self.profundidad,
                                            n_jobs=self.n_jobs, random_state=self.semilla)
        else:
            from xgboost import XGBClassifier
            self.m = XGBClassifier(n_estimators=self.arboles, max_depth=self.profundidad, learning_rate=self.tasa,
                                   tree_method="hist", n_jobs=self.n_jobs, random_state=self.semilla,
                                   objective="multi:softprob" if len(self.clases_) > 2 else "binary:logistic")
        self.m.fit(X, y_idx, sample_weight=w)
        return self

    def proba(self, X: np.ndarray) -> np.ndarray:
        p = self.m.predict_proba(X)
        out = np.zeros((len(X), config.N_ESTADOS))
        out[:, self.clases_] = p
        return out


def smote(X: np.ndarray, y: np.ndarray, semilla: int, fraccion: float = 0.1):
    """SMOTE solo en entrenamiento: cada etapa de ataque sube hasta `fraccion` de la clase
    mayoritaria (o se deja igual si ya la supera). k_neighbors se ajusta a la clase más
    pequeña, y las clases con menos de 2 ejemplos no se sobremuestrean.

    Devuelve (X, y, aplicado). Si SMOTE falla se sigue sin sobremuestreo con aplicado = False,
    lo que queda registrado en metricas.json en vez de detener el experimento."""
    from imblearn.over_sampling import SMOTE
    clases, cuentas = np.unique(y, return_counts=True)
    cuenta = dict(zip(clases.tolist(), cuentas.tolist()))
    mayor = cuentas.max()
    objetivo = {int(c): int(max(n, fraccion * mayor)) for c, n in cuenta.items() if 2 <= n < mayor}
    objetivo = {c: n for c, n in objetivo.items() if n > cuenta[c]}
    if not objetivo:
        return X, y, False
    k = int(min(5, min(cuenta[c] for c in objetivo) - 1))
    try:
        Xr, yr = SMOTE(sampling_strategy=objetivo, k_neighbors=k, random_state=semilla).fit_resample(X, y)
    except ValueError as x:
        log.warning("SMOTE falló (%s): se entrena sin sobremuestreo", x)
        return X, y, False
    return Xr, yr, True

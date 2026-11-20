"""Agregación de flujos en ventanas Δt por host interno (decisiones D1, D4, D5 y D6)."""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from . import config
from .errores import ErrorConfiguracion, ErrorDatos

ORDEN = {e: i for i, e in enumerate(config.ETAPAS)}


def _mascara(serie: pd.Series, pred: Callable[[str], bool]) -> np.ndarray:
    """Aplica pred sobre las categorías (rápido) y devuelve la máscara por fila."""
    cat = serie.astype("category")
    tabla = np.array([pred(str(c)) for c in cat.cat.categories] + [False])
    return tabla[cat.cat.codes.to_numpy()]


def construir_ventanas(
    flujos: pd.DataFrame,
    es_interno: Callable[[str], bool],
    dt: int = config.DT,
    min_flujos: int = 0,
    encubrimiento: str = "asignar",
) -> pd.DataFrame:
    """Devuelve una fila por (host interno, ventana con captura).

    - Cada flujo cuenta para sus extremos internos (ambos si los dos lo son).
    - Las ventanas en que hubo captura pero el host no tuvo flujos quedan con n = 0
      (símbolo "sin actividad").
    - etiqueta = etapa más avanzada entre los flujos de la ventana (0 = benigno).
    """
    if dt <= 0:
        raise ErrorConfiguracion(f"dt debe ser positivo: {dt}")
    faltan = [c for c in ("ts", "src", "dst", "dport", "dur", "bytes_fwd", "bytes_bwd", "pkts_bwd", "rst", "etapa", "grupo")
              if c not in flujos.columns]
    if faltan:
        raise ErrorDatos(f"Faltan columnas en los flujos: {faltan}")
    f = flujos.copy()
    etapa = f["etapa"].astype(str)
    if encubrimiento == "asignar":
        etapa = etapa.replace("encubrimiento", "exfiltracion")
    elif encubrimiento == "excluir":
        f, etapa = f[etapa != "encubrimiento"], etapa[etapa != "encubrimiento"]
    else:
        raise ErrorConfiguracion(f"encubrimiento debe ser 'asignar' o 'excluir': {encubrimiento!r}")
    estado = etapa.map(ORDEN)
    if estado.isna().any():
        raise ErrorDatos(f"Etapas sin estado del modelo: {sorted(etapa[estado.isna()].unique())[:10]}")
    if f["ts"].isna().any():
        raise ErrorDatos("Hay flujos sin marca de tiempo")
    f = f.assign(
        w=(f["ts"] // dt).astype("int64"),
        estado=estado.astype("int8").to_numpy(),
        fallido=((f["pkts_bwd"] == 0) | (f["rst"] > 0)).astype("float32"),
    )
    malicioso = f["estado"] > 0
    grupo = f["grupo"].astype(str)
    f["apt"] = malicioso & (grupo == "APT")
    f["aa"] = malicioso & (grupo == "AA")
    cobertura = np.unique(f["w"].to_numpy())

    comunes = ["w", "estado", "dur", "dport", "fallido", "apt", "aa"]
    m_src = _mascara(f["src"], es_interno)
    m_dst = _mascara(f["dst"], es_interno)
    lado_src = f.loc[m_src, comunes].assign(host=f.loc[m_src, "src"].astype(str), bytes_out=f.loc[m_src, "bytes_fwd"])
    lado_dst = f.loc[m_dst, comunes].assign(host=f.loc[m_dst, "dst"].astype(str), bytes_out=f.loc[m_dst, "bytes_bwd"])
    lados = pd.concat([lado_src, lado_dst], ignore_index=True)

    conteo = lados["host"].value_counts()
    hosts = sorted(conteo[conteo >= min_flujos].index)
    if not hosts:
        raise ErrorDatos(f"Ningún host interno tiene {min_flujos} flujos o más. Revisa 'internos', 'externos' y 'min_flujos' "
                         f"({len(conteo)} hosts internos encontrados).")
    lados = lados[lados["host"].isin(hosts)]

    g = lados.groupby(["host", "w"], sort=True)
    v = pd.DataFrame({
        "n": g.size(),
        "A1_bytes_salida": np.log1p(g["bytes_out"].sum()),
        "A2_duracion": g["dur"].median(),
        "A3_puertos": g["dport"].nunique(),
        "A4_fallidos": g["fallido"].mean(),
        "etiqueta": g["estado"].max(),
        "apt": g["apt"].any(),
        "aa": g["aa"].any(),
    })
    malla = pd.MultiIndex.from_product([hosts, cobertura], names=["host", "w"])
    v = v.reindex(malla)
    v["n"] = v["n"].fillna(0).astype("int32")
    v["etiqueta"] = v["etiqueta"].fillna(0).astype("int8")
    for c in ("apt", "aa"):
        v[c] = v[c].astype("boolean").fillna(False).astype(bool)
    v = v.reset_index()
    v["t"] = v["w"] * dt
    v.attrs["dt"] = dt
    return v

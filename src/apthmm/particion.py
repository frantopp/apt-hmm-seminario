"""Partición entrenamiento / validación / prueba y corte en secuencias (D3)."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from . import config
from .errores import ErrorConfiguracion, ErrorDatos

log = logging.getLogger(__name__)

PARTICIONES = ("entrenamiento", "validacion", "prueba")


def validar_spec(spec: dict) -> None:
    """Revisa la especificación de partición antes de usarla."""
    if not isinstance(spec, dict) or "tipo" not in spec:
        raise ErrorConfiguracion(f"particion debe tener 'tipo' (fechas o intradia): {spec!r}")
    if spec["tipo"] == "fechas":
        rangos = []
        for p in PARTICIONES:
            if p not in spec:
                raise ErrorConfiguracion(f"particion por fechas sin '{p}'")
            try:
                ini, fin = (pd.Timestamp(x) for x in spec[p])
            except (TypeError, ValueError):
                raise ErrorConfiguracion(f"particion.{p} debe ser [inicio, fin] en formato AAAA-MM-DD: {spec[p]!r}") from None
            if ini > fin:
                raise ErrorConfiguracion(f"particion.{p}: el inicio es posterior al fin ({spec[p]})")
            rangos.append((ini, fin, p))
        rangos.sort()
        for (_, f1, p1), (i2, _, p2) in zip(rangos, rangos[1:]):
            if i2 <= f1:
                raise ErrorConfiguracion(f"particion: {p1} y {p2} se solapan")
    elif spec["tipo"] == "intradia":
        fr = spec.get("fracciones")
        if not isinstance(fr, (list, tuple)) or len(fr) != 3 or any(not isinstance(x, (int, float)) or x <= 0 for x in fr) \
                or not np.isclose(sum(fr), 1.0):
            raise ErrorConfiguracion(f"particion.fracciones deben ser tres valores positivos que sumen 1: {fr!r}")
    else:
        raise ErrorConfiguracion(f"particion.tipo desconocido: {spec['tipo']!r} (fechas o intradia)")


def asignar_particion(v: pd.DataFrame, spec: dict) -> pd.Series:
    validar_spec(spec)
    fecha = pd.to_datetime(v["t"], unit="s").dt.strftime("%Y-%m-%d")
    out = pd.Series(pd.NA, index=v.index, dtype="object")
    if spec["tipo"] == "fechas":
        for p in PARTICIONES:
            ini, fin = (pd.Timestamp(x).strftime("%Y-%m-%d") for x in spec[p])
            out[(fecha >= ini) & (fecha <= fin)] = p
        return out
    f_ent, f_val, _ = spec["fracciones"]
    for dia in fecha.unique():
        m = fecha == dia
        ws = np.sort(v.loc[m, "w"].unique())
        rango = np.arange(len(ws)) / len(ws)
        etiqueta = np.where(rango < f_ent, "entrenamiento",
                            np.where(rango < f_ent + f_val, "validacion", "prueba")).astype(object)
        # Una ventana de separación al inicio de validación y de prueba.
        cambio = np.r_[False, etiqueta[1:] != etiqueta[:-1]]
        etiqueta[cambio] = "descartada"
        out[m] = v.loc[m, "w"].map(dict(zip(ws, etiqueta)))
    return out


def cortar_secuencias(v: pd.DataFrame, max_hueco: int = config.MAX_HUECO) -> pd.Series:
    """Id de secuencia: cambia con el host, la partición o un hueco de captura."""
    v = v.sort_values(["host", "w"])
    nueva = (
        (v["host"] != v["host"].shift())
        | (v["particion"] != v["particion"].shift())
        | (v["w"].diff() > max_hueco)
    )
    return nueva.cumsum().rename("secuencia")


def preparar(v: pd.DataFrame, spec: dict, max_hueco: int = config.MAX_HUECO) -> pd.DataFrame:
    v = v.copy()
    v["particion"] = asignar_particion(v, spec)
    fuera = int(v["particion"].isna().sum() + (v["particion"] == "descartada").sum())
    if fuera:
        log.info("%d ventanas quedan fuera de las particiones (fechas no cubiertas o separación)", fuera)
    v = v[v["particion"].isin(PARTICIONES)].sort_values(["host", "w"]).reset_index(drop=True)
    vacias = [p for p in PARTICIONES if not (v["particion"] == p).any()]
    if vacias:
        raise ErrorDatos(f"Particiones sin ventanas: {vacias}. Revisa 'particion' frente al rango de fechas de los datos.")
    v["secuencia"] = cortar_secuencias(v, max_hueco).to_numpy()
    return v


def secuencias(v: pd.DataFrame, columna: str) -> list[np.ndarray]:
    """Lista de arreglos de `columna`, una por secuencia, en orden temporal."""
    if v.empty:
        return []
    v = v.sort_values(["secuencia", "w"])
    cortes = np.flatnonzero(np.diff(v["secuencia"].to_numpy())) + 1
    return np.split(v[columna].to_numpy(), cortes)

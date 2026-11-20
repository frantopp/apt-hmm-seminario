"""Métricas por etapa y de detección temprana (Sección 8.6 del informe, D2 y D12)."""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

from . import config

log = logging.getLogger(__name__)

ATAQUE = list(range(1, config.N_ESTADOS))


def por_etapa(y: np.ndarray, yhat: np.ndarray) -> dict:
    etiquetas = list(range(config.N_ESTADOS))
    p, r, f, s = precision_recall_fscore_support(y, yhat, labels=etiquetas, zero_division=0)
    presentes = [k for k in ATAQUE if s[k] > 0]
    return {
        "por_etapa": {config.ETAPAS[k]: {"precision": float(p[k]), "recall": float(r[k]), "f1": float(f[k]), "soporte": int(s[k])}
                      for k in etiquetas},
        # Macro sobre las etapas de ataque presentes en la partición evaluada.
        "macro_f1_ataque": float(np.mean(f[presentes])) if presentes else float("nan"),
        "macro_recall_ataque": float(np.mean(r[presentes])) if presentes else float("nan"),
        "macro_precision_ataque": float(np.mean(p[presentes])) if presentes else float("nan"),
        "matriz_confusion": confusion_matrix(y, yhat, labels=etiquetas).tolist(),
    }


def calibrar_tau(p_benignas: np.ndarray, fpr: float) -> float:
    """Umbral tal que a lo más una fracción `fpr` de ventanas benignas alerta (p >= tau)."""
    if not 0 < fpr < 1:
        raise ValueError(f"fpr debe estar en (0, 1): {fpr}")
    p_benignas = np.asarray(p_benignas, dtype=float)
    p_benignas = p_benignas[np.isfinite(p_benignas)]
    if len(p_benignas) == 0:
        log.warning("No hay ventanas benignas para calibrar tau: se usa 0,5")
        return 0.5
    q = np.quantile(p_benignas, 1 - fpr, method="higher")
    return float(np.nextafter(q, np.inf))


def episodios(df: pd.DataFrame, dt: int, hueco: float = config.HUECO_EPISODIO) -> pd.DataFrame:
    """Tramos de ventanas maliciosas de un host separados por más de `hueco` segundos."""
    filas = []
    for host, g in df[df["etiqueta"] > 0].sort_values("t").groupby("host", sort=False):
        t = g["t"].to_numpy()
        corte = np.r_[0, np.flatnonzero(np.diff(t) > hueco) + 1, len(t)]
        for a, b in zip(corte[:-1], corte[1:]):
            tramo = g.iloc[a:b]
            exf = tramo.loc[tramo["etiqueta"] == config.EXFILTRACION, "t"]
            filas.append({
                "host": host, "t0": t[a], "tfin": t[b - 1] + dt,
                "texf": exf.min() if len(exf) else np.nan,
                "etapas": sorted(set(tramo["etiqueta"].tolist())),
                "apt": bool(tramo["apt"].any()), "aa": bool(tramo["aa"].any()),
                "ventanas": int(b - a),
            })
    return pd.DataFrame(filas)


def deteccion_temprana(df: pd.DataFrame, tau: float, dt: int, eps: pd.DataFrame | None = None,
                       hueco: float = config.HUECO_EPISODIO) -> dict:
    """df: una fila por ventana evaluada con host, t, etiqueta, p_ataque, pred, apt, aa."""
    faltan = [c for c in ("host", "t", "etiqueta", "p_ataque", "pred", "apt", "aa") if c not in df.columns]
    if faltan:
        raise ValueError(f"Faltan columnas para evaluar la detección: {faltan}")
    eps = episodios(df, dt, hueco) if eps is None else eps
    alerta = df["p_ataque"].to_numpy() >= tau
    benigna = df["etiqueta"].to_numpy() == 0
    fpr = float(alerta[benigna].mean()) if benigna.any() else float("nan")
    por_host = {h: g.sort_values("t") for h, g in df.assign(alerta=alerta).groupby("host", sort=False)}
    filas = []
    for e in eps.itertuples():
        g = por_host[e.host]
        tramo = g[(g["t"] >= e.t0) & (g["t"] < e.tfin)]
        al = tramo[tramo["alerta"]]
        fila = {"host": e.host, "t0": e.t0, "apt": e.apt, "aa": e.aa, "detectado": len(al) > 0}
        if len(al):
            td = al["t"].iloc[0]
            fila.update(ttd_min=(td - e.t0) / 60, precocidad=(td - e.t0) / (e.tfin - e.t0),
                        etapa_primera=config.ETAPAS[int(al["etiqueta"].iloc[0])])
        if not np.isnan(e.texf):
            fila["pre_exf"] = bool(len(al) and al["t"].iloc[0] < e.texf)
        for k in e.etapas:
            te = tramo.loc[tramo["etiqueta"] == k, "t"].min()
            ok = tramo[(tramo["t"] >= te) & (tramo["pred"] == k)]
            fila[f"retardo_{config.ETAPAS[k]}_min"] = (ok["t"].iloc[0] - te) / 60 if len(ok) else np.nan
        filas.append(fila)
    det = pd.DataFrame(filas)
    out = {"tau": tau, "fpr": fpr, "n_episodios": int(len(det)), "episodios": det.to_dict("records")}
    if len(det):
        d = det[det["detectado"]]
        out.update({
            "tasa_deteccion": float(det["detectado"].mean()),
            "ttd_mediana_min": float(d["ttd_min"].median()) if len(d) else np.nan,
            "ttd_p25_min": float(d["ttd_min"].quantile(0.25)) if len(d) else np.nan,
            "ttd_p75_min": float(d["ttd_min"].quantile(0.75)) if len(d) else np.nan,
            "precocidad_mediana": float(d["precocidad"].median()) if len(d) else np.nan,
            "etapa_primera_deteccion": d["etapa_primera"].value_counts().to_dict() if len(d) else {},
            "tasa_pre_exf": float(det["pre_exf"].dropna().mean()) if "pre_exf" in det and det["pre_exf"].notna().any() else np.nan,
            "retardo_mediano_min": {c[8:-4]: float(det[c].median()) for c in det.columns if c.startswith("retardo_")},
        })
    return out


def curva_ttd_fpr(df: pd.DataFrame, dt: int, fprs=None, hueco: float = config.HUECO_EPISODIO) -> pd.DataFrame:
    """Barre tau según cuantiles de las ventanas benignas evaluadas."""
    fprs = np.r_[0.0, np.logspace(-4, -0.3, 25)] if fprs is None else fprs
    eps = episodios(df, dt, hueco)
    pb = df.loc[df["etiqueta"] == 0, "p_ataque"].to_numpy()
    filas = []
    for f in fprs:
        tau = calibrar_tau(pb, f) if f > 0 else float(np.nextafter(pb.max(), np.inf)) if len(pb) else 1.0
        r = deteccion_temprana(df, tau, dt, eps)
        filas.append({k: r.get(k) for k in ("tau", "fpr", "tasa_deteccion", "ttd_mediana_min", "precocidad_mediana", "tasa_pre_exf")})
    return pd.DataFrame(filas)

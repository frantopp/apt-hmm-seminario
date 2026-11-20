import numpy as np
import pandas as pd

from apthmm import metricas


def _serie():
    # Host a: benigno, reconocimiento (2), foothold, exfiltración, benigno. dt = 300.
    et = [0, 0, 1, 1, 2, 4, 0, 0]
    p = [0.1, 0.6, 0.2, 0.7, 0.9, 0.9, 0.1, 0.1]
    pred = [0, 0, 0, 1, 2, 2, 0, 0]
    return pd.DataFrame({"host": "a", "t": np.arange(8) * 300, "etiqueta": et, "p_ataque": p,
                         "pred": pred, "apt": [e > 0 for e in et], "aa": False})


def test_episodios():
    e = metricas.episodios(_serie(), 300)
    assert len(e) == 1
    assert e.loc[0, "t0"] == 600 and e.loc[0, "tfin"] == 1800 and e.loc[0, "texf"] == 1500


def test_deteccion_temprana():
    r = metricas.deteccion_temprana(_serie(), tau=0.5, dt=300)
    ep = r["episodios"][0]
    assert ep["detectado"] and ep["ttd_min"] == 5           # primera alerta en t=900
    assert np.isclose(ep["precocidad"], 300 / 1200)
    assert ep["etapa_primera"] == "reconocimiento" and ep["pre_exf"]
    assert ep["retardo_reconocimiento_min"] == 5 and ep["retardo_foothold_min"] == 0
    assert np.isnan(ep["retardo_exfiltracion_min"])
    assert np.isclose(r["fpr"], 1 / 4)                       # una alerta en 4 ventanas benignas


def test_calibrar_tau_respeta_fpr():
    p = np.linspace(0, 1, 1001)
    tau = metricas.calibrar_tau(p, 0.01)
    assert (p >= tau).mean() <= 0.01


def test_curva_monotona_en_fpr():
    c = metricas.curva_ttd_fpr(_serie(), 300, fprs=[0.0, 0.25, 0.5])
    assert list(c["fpr"]) == sorted(c["fpr"])

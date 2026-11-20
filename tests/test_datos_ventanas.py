import numpy as np
import pandas as pd

from apthmm import datos, particion, ventanas
from apthmm.discretizacion import Discretizador


def test_reparar_fila_con_comas_en_texto():
    enc = ["a", "b", "application_name", "user_agent", "Activity", "Stage", "DefenderResponse", "Signature"]
    fila = ["1", "2", "http", "Mozilla (KHTML", " like Gecko)", "Normal", "Benign", "Benign", "None"]
    r = datos.reparar_fila(fila, len(enc), enc.index("application_name"))
    assert r[:2] == ["1", "2"] and r[-4:] == ["Normal", "Benign", "Benign", "None"] and len(r) == len(enc)
    assert datos.reparar_fila(fila[:5], len(enc), 2) is None


def _flujos():
    return pd.DataFrame({
        "ts": [0, 10, 20, 310, 320, 900],
        "src": ["ext", "ext", "h1", "h1", "h1", "h2"],
        "dst": ["h1", "h1", "h2", "ext", "ext", "ext"],
        "dport": [22, 80, 445, 443, 443, 53],
        "dur": [0.1, 0.2, 1.0, 5.0, 7.0, 0.5],
        "bytes_fwd": [10, 10, 100, 1000, 3000, 5],
        "bytes_bwd": [0, 50, 20, 10, 10, 5],
        "pkts_bwd": [0, 1, 1, 1, 1, 1],
        "rst": [0, 0, 0, 0, 1, 0],
        "etapa": ["reconocimiento", "benigno", "lateral", "exfiltracion", "encubrimiento", "benigno"],
        "grupo": ["APT", "", "APT", "APT", "APT", ""],
    })


def test_ventanas_por_host_interno():
    v = ventanas.construir_ventanas(_flujos(), lambda ip: ip.startswith("h"), dt=300)
    v = v.set_index(["host", "w"])
    # Ventana 0 de h1: dos flujos entrantes + uno saliente lateral -> etapa más avanzada = lateral (3)
    assert v.loc[("h1", 0), "n"] == 3
    assert v.loc[("h1", 0), "etiqueta"] == 3
    assert v.loc[("h1", 0), "A3_puertos"] == 3
    assert np.isclose(v.loc[("h1", 0), "A1_bytes_salida"], np.log1p(0 + 50 + 100))
    assert np.isclose(v.loc[("h1", 0), "A4_fallidos"], 1 / 3)
    # El flujo lateral h1->h2 también cuenta para h2
    assert v.loc[("h2", 0), "etiqueta"] == 3
    # Encubrimiento asignado a exfiltración
    assert v.loc[("h1", 1), "etiqueta"] == 4
    # h1 no tiene flujos en la ventana 3 pero hubo captura: n = 0, benigno
    assert v.loc[("h1", 3), "n"] == 0 and v.loc[("h1", 3), "etiqueta"] == 0
    assert "ext" not in v.index.get_level_values(0)


def test_excluir_encubrimiento():
    v = ventanas.construir_ventanas(_flujos(), lambda ip: ip.startswith("h"), dt=300, encubrimiento="excluir")
    assert v.set_index(["host", "w"]).loc[("h1", 1), "n"] == 1


def test_secuencias_se_cortan_por_host_particion_y_hueco():
    v = pd.DataFrame({"host": ["a"] * 5 + ["b"] * 2, "w": [0, 1, 2, 30, 31, 0, 1],
                      "particion": ["entrenamiento"] * 2 + ["validacion"] + ["validacion"] * 2 + ["prueba"] * 2})
    s = particion.cortar_secuencias(v, max_hueco=12).to_numpy()
    assert list(s) == [1, 1, 2, 3, 3, 4, 4]


def test_particion_intradia_separa_tramos():
    v = pd.DataFrame({"host": "a", "w": np.arange(10), "t": np.arange(10) * 300})
    p = particion.asignar_particion(v, {"tipo": "intradia", "fracciones": (0.6, 0.2, 0.2)}).tolist()
    assert p == ["entrenamiento"] * 6 + ["descartada", "validacion", "descartada", "prueba"]


def test_discretizador_usa_solo_entrenamiento_y_simbolo_inactivo():
    ent = pd.DataFrame({"n": [1] * 100, **{a: np.arange(100.0) for a in ["A1_bytes_salida", "A2_duracion", "A3_puertos", "A4_fallidos"]}})
    d = Discretizador((0.5, 0.95)).ajustar(ent)
    assert d.M == 82
    otro = pd.DataFrame({"n": [0, 1, 1], **{a: [np.nan, 0.0, 1e9] for a in ["A1_bytes_salida", "A2_duracion", "A3_puertos", "A4_fallidos"]}})
    s = d.transformar(otro)
    assert s[0] == 0 and s[1] == 1 and s[2] == 81
    assert "bytes_salida=alto" in d.describir(81)

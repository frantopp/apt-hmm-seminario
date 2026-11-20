"""Configuración, captura de errores y casos borde del motor."""
import json

import numpy as np
import pandas as pd
import pytest

from apthmm import __main__ as cli
from apthmm import baseline, config, datos, experimentos as ex, hmm, particion
from apthmm.config import Parametros
from apthmm.errores import ErrorConfiguracion, ErrorDatos


@pytest.fixture
def aislado(tmp_path, monkeypatch):
    """Resultados y caché en una carpeta temporal."""
    monkeypatch.setattr(config, "RESULTADOS", tmp_path / "results")
    monkeypatch.setattr(config, "CACHE", tmp_path / "cache")
    return tmp_path


# ------------------------------------------------------------------ parámetros
def test_carpeta_por_defecto_y_con_cambios():
    base = Parametros(dataset="unraveled")
    assert base.carpeta().name == "dt300_asignar"
    assert base.fpr == 0.001 and base.min_flujos == 1000
    # n_jobs no cambia los resultados: misma carpeta
    assert base.con(n_jobs=2).carpeta() == base.carpeta()
    otra = base.con(cortes=(0.333, 0.667))
    assert otra.carpeta().name.startswith("dt300_asignar_") and otra.carpeta() != base.carpeta()
    assert base.con(etiqueta="mia").carpeta().name == "mia"


@pytest.mark.parametrize("cambio", [
    {"cortes": (0.9, 0.5)}, {"cortes": (0.5, 1.0)}, {"fpr": 1.5}, {"dt": 0}, {"encubrimiento": "otro"},
    {"ks": (0,)}, {"xgb_profundidades": (0,)}, {"etiqueta": "../fuera"},
    {"particion": {"tipo": "intradia", "fracciones": [0.5, 0.5, 0.5]}},
    {"particion": {"tipo": "fechas", "entrenamiento": ["2021-01-01", "2021-01-10"],
                   "validacion": ["2021-01-05", "2021-01-12"], "prueba": ["2021-01-13", "2021-01-14"]}},
])
def test_parametros_invalidos(cambio):
    with pytest.raises(ErrorConfiguracion):
        Parametros(dataset="unraveled", **cambio)


def test_dataset_desconocido_y_tipo_invalido():
    with pytest.raises(ErrorConfiguracion):
        Parametros(dataset="otro")
    with pytest.raises(ErrorConfiguracion):
        Parametros(dataset="dapt", dt="cinco")


def test_toml_ida_y_vuelta_y_prioridad_de_la_linea_de_comandos(tmp_path):
    p = Parametros(dataset="dapt", dt=900, cortes=(0.333, 0.667), rf_profundidades=(None, 10), alfa_A=0.5)
    archivo = tmp_path / "exp.toml"
    archivo.write_text(p.a_toml(), encoding="utf-8")
    leido = Parametros.desde(archivo=archivo)
    assert leido.a_dict() == p.a_dict()
    assert Parametros.desde(archivo=archivo, dt=60).dt == 60


def test_toml_rechaza_claves_desconocidas_y_mal_formado(tmp_path):
    a = tmp_path / "a.toml"
    a.write_text('dataset = "dapt"\n[hmm]\nnada = 1\n', encoding="utf-8")
    with pytest.raises(ErrorConfiguracion, match="nada"):
        Parametros.desde(archivo=a)
    a.write_text('dataset = "dapt"\ndt = [\n', encoding="utf-8")
    with pytest.raises(ErrorConfiguracion, match="TOML"):
        Parametros.desde(archivo=a)
    with pytest.raises(ErrorConfiguracion):
        Parametros.desde(archivo=tmp_path / "no_existe.toml")


def test_prefijos_internos_equivalen_a_la_regla_de_unraveled():
    es = Parametros(dataset="unraveled").es_interno
    assert es("10.1.2.3") and es("192.168.0.9")
    assert not es("10.8.10.4") and not es("8.8.8.8")


def test_preparar_salida_no_mezcla_parametros(aislado):
    salida = ex.preparar_salida(Parametros(dataset="dapt", etiqueta="x"))
    # Sin resultados todavía, cambiar de parámetros no bloquea.
    ex.preparar_salida(Parametros(dataset="dapt", etiqueta="x", dt=900))
    ex.preparar_salida(Parametros(dataset="dapt", etiqueta="x"))
    (salida / "H1-original").mkdir()
    (salida / "H1-original" / "metricas.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ErrorConfiguracion, match="otros parámetros"):
        ex.preparar_salida(Parametros(dataset="dapt", etiqueta="x", dt=60))
    ex.preparar_salida(Parametros(dataset="dapt", etiqueta="x", dt=60), forzar=True)
    # n_jobs no cuenta como parámetro distinto
    ex.preparar_salida(Parametros(dataset="dapt", etiqueta="x", dt=60, n_jobs=1))


# ------------------------------------------------------------------ datos
def test_ruta_inexistente_da_error_claro(aislado):
    with pytest.raises(ErrorDatos, match="No existe la carpeta"):
        datos.cargar("dapt", aislado / "no_esta")


def test_particion_vacia_da_error():
    v = pd.DataFrame({"host": "a", "w": np.arange(5), "t": pd.Timestamp("2021-01-01").timestamp() + np.arange(5) * 300})
    spec = {"tipo": "fechas", "entrenamiento": ["2021-01-01", "2021-01-01"],
            "validacion": ["2021-01-02", "2021-01-02"], "prueba": ["2021-01-03", "2021-01-03"]}
    with pytest.raises(ErrorDatos, match="validacion"):
        particion.preparar(v, spec)


# ------------------------------------------------------------------ modelo
def test_filtrado_con_simbolo_imposible_no_produce_nan():
    m = hmm.HMM(np.array([[0.9, 0.1], [0.2, 0.8]]), np.array([[0.5, 0.5, 0.0], [0.3, 0.7, 0.0]]), np.array([0.5, 0.5]))
    alfa, ll = m.filtrar(np.array([0, 2, 1]))
    assert np.isfinite(alfa).all() and np.allclose(alfa.sum(1), 1) and np.isfinite(ll)


def test_secuencia_vacia():
    m = hmm.HMM(np.eye(2), np.full((2, 3), 1 / 3), np.array([0.5, 0.5]))
    alfa, ll = m.filtrar(np.array([], dtype=int))
    assert alfa.shape == (0, 2) and ll == 0.0
    assert len(m.viterbi(np.array([], dtype=int))) == 0


def test_supervisado_rechaza_simbolos_fuera_de_rango():
    with pytest.raises(ValueError):
        hmm.HMM.supervisado([np.array([0, 5])], [np.array([0, 1])], N=2, M=3)


def test_submuestrear_conserva_todo_el_ataque():
    et = np.zeros(1000, int)
    et[500:510] = 2
    d = pd.DataFrame({"secuencia": 1, "w": np.arange(1000), "etiqueta": et})
    out = ex.submuestrear(d, np.random.default_rng(0), razon=2.0, bloque=72)
    assert (out["etiqueta"] > 0).sum() == 10
    assert len(out) < len(d)
    # Lo que rodea al ataque (a menos de un bloque) se conserva entero.
    assert set(range(500 - 72, 509 + 72 + 1)) <= set(out["w"])


def test_smote_informa_si_no_se_aplica():
    X, y = np.random.default_rng(0).normal(size=(20, 3)), np.array([0] * 19 + [1])
    _, _, aplicado = baseline.smote(X, y, 0)
    assert aplicado is False


# ------------------------------------------------------------------ resultados
def test_json_limpio_sin_nan():
    d = ex.limpiar({"a": np.nan, "b": np.float64(np.inf), "c": np.bool_(True), "d": [np.int64(3)], 1.5: pd.NA})
    assert d == {"a": None, "b": None, "c": True, "d": [3], "1.5": None}
    json.dumps(d, allow_nan=False)


class _Ctx:
    def __init__(self, salida):
        self.salida = salida


def test_lote_sigue_tras_un_fallo_y_continuar_salta_lo_hecho(tmp_path, monkeypatch):
    llamadas = []

    def falso(ctx, c):
        nombre = ex.nombre_config(c)
        llamadas.append(nombre)
        if nombre == "H1-umbral":
            raise RuntimeError("falla de prueba")
        (ctx.salida / nombre).mkdir(parents=True, exist_ok=True)
        (ctx.salida / nombre / "metricas.json").write_text("{}", encoding="utf-8")
        return {"por_etapa": {"macro_f1_ataque": 0.5}, "deteccion": {"fpr": 0.01}, "segundos": 0}

    monkeypatch.setattr(ex, "ejecutar", falso)
    ctx = _Ctx(tmp_path)
    configs = [("hmm", "H1", "original"), ("hmm", "H1", "umbral"), ("hmm", "H1", "remuestreo")]
    hechas, fallidas = ex.ejecutar_lote(ctx, configs)
    assert hechas == ["H1-original", "H1-remuestreo"] and list(fallidas) == ["H1-umbral"]
    assert "falla de prueba" in json.loads((tmp_path / "errores.json").read_text(encoding="utf-8"))["H1-umbral"]
    llamadas.clear()
    ex.ejecutar_lote(ctx, configs, continuar=True)
    assert llamadas == ["H1-umbral"]


def test_resumen_omite_archivos_corruptos(tmp_path):
    (tmp_path / "X").mkdir()
    (tmp_path / "X" / "metricas.json").write_text("{roto", encoding="utf-8")
    t = ex.resumen(tmp_path)
    assert t.empty and "macro_f1" in t.columns


# ------------------------------------------------------------------ línea de comandos
def test_patrones_de_configuracion():
    assert len(cli.elegir_configuraciones(["H"], ["H1-*"])) == 3
    assert len(cli.elegir_configuraciones(["H", "B"], None)) == 31
    with pytest.raises(ErrorConfiguracion):
        cli.elegir_configuraciones(["H"], ["Z9"])


def test_codigos_de_salida(aislado, capsys):
    assert cli.main(["resumen", "--dataset", "dapt", "--etiqueta", "no_existe"]) == 2
    assert cli.main(["ejecutar", "--dataset", "dapt", "--cortes", "0.9", "0.1"]) == 2
    assert cli.main(["listar"]) == 0
    assert "H1-original" in capsys.readouterr().out

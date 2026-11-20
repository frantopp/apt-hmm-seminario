"""Orquestación de los experimentos de la Tabla 8.4 del informe (H0, H1, H2, B1, B2)."""
from __future__ import annotations

import json
import logging
import math
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import baseline, config, datos, hmm, metricas, particion, ventanas
from .config import Parametros
from .discretizacion import Discretizador
from .errores import ErrorConfiguracion, ErrorDatos

log = logging.getLogger(__name__)

DESBALANCE_HMM = ("original", "umbral", "remuestreo")
BALANCE_BASE = ("original", "pesos", "smote")
VERSION_VENTANAS = 1


# ------------------------------------------------------------------ datos
def ventanas_dataset(par: Parametros, rehacer: bool = False) -> pd.DataFrame:
    """Ventanas con partición y secuencia. Caché por huella de los parámetros que las definen."""
    huella = par.huella(Parametros._VENTANAS)
    destino = config.CACHE / f"{par.dataset}_ventanas_dt{par.dt}_{par.encubrimiento}_{huella}_v{VERSION_VENTANAS}.parquet"
    flujos_cache = config.CACHE / f"{par.dataset}_flujos.parquet"
    if not rehacer and destino.exists() and (not flujos_cache.exists() or destino.stat().st_mtime >= flujos_cache.stat().st_mtime):
        try:
            return pd.read_parquet(destino)
        except (OSError, ValueError) as x:
            log.warning("Caché de ventanas ilegible (%s): se rehace", x)
    f = datos.cargar(par.dataset, par.ruta, usar_cache=not rehacer)
    log.info("Construyendo ventanas de %d s para %s (%d flujos)", par.dt, par.dataset, len(f))
    v = ventanas.construir_ventanas(f, par.es_interno, par.dt, par.min_flujos, par.encubrimiento)
    v = particion.preparar(v, par.particion, par.max_hueco)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp")
    v.to_parquet(tmp, index=False)
    tmp.replace(destino)
    return v


@dataclass
class Contexto:
    par: Parametros
    v: pd.DataFrame                      # ventanas con particion, secuencia y símbolo "o"
    disc: Discretizador
    salida: Path
    cache: dict = field(default_factory=dict)

    @property
    def dataset(self) -> str:
        return self.par.dataset

    @property
    def dt(self) -> int:
        return self.par.dt

    @property
    def fpr(self) -> float:
        return self.par.fpr

    def parte(self, nombre: str) -> pd.DataFrame:
        return self.v[self.v["particion"] == nombre]


def preparar_salida(par: Parametros, forzar: bool = False) -> Path:
    """Crea la carpeta de resultados y guarda parametros.json. Si la carpeta ya tiene
    resultados de otros parámetros (misma --etiqueta), se detiene salvo `forzar`."""
    salida = par.carpeta()
    salida.mkdir(parents=True, exist_ok=True)
    archivo = salida / "parametros.json"
    actual = par.a_dict()
    if archivo.exists():
        try:
            previo = json.loads(archivo.read_text(encoding="utf-8"))
        except ValueError:
            previo = None
        neutros = set(Parametros._NEUTROS)
        distintos = sorted(k for k in set(actual) | set(previo or {})
                           if k not in neutros and (previo or {}).get(k) != actual.get(k))
        con_resultados = any(salida.glob("*/metricas.json"))
        if previo is not None and distintos and con_resultados and not forzar:
            raise ErrorConfiguracion(
                f"{salida} ya tiene resultados con otros parámetros ({distintos}). "
                "Usa otra --etiqueta o --forzar para mezclarlos.")
    escribir_json(archivo, actual)
    return salida


def contexto(par: Parametros, forzar: bool = False, rehacer: bool = False) -> Contexto:
    v = ventanas_dataset(par, rehacer).sort_values(["secuencia", "w"]).reset_index(drop=True)
    disc = Discretizador(par.cortes).ajustar(v[v["particion"] == "entrenamiento"])
    v["o"] = disc.transformar(v)
    ctx = Contexto(par, v, disc, preparar_salida(par, forzar))
    _revisar_particiones(ctx)
    return ctx


def _revisar_particiones(ctx: Contexto) -> None:
    """Avisa (sin detener) cuando una etapa falta en entrenamiento o en prueba."""
    for p in particion.PARTICIONES:
        presentes = set(ctx.parte(p)["etiqueta"].unique().tolist())
        faltan = [config.ETAPAS[k] for k in range(1, config.N_ESTADOS) if k not in presentes]
        if faltan:
            nivel = logging.WARNING if p != "validacion" else logging.INFO
            log.log(nivel, "%s sin ventanas de %s", p, faltan)
    if not (ctx.parte("entrenamiento")["etiqueta"] > 0).any():
        raise ErrorDatos("El entrenamiento no tiene ventanas de ataque: no se puede estimar el modelo")


def describir_particiones(ctx: Contexto) -> dict:
    out = {}
    for p in particion.PARTICIONES:
        d = ctx.parte(p)
        out[p] = {
            "ventanas": int(len(d)), "secuencias": int(d["secuencia"].nunique()), "hosts": int(d["host"].nunique()),
            "ventanas_por_etapa": {config.ETAPAS[k]: int(n) for k, n in d["etiqueta"].value_counts().sort_index().items()},
            "episodios": int(len(metricas.episodios(d, ctx.dt, ctx.par.hueco_episodio))),
            "desde": str(pd.to_datetime(d["t"].min(), unit="s")), "hasta": str(pd.to_datetime(d["t"].max(), unit="s")),
        }
    out["simbolos"] = {"M": ctx.disc.M, "limites": {a: l.tolist() for a, l in ctx.disc.limites_.items()}}
    return out


# ------------------------------------------------------------------ HMM
def submuestrear(d: pd.DataFrame, rng: np.random.Generator, razon: float = 2.0, bloque: int = 72) -> pd.DataFrame:
    """D11: quita bloques benignos alejados (más de `bloque` ventanas) de toda actividad de
    ataque hasta que las ventanas benignas sean a lo más `razon` veces las atacadas.
    Las secuencias se recortan en los huecos que quedan, sin alterar su orden interno."""
    d = d.sort_values(["secuencia", "w"]).reset_index(drop=True)
    pos = np.arange(len(d))
    seq = d["secuencia"].to_numpy()
    atq = d["etiqueta"].to_numpy() > 0
    # Distancia (en ventanas de la misma secuencia) al ataque más cercano.
    dist = np.full(len(d), np.inf)
    for _, g in d.groupby("secuencia", sort=False).indices.items():
        a = g[atq[g]]
        if len(a):
            idx = np.searchsorted(a, g)
            izq = np.where(idx > 0, g - a[np.maximum(idx - 1, 0)], np.inf)
            der = np.where(idx < len(a), a[np.minimum(idx, len(a) - 1)] - g, np.inf)
            dist[g] = np.minimum(np.abs(izq), np.abs(der))
    lejos = dist > bloque
    # Bloques de hasta `bloque` ventanas lejanas consecutivas dentro de una secuencia.
    nuevo = np.r_[True, (seq[1:] != seq[:-1]) | (lejos[1:] != lejos[:-1])]
    tramo = np.cumsum(nuevo)
    sub = (pos - pd.Series(pos).groupby(tramo).transform("min").to_numpy()) // bloque
    id_bloque = np.where(lejos, tramo.astype(np.int64) * (len(d) + 1) + sub, -1)
    sobra = int((~atq).sum() - razon * atq.sum())
    quitar = np.array([], dtype=np.int64)
    if sobra > 0 and lejos.any():
        bloques = pd.Series(1, index=id_bloque[lejos]).groupby(level=0).size()
        orden = rng.permutation(bloques.index.to_numpy())
        acumulado = np.cumsum(bloques.loc[orden].to_numpy())
        quitar = orden[: np.searchsorted(acumulado, sobra) + 1]
    queda = ~np.isin(id_bloque, quitar)
    out = d[queda].copy()
    p = pos[queda]
    s = out["secuencia"].to_numpy()
    corte = np.r_[True, (s[1:] != s[:-1]) | (np.diff(p) > 1)]
    out["secuencia"] = np.cumsum(corte)
    return out


def _seqs(d: pd.DataFrame):
    return particion.secuencias(d, "o"), particion.secuencias(d, "etiqueta")


def inferir(modelo: hmm.HMM, d: pd.DataFrame, viterbi: bool = True) -> pd.DataFrame:
    if d.empty:
        raise ErrorDatos("No hay ventanas para inferir")
    d = d.sort_values(["secuencia", "w"])
    filt, vit = [], []
    for o in particion.secuencias(d, "o"):
        f, _ = modelo.filtrar(o)
        filt.append(f)
        if viterbi:
            vit.append(modelo.viterbi(o))
    F = np.vstack(filt)
    out = d[["host", "secuencia", "w", "t", "etiqueta", "apt", "aa"]].copy()
    for k, e in enumerate(config.ETAPAS):
        out[f"p_{e}"] = F[:, k]
    out["p_ataque"] = 1 - F[:, config.BENIGNO]
    out["pred_argmax"] = F.argmax(axis=1)
    if viterbi:
        out["pred_viterbi"] = np.concatenate(vit)
    return out


def _decidir(p: pd.DataFrame, tau: float, regla: str) -> np.ndarray:
    if regla == "umbral":
        P = p[[f"p_{e}" for e in config.ETAPAS]].to_numpy()
        ataque = 1 + P[:, 1:].argmax(axis=1)
        return np.where(p["p_ataque"].to_numpy() >= tau, ataque, 0)
    return p["pred_argmax"].to_numpy()


def _elegir_alfa(ctx: Contexto, obs, est, mascara, pesos=None) -> tuple[float, dict]:
    val = ctx.parte("validacion")
    par = ctx.par
    puntajes = {}
    for a in par.alfas_B:
        m = hmm.HMM.supervisado(obs, est, config.N_ESTADOS, ctx.disc.M, alfa_A=par.alfa_A, alfa_B=a,
                                alfa_pi=par.alfa_pi, mascara=mascara, pesos=pesos)
        p = inferir(m, val, viterbi=False)
        puntajes[a] = metricas.por_etapa(p["etiqueta"].to_numpy(), p["pred_argmax"].to_numpy())["macro_f1_ataque"]
    return max(puntajes, key=lambda a: (np.nan_to_num(puntajes[a], nan=-1), -a)), puntajes


def ejecutar_hmm(ctx: Contexto, variante: str, desbalance: str = "original") -> dict:
    if variante not in ("H0", "H1", "H2") or desbalance not in DESBALANCE_HMM:
        raise ErrorConfiguracion(f"Configuración HMM desconocida: {variante}-{desbalance}")
    par = ctx.par
    nombre = nombre_config(("hmm", variante, desbalance))
    t0 = time.time()
    rng = np.random.default_rng(par.semilla)
    ent = ctx.parte("entrenamiento")
    if desbalance == "remuestreo":
        ent = submuestrear(ent, rng, par.remuestreo_razon, par.remuestreo_bloque)
    obs, est = _seqs(ent)
    mascara = hmm.mascara_estructural(est)
    info: dict = {"config": nombre, "ventanas_entrenamiento": int(len(ent)),
                  "transiciones_prohibidas": [[config.ETAPAS[i], config.ETAPAS[j]] for i, j in zip(*np.where(~mascara))]}

    if variante == "H0":
        semillas = range(par.h0_semilla, par.h0_semilla + par.h0_reinicios)
        modelo, lls = hmm.no_supervisado(obs, config.N_ESTADOS, ctx.disc.M, semillas=semillas,
                                         max_iter=par.h0_max_iter, alfa_B=par.h0_alfa_B)
        p_ent = inferir(modelo, ent, viterbi=False)
        perm = hmm.asignacion_hungara(p_ent["pred_argmax"].to_numpy(), p_ent["etiqueta"].to_numpy(), config.N_ESTADOS)
        modelo = hmm.permutar(modelo, perm)
        info.update(ll_reinicios=lls, asignacion={f"estado_{k}": config.ETAPAS[perm[k]] for k in range(config.N_ESTADOS)})
    else:
        alfa, puntajes = _elegir_alfa(ctx, obs, est, mascara)
        modelo = hmm.HMM.supervisado(obs, est, config.N_ESTADOS, ctx.disc.M, alfa_A=par.alfa_A, alfa_B=alfa,
                                     alfa_pi=par.alfa_pi, mascara=mascara)
        info.update(alfa_B=alfa, macro_f1_val_por_alfa=puntajes)
        if variante == "H2":
            val = ctx.parte("validacion")
            obs_val, _ = _seqs(val)
            refinado, historia = hmm.refinar_em(modelo, obs, obs_val, mascara, alfa_A=par.alfa_A, alfa_B=alfa,
                                                alfa_pi=par.alfa_pi, max_iter=par.em_max_iter, paciencia=par.em_paciencia)
            # Verificación posterior: se descarta el refinamiento si algún estado pierde recall en validación.
            y_val = val.sort_values(["secuencia", "w"])["etiqueta"].to_numpy()
            r0 = metricas.por_etapa(y_val, inferir(modelo, val, False)["pred_argmax"].to_numpy())
            r1 = metricas.por_etapa(y_val, inferir(refinado, val, False)["pred_argmax"].to_numpy())
            degradados = [e for e, m in r1["por_etapa"].items()
                          if m["soporte"] > 0 and m["recall"] < r0["por_etapa"][e]["recall"] - par.tolerancia_recall]
            info.update(em_historia=historia, em_degradados=degradados, em_descartado=bool(degradados))
            if not degradados:
                modelo = refinado

    val = inferir(modelo, ctx.parte("validacion"), viterbi=False)
    tau = metricas.calibrar_tau(val.loc[val["etiqueta"] == 0, "p_ataque"].to_numpy(), par.fpr)
    prueba = inferir(modelo, ctx.parte(par.evaluar_en))
    prueba["pred"] = _decidir(prueba, tau, desbalance)
    res = _evaluar(ctx, nombre, prueba, tau, info)
    res["perfil_emisiones"] = perfil_emisiones(modelo, ctx.disc)
    np.savez(ctx.salida / nombre / "modelo.npz", A=modelo.A, B=modelo.B, pi=modelo.pi)
    res["segundos"] = round(time.time() - t0, 1)
    _guardar(ctx, nombre, res)
    return res


def perfil_emisiones(modelo: hmm.HMM, disc: Discretizador, top: int = 3) -> dict:
    """Los símbolos más probables de cada estado, legibles (verificación de la Sección 8.4)."""
    return {e: [{"simbolo": disc.describir(int(s)), "p": round(float(modelo.B[k, s]), 4)}
                for s in np.argsort(modelo.B[k])[::-1][:top]] for k, e in enumerate(config.ETAPAS)}


# ------------------------------------------------------------------ línea base
def ejecutar_base(ctx: Contexto, tipo: str, representacion: str, contexto_temporal: bool, balance: str) -> dict:
    if tipo not in ("RF", "XGB") or representacion not in ("continuo", "discreto") or balance not in BALANCE_BASE:
        raise ErrorConfiguracion(f"Configuración de línea base desconocida: {tipo}-{representacion}-{balance}")
    par = ctx.par
    nombre = nombre_config(("base", tipo, representacion, contexto_temporal, balance))
    t0 = time.time()
    if "niveles" not in ctx.cache:
        ctx.cache["niveles"] = ctx.disc.niveles_de(ctx.v)
    niv = ctx.cache["niveles"]
    # Posiciones (no etiquetas del índice): ctx.v está ordenado por (secuencia, w).
    partes = {p: np.flatnonzero(ctx.v["particion"].to_numpy() == p) for p in particion.PARTICIONES}
    ks = tuple(par.ks) if contexto_temporal else (0,)
    profundidades = par.rf_profundidades if tipo == "RF" else par.xgb_profundidades
    arboles = par.rf_arboles if tipo == "RF" else par.xgb_arboles
    y = ctx.v["etiqueta"].to_numpy()
    mejor = None
    seleccion = []
    for k in ks:
        X = baseline.caracteristicas(ctx.v, niv, representacion, k)
        for prof in profundidades:
            clf = baseline.Clasificador(tipo, prof, par.semilla, arboles, par.xgb_tasa, par.n_jobs, par.smote_fraccion)
            clf.ajustar(X[partes["entrenamiento"]], y[partes["entrenamiento"]], balance)
            pv = clf.proba(X[partes["validacion"]])
            f1 = metricas.por_etapa(y[partes["validacion"]], pv.argmax(1))["macro_f1_ataque"]
            seleccion.append({"k": k, "profundidad": prof, "macro_f1_val": f1, "smote_aplicado": clf.smote_aplicado})
            if mejor is None or np.nan_to_num(f1, nan=-1) > mejor[0]:
                mejor = (np.nan_to_num(f1, nan=-1), k, prof, clf, X, pv)
    _, k, prof, clf, X, pv = mejor
    benignas_val = y[partes["validacion"]] == 0
    tau = metricas.calibrar_tau(1 - pv[benignas_val, 0], par.fpr)
    P = clf.proba(X[partes[par.evaluar_en]])
    prueba = ctx.v.iloc[partes[par.evaluar_en]][["host", "secuencia", "w", "t", "etiqueta", "apt", "aa"]].copy()
    prueba["p_ataque"] = 1 - P[:, 0]
    prueba["pred"] = P.argmax(1)
    info = {"config": nombre, "k": k, "profundidad": prof, "smote_aplicado": clf.smote_aplicado, "seleccion": seleccion}
    res = _evaluar(ctx, nombre, prueba, tau, info)
    res["segundos"] = round(time.time() - t0, 1)
    _guardar(ctx, nombre, res)
    return res


# ------------------------------------------------------------------ común
def _evaluar(ctx: Contexto, nombre: str, prueba: pd.DataFrame, tau: float, info: dict) -> dict:
    (ctx.salida / nombre).mkdir(parents=True, exist_ok=True)
    hueco = ctx.par.hueco_episodio
    y = prueba["etiqueta"].to_numpy()
    res = dict(info)
    res["evaluado_en"] = ctx.par.evaluar_en
    res["tau"] = tau
    res["por_etapa"] = metricas.por_etapa(y, prueba["pred"].to_numpy())
    if "pred_viterbi" in prueba:
        res["por_etapa_viterbi"] = metricas.por_etapa(y, prueba["pred_viterbi"].to_numpy())
    res["deteccion"] = metricas.deteccion_temprana(prueba, tau, ctx.dt, hueco=hueco)
    # Desempeño separado por grupo atacante (Unraveled): episodios del grupo APT vs. aficionado.
    eps = pd.DataFrame(res["deteccion"]["episodios"])
    if len(eps) and eps["aa"].any():
        res["deteccion_por_grupo"] = {g: {"n": int(eps[g].sum()), "tasa_deteccion": float(eps.loc[eps[g], "detectado"].mean())}
                                      for g in ("apt", "aa") if eps[g].any()}
    metricas.curva_ttd_fpr(prueba, ctx.dt, hueco=hueco).to_csv(ctx.salida / nombre / "curva_ttd_fpr.csv", index=False)
    prueba.to_parquet(ctx.salida / nombre / "predicciones.parquet", index=False)
    return res


def limpiar(o):
    """Convierte a tipos de JSON estándar: NaN/inf pasan a null y los tipos de numpy a Python."""
    if isinstance(o, dict):
        return {str(k): limpiar(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [limpiar(v) for v in o]
    if isinstance(o, np.ndarray):
        return limpiar(o.tolist())
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, (int, np.integer)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return float(o) if math.isfinite(o) else None
    if o is None or isinstance(o, str):
        return o
    if o is pd.NA or o is pd.NaT:
        return None
    return str(o)


def escribir_json(ruta: Path, datos_json) -> None:
    """Escritura atómica: un corte a mitad de camino no deja un JSON truncado."""
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    tmp.write_text(json.dumps(limpiar(datos_json), ensure_ascii=False, indent=1, allow_nan=False), encoding="utf-8")
    tmp.replace(ruta)


def _guardar(ctx: Contexto, nombre: str, res: dict) -> None:
    (ctx.salida / nombre).mkdir(parents=True, exist_ok=True)
    escribir_json(ctx.salida / nombre / "metricas.json", res)


def nombre_config(c: tuple) -> str:
    if c[0] == "hmm":
        return "H0" if c[1] == "H0" else f"{c[1]}-{c[2]}"
    _, t, r, ctx, b = c
    return f"{'B1' if t == 'RF' else 'B2'}-{t}-{r}-{'ctx' if ctx else 'sinctx'}-{b}"


def todas_las_configuraciones(grupos=("H", "B")) -> list[tuple]:
    out = []
    if "H" in grupos:
        out += [("hmm", v, d) for v in ("H1", "H2") for d in DESBALANCE_HMM] + [("hmm", "H0", "original")]
    if "B" in grupos:
        out += [("base", t, r, c, b) for t in ("RF", "XGB") for r in ("continuo", "discreto")
                for c in (False, True) for b in BALANCE_BASE]
    return out


def ejecutar(ctx: Contexto, c: tuple) -> dict:
    return ejecutar_hmm(ctx, c[1], c[2]) if c[0] == "hmm" else ejecutar_base(ctx, *c[1:])


def ejecutar_lote(ctx: Contexto, configs: list[tuple], continuar: bool = False,
                  detener_en_error: bool = False) -> tuple[list[str], dict[str, str]]:
    """Corre varias configuraciones. Un fallo se registra (registro.log y errores.json) y
    se sigue con la siguiente, salvo `detener_en_error`. Con `continuar` se saltan las que
    ya tienen metricas.json. Devuelve (hechas, fallidas)."""
    hechas, fallidas, saltadas = [], {}, []
    archivo_err = ctx.salida / "errores.json"
    for i, c in enumerate(configs, 1):
        nombre = nombre_config(c)
        if continuar and (ctx.salida / nombre / "metricas.json").exists():
            saltadas.append(nombre)
            continue
        log.info("== [%d/%d] %s", i, len(configs), nombre)
        try:
            r = ejecutar(ctx, c)
        except KeyboardInterrupt:
            raise
        except Exception as x:          # noqa: BLE001 - se registra y se sigue con la siguiente
            fallidas[nombre] = f"{type(x).__name__}: {x}"
            log.error("   %s falló: %s\n%s", nombre, fallidas[nombre], traceback.format_exc())
            if detener_en_error:
                break
            continue
        hechas.append(nombre)
        d = r["deteccion"]
        log.info("   macro-F1 %s | FPR %s | detección %s | TTD mediana %s min | %ss",
                 _f(r["por_etapa"]["macro_f1_ataque"]), _f(d["fpr"], 4), _f(d.get("tasa_deteccion")),
                 _f(d.get("ttd_mediana_min"), 1), r["segundos"])
    if saltadas:
        log.info("Se saltaron %d configuraciones ya hechas (--continuar)", len(saltadas))
    previas = {}
    if archivo_err.exists():
        try:
            previas = json.loads(archivo_err.read_text(encoding="utf-8"))
        except ValueError:
            previas = {}
    for n in hechas:
        previas.pop(n, None)
    previas.update(fallidas)
    if previas:
        escribir_json(archivo_err, previas)
    elif archivo_err.exists():
        archivo_err.unlink()
    return hechas, fallidas


def _f(x, dec: int = 3) -> str:
    return "-" if x is None or (isinstance(x, float) and not math.isfinite(x)) else f"{x:.{dec}f}"


COLUMNAS_RESUMEN = (["config", "macro_f1", "macro_f1_viterbi"] + [f"f1_{e}" for e in config.ETAPAS[1:]]
                    + ["fpr", "n_episodios", "tasa_deteccion", "ttd_mediana_min", "precocidad_mediana", "tasa_pre_exf"])


def resumen(salida: Path) -> pd.DataFrame:
    filas = []
    for f in sorted(Path(salida).glob("*/metricas.json")):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
            d, pe = r.get("deteccion", {}), r["por_etapa"]
            fila = {"config": r["config"], "macro_f1": pe["macro_f1_ataque"],
                    "macro_f1_viterbi": r.get("por_etapa_viterbi", {}).get("macro_f1_ataque")}
            for e in config.ETAPAS[1:]:
                fila[f"f1_{e}"] = pe["por_etapa"][e]["f1"]
        except (ValueError, KeyError, TypeError) as x:
            log.warning("Se omite %s: %s", f, x)
            continue
        fila.update({k: d.get(k) for k in ("fpr", "n_episodios", "tasa_deteccion", "ttd_mediana_min",
                                            "precocidad_mediana", "tasa_pre_exf")})
        filas.append(fila)
    return pd.DataFrame(filas, columns=COLUMNAS_RESUMEN)

"""Línea de comandos.

    python -m apthmm preparar   --dataset dapt
    python -m apthmm ejecutar   --dataset dapt --grupos H B
    python -m apthmm ejecutar   --dataset unraveled --solo "H1-*" B1-RF-continuo-ctx-pesos --continuar
    python -m apthmm ejecutar   --config configs/sensibilidad_dt.toml
    python -m apthmm resumen    --dataset dapt
    python -m apthmm graficar   --dataset unraveled
    python -m apthmm listar
    python -m apthmm parametros --dataset unraveled --guardar configs/mio.toml

Códigos de salida: 0 bien, 1 alguna configuración falló, 2 error de configuración o de
datos, 130 interrumpido.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import logging
import sys
import traceback
from pathlib import Path

import pandas as pd

from . import config, datos, experimentos as ex
from .config import Parametros
from .errores import ErrorApthmm, ErrorConfiguracion

log = logging.getLogger("apthmm")


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="apthmm", description="Motor HMM para detección temprana de APT")
    sub = ap.add_subparsers(dest="cmd", required=True)
    comunes = argparse.ArgumentParser(add_help=False)
    g = comunes.add_argument_group("parámetros (sobrescriben a --config)")
    g.add_argument("--dataset", choices=list(config.DATASETS))
    g.add_argument("--config", help="archivo TOML con los parámetros del experimento")
    g.add_argument("--etiqueta", help="subcarpeta de results/<dataset>/ (por defecto, automática)")
    g.add_argument("--dt", type=int, help="segundos por ventana")
    g.add_argument("--encubrimiento", choices=("asignar", "excluir"))
    g.add_argument("--cortes", type=float, nargs="+", help="percentiles de discretización, p. ej. 0.333 0.667")
    g.add_argument("--fpr", type=float, help="tasa objetivo de falsas alarmas para calibrar tau")
    g.add_argument("--semilla", type=int)
    g.add_argument("--evaluar-en", dest="evaluar_en", choices=("prueba", "validacion"),
                   help="validacion para comparar sensibilidades sin mirar la prueba")
    g.add_argument("--n-jobs", type=int, dest="n_jobs", help="núcleos para RF y XGBoost")
    g.add_argument("--ruta-datos", dest="ruta", help="carpeta de los CSV del conjunto de datos")
    comunes.add_argument("-v", "--detallado", action="store_true", help="mensajes de depuración")
    datos_ = argparse.ArgumentParser(add_help=False)
    datos_.add_argument("--rehacer-cache", action="store_true", help="vuelve a leer los CSV y a construir las ventanas")
    datos_.add_argument("--forzar", action="store_true", help="permite escribir en una carpeta con otros parámetros")

    sub.add_parser("preparar", parents=[comunes, datos_], help="carga, ventanas y particiones")
    e = sub.add_parser("ejecutar", parents=[comunes, datos_], help="corre configuraciones de la Tabla 8.4")
    e.add_argument("--grupos", nargs="+", default=["H", "B"], choices=["H", "B"])
    e.add_argument("--solo", nargs="+", help="nombres o patrones (p. ej. 'H1-*'); ver 'listar'")
    e.add_argument("--continuar", action="store_true", help="salta las configuraciones que ya tienen metricas.json")
    e.add_argument("--detener-en-error", action="store_true", help="se detiene en la primera configuración que falle")
    sub.add_parser("resumen", parents=[comunes], help="tabla con todas las configuraciones de una carpeta")
    gr = sub.add_parser("graficar", parents=[comunes], help="curva TTD vs. FPR")
    gr.add_argument("--configs", nargs="+", help="por defecto: todas las HMM y las dos mejores líneas base")
    sub.add_parser("listar", help="nombres de las configuraciones disponibles")
    p = sub.add_parser("parametros", parents=[comunes], help="muestra los parámetros efectivos en TOML")
    p.add_argument("--guardar", help="escribe la plantilla TOML en este archivo")
    return ap


def _parametros(a) -> Parametros:
    cambios = {k: getattr(a, k, None) for k in ("etiqueta", "dt", "encubrimiento", "cortes", "fpr", "semilla", "n_jobs", "ruta", "evaluar_en")}
    return Parametros.desde(a.dataset, a.config, **cambios)


def _registro(detallado: bool, archivo: Path | None = None) -> None:
    raiz = logging.getLogger()
    for h in list(raiz.handlers):
        raiz.removeHandler(h)
    formato = logging.Formatter("%(asctime)s %(levelname).1s %(message)s", datefmt="%H:%M:%S")
    consola = logging.StreamHandler()
    consola.setFormatter(formato)
    raiz.addHandler(consola)
    if archivo:
        fh = logging.FileHandler(archivo, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        raiz.addHandler(fh)
    raiz.setLevel(logging.DEBUG if detallado else logging.INFO)
    for ruidoso in ("matplotlib", "PIL", "numba"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)


def elegir_configuraciones(grupos, solo) -> list[tuple]:
    if not solo:
        return ex.todas_las_configuraciones(tuple(grupos))
    todas = {ex.nombre_config(c): c for c in ex.todas_las_configuraciones(("H", "B"))}
    elegidas, sin_coincidencia = {}, []
    for patron in solo:
        hits = [n for n in todas if fnmatch.fnmatchcase(n, patron)]
        if not hits:
            sin_coincidencia.append(patron)
        elegidas.update({n: todas[n] for n in hits})
    if sin_coincidencia:
        raise ErrorConfiguracion(f"Ninguna configuración coincide con {sin_coincidencia}. Usa 'python -m apthmm listar'.")
    return list(elegidas.values())


def main(argv=None) -> int:
    for flujo in (sys.stdout, sys.stderr):
        if not flujo.isatty() and hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8", errors="replace")
    a = _parser().parse_args(argv)
    _registro(getattr(a, "detallado", False))
    pd.set_option("display.width", 200, "display.max_columns", 30)
    try:
        return _despachar(a)
    except ErrorApthmm as x:
        log.error("%s", x)
        return 2
    except KeyboardInterrupt:
        log.error("Interrumpido. Con --continuar se retoma desde la última configuración terminada.")
        return 130


def _despachar(a) -> int:
    if a.cmd == "listar":
        for c in ex.todas_las_configuraciones(("H", "B")):
            print(ex.nombre_config(c))
        return 0

    par = _parametros(a)
    if a.cmd == "parametros":
        texto = par.a_toml()
        if a.guardar:
            Path(a.guardar).parent.mkdir(parents=True, exist_ok=True)
            Path(a.guardar).write_text(texto, encoding="utf-8")
            print("Plantilla escrita en", a.guardar)
        else:
            print(texto)
        print(f"# carpeta de resultados: {par.carpeta()}", file=sys.stderr)
        return 0

    if a.cmd in ("resumen", "graficar"):
        salida = par.carpeta()
        if not salida.exists():
            raise ErrorConfiguracion(f"No hay resultados en {salida}. Revisa --dataset, --etiqueta y los parámetros.")
        if a.cmd == "graficar":
            print("Figura:", graficar(salida, a.configs))
            return 0
        tabla = ex.resumen(salida)
        if tabla.empty:
            raise ErrorConfiguracion(f"{salida} no tiene metricas.json")
        tabla.to_csv(salida / "resumen.csv", index=False)
        print(tabla.round(3).to_string(index=False))
        return 0

    # preparar y ejecutar: se valida todo antes de cargar datos.
    configs = elegir_configuraciones(a.grupos, a.solo) if a.cmd == "ejecutar" else []
    salida = ex.preparar_salida(par, a.forzar)
    _registro(a.detallado, salida / "registro.log")
    log.info("Parámetros: %s | salida %s", json.dumps(par.diferencias() or "por defecto", ensure_ascii=False), salida)
    if a.cmd == "preparar":
        print(json.dumps(datos.resumen(datos.cargar(par.dataset, par.ruta, usar_cache=not a.rehacer_cache)),
                         indent=1, ensure_ascii=False))
    ctx = ex.contexto(par, forzar=True, rehacer=a.rehacer_cache and a.cmd == "ejecutar")
    if a.cmd == "preparar":
        desc = ex.describir_particiones(ctx)
        ex.escribir_json(ctx.salida / "particiones.json", desc)
        print(json.dumps(ex.limpiar(desc), indent=1, ensure_ascii=False))
        return 0

    hechas, fallidas = ex.ejecutar_lote(ctx, configs, a.continuar, a.detener_en_error)
    tabla = ex.resumen(ctx.salida)
    if not tabla.empty:
        tabla.to_csv(ctx.salida / "resumen.csv", index=False)
        print(tabla.round(3).to_string(index=False))
    if fallidas:
        log.error("%d configuraciones fallaron (detalle en %s y errores.json):", len(fallidas), ctx.salida / "registro.log")
        for n, m in fallidas.items():
            log.error("  %s: %s", n, m)
        return 1
    log.info("Listo: %d configuraciones en %s", len(hechas), ctx.salida)
    return 0


def graficar(salida, configs=None):
    """Curvas tasa de detección y TTD frente a la tasa de falsas alarmas (estilo cAPTure)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    salida = Path(salida)
    if configs is None:
        tabla = ex.resumen(salida)
        if tabla.empty:
            raise ErrorConfiguracion(f"{salida} no tiene resultados que graficar")
        hmm_ = [c for c in tabla["config"] if c.startswith("H")]
        base = tabla[tabla["config"].str.startswith("B")].sort_values("macro_f1", ascending=False)["config"].head(2).tolist()
        configs = hmm_ + base
    curvas = {}
    for c in configs:
        archivo = salida / c / "curva_ttd_fpr.csv"
        if not archivo.exists():
            log.warning("Sin curva para %s (%s), se omite", c, archivo)
            continue
        curva = pd.read_csv(archivo)
        curvas[c] = curva[curva["fpr"] > 0]
    if not curvas:
        raise ErrorConfiguracion("Ninguna de las configuraciones pedidas tiene curva_ttd_fpr.csv")
    fig, ejes = plt.subplots(1, 2, figsize=(11, 4))
    for c, curva in curvas.items():
        estilo = "-" if c.startswith("H") else "--"
        ejes[0].plot(curva["fpr"], curva["tasa_deteccion"], estilo, marker=".", label=c)
        ejes[1].plot(curva["fpr"], curva["ttd_mediana_min"], estilo, marker=".", label=c)
    for ax, y in zip(ejes, ("Episodios detectados (fracción)", "TTD mediano (min)")):
        ax.set_xscale("log")
        ax.set_xlabel("Tasa de falsas alarmas por ventana benigna")
        ax.set_ylabel(y)
        ax.grid(alpha=0.3)
    ejes[0].legend(fontsize=7)
    fig.tight_layout()
    destino = salida / "curva_ttd_fpr.png"
    fig.savefig(destino, dpi=150)
    plt.close(fig)
    return destino


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                    # noqa: BLE001 - defecto del código: traza completa
        traceback.print_exc()
        sys.exit(1)

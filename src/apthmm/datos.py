"""Carga de DAPT2020 y Unraveled a un formato común de flujos.

Columnas del formato común:
    ts         inicio del flujo (segundos, época UTC)
    src, dst   IP de origen y destino
    dport      puerto de destino
    dur        duración (s)
    bytes_fwd  bytes enviados por src
    bytes_bwd  bytes enviados por dst
    pkts_bwd   paquetes enviados por dst (0 = sin respuesta)
    rst        1 si el flujo tiene algún paquete con RST
    etapa      etapa normalizada (config.MAPA_ETAPAS) o "encubrimiento"
    grupo      grupo atacante en Unraveled (APT, AA, SH) o "" si no aplica
"""
from __future__ import annotations

import csv
import hashlib
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from . import config
from .errores import ErrorDatos

log = logging.getLogger(__name__)

COLUMNAS = ["ts", "src", "dst", "dport", "dur", "bytes_fwd", "bytes_bwd", "pkts_bwd", "rst", "etapa", "grupo"]
# Subir al cambiar la lógica de carga: invalida las cachés de flujos.
VERSION_CARGA = 2
# Fracción de filas descartadas a partir de la cual se avisa.
AVISO_DESCARTE = 0.001


def normalizar_etapa(serie: pd.Series) -> pd.Series:
    s = serie.astype(str).str.strip().str.lower()
    out = s.map(config.MAPA_ETAPAS)
    desconocidas = s[out.isna()].unique()
    if len(desconocidas):
        raise ErrorDatos(f"Etiquetas de etapa sin correspondencia en config.MAPA_ETAPAS: {list(desconocidas[:10])}")
    return out


def _archivos(ruta: Path, patron: str, recursivo: bool) -> list[Path]:
    ruta = Path(ruta)
    if not ruta.exists():
        raise ErrorDatos(f"No existe la carpeta de datos {ruta}. Ajusta 'ruta' en [datos] o con --ruta-datos.")
    archivos = sorted(ruta.rglob(patron) if recursivo else ruta.glob(patron))
    if not archivos:
        raise ErrorDatos(f"No hay archivos {patron} en {ruta}")
    return archivos


# ---------------------------------------------------------------- DAPT2020
_DAPT = {
    "Src IP": "src", "Dst IP": "dst", "Dst Port": "dport", "Timestamp": "ts",
    "Flow Duration": "dur", "Total Length of Fwd Packet": "bytes_fwd",
    "Total Length of Bwd Packet": "bytes_bwd", "Total Bwd packets": "pkts_bwd",
    "RST Flag Count": "rst", "Stage": "etapa",
}


def _primera_fila(f: Path) -> list[str]:
    with open(f, newline="", encoding="utf-8", errors="replace") as fh:
        return next(csv.reader(fh), [])


def cargar_dapt(ruta: Path) -> pd.DataFrame:
    archivos = _archivos(ruta, "*.csv", recursivo=False)
    primeras = {f: _primera_fila(f) for f in archivos}
    vacios = [f.name for f, p in primeras.items() if not p]
    if vacios:
        log.warning("DAPT2020: archivos vacíos que se omiten: %s", vacios)
    encabezado = next((p for p in primeras.values() if p and p[0] == "Flow ID"), None)
    if encabezado is None:
        raise ErrorDatos(f"Ningún CSV de {ruta} trae el encabezado de CICFlowMeter ('Flow ID', ...)")
    faltan = [c for c in _DAPT if c not in encabezado]
    if faltan:
        raise ErrorDatos(f"Al encabezado de DAPT2020 le faltan columnas: {faltan}")
    partes = []
    for f, primera in primeras.items():
        if not primera:
            continue
        tiene_encabezado = primera[0] == "Flow ID"
        if not tiene_encabezado:
            if len(primera) != len(encabezado):
                raise ErrorDatos(f"{f.name} no trae encabezado y tiene {len(primera)} columnas en vez de {len(encabezado)}")
            log.info("%s no trae encabezado: se usa el de los demás archivos", f.name)
        try:
            df = pd.read_csv(f, header=0 if tiene_encabezado else None,
                             names=None if tiene_encabezado else encabezado, low_memory=False)
        except (pd.errors.ParserError, UnicodeDecodeError) as x:
            raise ErrorDatos(f"No se pudo leer {f.name}: {x}") from None
        faltan = [c for c in _DAPT if c not in df.columns]
        if faltan:
            raise ErrorDatos(f"{f.name}: faltan columnas {faltan}")
        partes.append(df[list(_DAPT)].rename(columns=_DAPT))
    df = pd.concat(partes, ignore_index=True)
    ts = pd.to_datetime(df["ts"], format="%d/%m/%Y %I:%M:%S %p", errors="coerce")
    malas = int(ts.isna().sum())
    if malas:
        log.warning("DAPT2020: %d marcas de tiempo sin parsear, se descartan esas filas", malas)
        df, ts = df[ts.notna()], ts[ts.notna()]
    # Sin zona horaria en el origen: se interpreta como UTC. La división por
    # Timedelta no depende de la resolución interna (ns, us o s) de pandas.
    df = df.assign(ts=(ts - pd.Timestamp("1970-01-01")) / pd.Timedelta(seconds=1))
    df["dur"] = pd.to_numeric(df["dur"], errors="coerce") / 1e6          # CICFlowMeter reporta microsegundos
    df["rst"] = (pd.to_numeric(df["rst"], errors="coerce").fillna(0) > 0).astype("int8")
    df["etapa"] = normalizar_etapa(df["etapa"])
    df["grupo"] = ""
    df.attrs["descartadas"] = malas
    return _tipos(df)


# --------------------------------------------------------------- Unraveled
_UNR = {
    "src_ip": "src", "dst_ip": "dst", "dst_port": "dport",
    "bidirectional_first_seen_ms": "ts", "bidirectional_duration_ms": "dur",
    "src2dst_bytes": "bytes_fwd", "dst2src_bytes": "bytes_bwd",
    "dst2src_packets": "pkts_bwd", "bidirectional_rst_packets": "rst",
}
_ETIQUETAS_UNR = ["Activity", "Stage", "DefenderResponse", "Signature"]


def reparar_fila(fila: list[str], n_cols: int, idx_texto: int) -> list[str] | None:
    """Devuelve la fila alineada con el encabezado o None si no se puede reparar.

    Las filas con columnas de más se deben a campos de texto (p. ej. user_agent) con
    comas sin comillas. Los campos numéricos están antes del primer campo de texto y
    las cuatro etiquetas al final, así que ambos se recuperan por posición.
    """
    if len(fila) == n_cols:
        return fila
    if len(fila) > n_cols:
        n_txt = n_cols - idx_texto - len(_ETIQUETAS_UNR)
        return fila[:idx_texto] + [""] * n_txt + fila[-len(_ETIQUETAS_UNR):]
    return None


def _indices_unraveled(f: Path, enc: list[str]) -> tuple[list[int], int]:
    faltan = [c for c in list(_UNR) + ["application_name"] if c not in enc]
    if faltan or enc[-4:] != _ETIQUETAS_UNR:
        raise ErrorDatos(f"{f}: encabezado inesperado (faltan {faltan} o las 4 etiquetas no están al final)")
    idx = [enc.index(c) for c in _UNR] + [enc.index(c) for c in ("Stage", "Signature")]
    idx_texto = enc.index("application_name")
    if max(idx[: len(_UNR)]) >= idx_texto:
        raise ErrorDatos(f"{f}: hay columnas numéricas después de application_name; la reparación por posición no aplica")
    return idx, idx_texto


def cargar_unraveled(ruta: Path) -> pd.DataFrame:
    csv.field_size_limit(10**9)
    archivos = _archivos(ruta, "*.csv", recursivo=True)
    partes, reparadas, descartadas = [], 0, 0
    for i, f in enumerate(archivos, 1):
        try:
            with open(f, newline="", encoding="utf-8", errors="replace") as fh:
                lector = csv.reader(fh)
                enc = next(lector, None)
                if enc is None:
                    log.warning("%s está vacío, se omite", f)
                    continue
                n = len(enc)
                idx, idx_texto = _indices_unraveled(f, enc)
                filas = []
                for fila in lector:
                    if len(fila) != n:
                        fila = reparar_fila(fila, n, idx_texto)
                        if fila is None:
                            descartadas += 1
                            continue
                        reparadas += 1
                    filas.append([fila[j] for j in idx])
        except csv.Error as x:
            raise ErrorDatos(f"{f}: CSV mal formado ({x})") from None
        partes.append(pd.DataFrame(filas, columns=list(_UNR.values()) + ["etapa", "grupo"]))
        if i % 20 == 0:
            log.info("Unraveled: %d/%d archivos", i, len(archivos))
    if not partes:
        raise ErrorDatos(f"Todos los CSV de {ruta} están vacíos")
    df = pd.concat(partes, ignore_index=True)
    for c in ("ts", "dur", "bytes_fwd", "bytes_bwd", "pkts_bwd", "rst"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    sin_ts = int(df["ts"].isna().sum())
    if sin_ts:
        df = df[df["ts"].notna()]
    descartadas += sin_ts
    log.info("Unraveled: %d filas reparadas, %d descartadas (%d sin marca de tiempo)", reparadas, descartadas, sin_ts)
    df["ts"] = df["ts"] / 1000
    df["dur"] = df["dur"] / 1000
    df["rst"] = (df["rst"].fillna(0) > 0).astype("int8")
    df["etapa"] = normalizar_etapa(df["etapa"])
    df["grupo"] = df["grupo"].replace({"None": "", "nan": ""})
    df.attrs["reparadas"], df.attrs["descartadas"] = reparadas, descartadas
    return _tipos(df)


def _tipos(df: pd.DataFrame) -> pd.DataFrame:
    total = len(df) + df.attrs.get("descartadas", 0)
    if total and df.attrs.get("descartadas", 0) / total > AVISO_DESCARTE:
        log.warning("Se descartó el %.2f %% de las filas", 100 * df.attrs["descartadas"] / total)
    attrs = dict(df.attrs)
    df = df[COLUMNAS].copy()
    df["dport"] = pd.to_numeric(df["dport"], errors="coerce").fillna(-1).astype("int32")
    for c in ("dur", "bytes_fwd", "bytes_bwd"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype("float64")
    df["pkts_bwd"] = pd.to_numeric(df["pkts_bwd"], errors="coerce").fillna(0).astype("int64")
    for c in ("src", "dst", "etapa", "grupo"):
        df[c] = df[c].astype("category")
    df = df.sort_values("ts", kind="stable").reset_index(drop=True)
    df.attrs.update(attrs)
    return df


# ------------------------------------------------------------------- caché
def _huella_fuente(dataset: str, ruta: Path) -> dict:
    recursivo = dataset != "dapt"
    archivos = _archivos(ruta, "*.csv", recursivo)
    return {"version": VERSION_CARGA, "dataset": dataset,
            "archivos": [[str(f.relative_to(ruta)), f.stat().st_size, f.stat().st_mtime_ns] for f in archivos]}


def cargar(dataset: str, ruta: str | Path | None = None, usar_cache: bool = True) -> pd.DataFrame:
    """Carga un conjunto de datos en el formato común, con caché en Parquet.

    La caché se rehace sola si cambian los CSV de origen (nombre, tamaño o fecha) o la
    versión del cargador. Si la carpeta de origen no está pero la caché sí, se usa la caché.
    """
    defecto = Path(config.DATASETS[dataset]["ruta"])
    ruta = Path(ruta or defecto)
    # Una caché por carpeta de origen: otra --ruta-datos no reutiliza la de la ruta por defecto.
    sufijo = "" if ruta.resolve() == defecto.resolve() else "_" + hashlib.sha1(str(ruta.resolve()).encode()).hexdigest()[:8]
    destino = config.CACHE / f"{dataset}_flujos{sufijo}.parquet"
    meta = destino.with_suffix(".json")
    if usar_cache and destino.exists():
        if not ruta.exists():
            log.warning("No está %s: se usa la caché %s sin verificar que esté al día", ruta, destino.name)
            return pd.read_parquet(destino)
        try:
            guardada = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            guardada = None
        if guardada == _huella_fuente(dataset, ruta):
            return pd.read_parquet(destino)
        log.info("La caché de flujos de %s no corresponde a los CSV actuales: se rehace", dataset)
    huella = _huella_fuente(dataset, ruta)
    df = cargar_dapt(ruta) if dataset == "dapt" else cargar_unraveled(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(destino)
    meta.write_text(json.dumps(huella), encoding="utf-8")
    return df


def resumen(df: pd.DataFrame) -> dict:
    return {
        "flujos": int(len(df)),
        "por_etapa": {k: int(v) for k, v in df["etapa"].value_counts().items()},
        "por_grupo": {k or "-": int(v) for k, v in df.loc[df["etapa"] != "benigno", "grupo"].value_counts().items()},
        "inicio": str(pd.to_datetime(df["ts"].min(), unit="s")),
        "fin": str(pd.to_datetime(df["ts"].max(), unit="s")),
        "proporcion_benigna": float(np.mean(df["etapa"] == "benigno")),
    }

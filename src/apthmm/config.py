"""Constantes del modelo, conjuntos de datos y parámetros de un experimento.

Los parámetros se toman, en este orden de prioridad: opciones de la línea de comandos,
archivo TOML (`--config`), valores por conjunto de datos (DATASETS) y valores por
defecto de `Parametros` (decisiones de docs/plan_experimentacion.md).
"""
from __future__ import annotations

import copy
import hashlib
import json
import tomllib
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any, Callable

from .errores import ErrorConfiguracion

RAIZ = Path(__file__).resolve().parents[2]
DATOS = RAIZ / "data"
CACHE = DATOS / "cache"
RESULTADOS = RAIZ / "results"

# Estados ocultos del modelo. El índice es el número de estado y define el orden
# de avance de la campaña (etapa más avanzada = índice mayor).
ETAPAS = ["benigno", "reconocimiento", "foothold", "lateral", "exfiltracion"]
N_ESTADOS = len(ETAPAS)
BENIGNO = 0
EXFILTRACION = ETAPAS.index("exfiltracion")

# Etiquetas originales (en minúscula) -> etapa normalizada.
MAPA_ETAPAS = {
    "benign": "benigno",
    "reconnaissance": "reconocimiento",
    "establish foothold": "foothold",
    "lateral movement": "lateral",
    "data exfiltration": "exfiltracion",
    "cover up": "encubrimiento",
    "pivoting": "lateral",
}

ATRIBUTOS = ["A1_bytes_salida", "A2_duracion", "A3_puertos", "A4_fallidos"]

DATASETS = {
    "dapt": {
        "ruta": DATOS / "dapt2020" / "csv",
        "internos": ["192.168.3."],
        "externos": [],
        "min_flujos": 100,
        "particion": {"tipo": "intradia", "fracciones": [0.6, 0.2, 0.2]},
        "fpr": 0.01,
    },
    "unraveled": {
        "ruta": DATOS / "unraveled" / "data" / "network-flows",
        # 10.8.10.x es infraestructura del atacante (extremo externo de los flujos APT/AA).
        "internos": ["10.", "192.168."],
        "externos": ["10.8.10."],
        "min_flujos": 1000,
        # Fechas en UTC, ambos extremos incluidos.
        "particion": {
            "tipo": "fechas",
            "entrenamiento": ["2021-05-26", "2021-06-26"],
            "validacion": ["2021-06-27", "2021-06-29"],
            "prueba": ["2021-06-30", "2021-07-06"],
        },
        "fpr": 0.001,
    },
}

# Constantes que usan los módulos cuando se llaman sin Parametros (pruebas, uso interactivo).
DT = 300
MAX_HUECO = 12
CORTES = (0.50, 0.95)
ALFAS_B = (0.01, 0.1, 1.0)
ALFA_A = 1.0
ALFA_PI = 1.0
HUECO_EPISODIO = 6 * 3600
SEMILLA = 2027


def es_interno_por_prefijos(internos: list[str], externos: list[str]) -> Callable[[str], bool]:
    """Una IP es interna si empieza con algún prefijo de `internos` y con ninguno de `externos`."""
    internos, externos = tuple(internos), tuple(externos)
    return lambda ip: ip.startswith(internos) and not (externos and ip.startswith(externos))


# --------------------------------------------------------------- parámetros
def _p(defecto, seccion: str, tipo: str, ayuda: str):
    return field(default=defecto, metadata={"seccion": seccion, "tipo": tipo, "ayuda": ayuda})


@dataclass
class Parametros:
    dataset: str = ""
    etiqueta: str = _p("", "general", "str", "subcarpeta de results/<dataset>/ (vacío = automática)")
    # [datos] (None = valor de DATASETS)
    ruta: str | None = _p(None, "datos", "str", "carpeta de los CSV")
    internos: list | None = _p(None, "datos", "lista_str", "prefijos de IP internas")
    externos: list | None = _p(None, "datos", "lista_str", "prefijos excluidos de los internos")
    min_flujos: int | None = _p(None, "datos", "int", "flujos mínimos para incluir un host")
    particion: dict | None = _p(None, "datos", "dict", "partición (tipo = fechas o intradia)")
    # [ventanas]
    dt: int = _p(DT, "ventanas", "int", "segundos por ventana")
    max_hueco: int = _p(MAX_HUECO, "ventanas", "int", "ventanas sin captura que cortan una secuencia")
    encubrimiento: str = _p("asignar", "ventanas", "str", "asignar (a exfiltración) o excluir")
    cortes: tuple = _p(CORTES, "ventanas", "tupla_float", "percentiles de discretización")
    # [hmm]
    alfas_B: tuple = _p(ALFAS_B, "hmm", "tupla_float", "suavizado de emisiones, se elige en validación")
    alfa_A: float = _p(ALFA_A, "hmm", "float", "suavizado de transiciones permitidas")
    alfa_pi: float = _p(ALFA_PI, "hmm", "float", "suavizado de la distribución inicial")
    em_max_iter: int = _p(50, "hmm", "int", "iteraciones máximas de Baum-Welch (H2)")
    em_paciencia: int = _p(2, "hmm", "int", "caídas seguidas de la verosimilitud de validación que detienen EM")
    tolerancia_recall: float = _p(0.01, "hmm", "float", "caída de recall que descarta el refinamiento")
    h0_reinicios: int = _p(10, "hmm", "int", "inicializaciones aleatorias del control H0")
    h0_max_iter: int = _p(100, "hmm", "int", "iteraciones máximas por reinicio de H0")
    h0_semilla: int = _p(0, "hmm", "int", "semilla del primer reinicio de H0")
    h0_alfa_B: float = _p(0.1, "hmm", "float", "pseudoconteo de emisiones en H0")
    remuestreo_razon: float = _p(2.0, "hmm", "float", "ventanas benignas por cada ventana de ataque")
    remuestreo_bloque: int = _p(72, "hmm", "int", "tamaño de bloque benigno que se quita")
    # [base]
    ks: tuple = _p((1, 3, 6), "base", "tupla_int", "ventanas previas probadas (variante con contexto)")
    rf_arboles: int = _p(200, "base", "int", "árboles del Random Forest")
    rf_profundidades: tuple = _p((None, 20), "base", "tupla_prof", "profundidades RF (0 = sin límite)")
    xgb_arboles: int = _p(300, "base", "int", "árboles de XGBoost")
    xgb_profundidades: tuple = _p((4, 8), "base", "tupla_prof", "profundidades XGBoost")
    xgb_tasa: float = _p(0.1, "base", "float", "tasa de aprendizaje de XGBoost")
    smote_fraccion: float = _p(0.1, "base", "float", "fracción de la clase mayoritaria que alcanza SMOTE")
    n_jobs: int = _p(-1, "base", "int", "núcleos para RF y XGBoost (-1 = todos)")
    # [evaluacion]
    fpr: float | None = _p(None, "evaluacion", "float", "tasa objetivo de falsas alarmas para calibrar tau")
    hueco_episodio: float = _p(HUECO_EPISODIO, "evaluacion", "float", "segundos sin ataque que separan episodios")
    evaluar_en: str = _p("prueba", "evaluacion", "str", "partición evaluada: prueba o validacion (sensibilidades, Fase 3)")
    semilla: int = _p(SEMILLA, "evaluacion", "int", "semilla de remuestreo y línea base")

    # Campos que no cambian los resultados y no entran en la huella de la carpeta.
    _NEUTROS = ("etiqueta", "n_jobs")
    # Campos de los que depende la caché de ventanas.
    _VENTANAS = ("ruta", "internos", "externos", "min_flujos", "particion", "dt", "encubrimiento", "max_hueco")

    def __post_init__(self):
        if self.dataset not in DATASETS:
            raise ErrorConfiguracion(f"Conjunto de datos desconocido: {self.dataset!r}. Opciones: {sorted(DATASETS)}")
        base = DATASETS[self.dataset]
        for c in ("ruta", "internos", "externos", "min_flujos", "particion", "fpr"):
            if getattr(self, c) is None:
                setattr(self, c, copy.deepcopy(base[c]))
        self.ruta = str(self.ruta)
        for f in fields(self):
            if "tipo" in f.metadata:
                setattr(self, f.name, _convertir(f.name, f.metadata["tipo"], getattr(self, f.name)))
        self.validar()

    # ---------------------------------------------------------- construcción
    @classmethod
    def desde(cls, dataset: str | None = None, archivo: str | Path | None = None, **cambios) -> "Parametros":
        """Combina el archivo TOML (si lo hay) con `cambios` (los None se ignoran)."""
        valores: dict[str, Any] = leer_toml(archivo) if archivo else {}
        if dataset:
            valores["dataset"] = dataset
        valores.update({k: v for k, v in cambios.items() if v is not None})
        if not valores.get("dataset"):
            raise ErrorConfiguracion("Falta el conjunto de datos: usa --dataset o 'dataset = ...' en el archivo")
        desconocidos = set(valores) - {f.name for f in fields(cls)}
        if desconocidos:
            raise ErrorConfiguracion(f"Parámetros desconocidos: {sorted(desconocidos)}")
        return cls(**valores)

    def con(self, **cambios) -> "Parametros":
        return replace(self, **cambios)

    # ------------------------------------------------------------ validación
    def validar(self) -> None:
        e = []
        def exigir(cond, msj):
            if not cond:
                e.append(msj)
        exigir(self.dt > 0, "dt debe ser positivo")
        exigir(self.max_hueco >= 0, "max_hueco no puede ser negativo")
        exigir(self.encubrimiento in ("asignar", "excluir"), "encubrimiento debe ser 'asignar' o 'excluir'")
        exigir(len(self.cortes) >= 1 and all(0 < c < 1 for c in self.cortes)
               and all(a < b for a, b in zip(self.cortes, self.cortes[1:])),
               f"cortes deben ser percentiles crecientes en (0, 1): {self.cortes}")
        exigir(len(self.alfas_B) >= 1 and all(a > 0 for a in self.alfas_B), "alfas_B deben ser positivos")
        exigir(min(self.alfa_A, self.alfa_pi, self.h0_alfa_B) >= 0, "alfa_A, alfa_pi y h0_alfa_B no pueden ser negativos")
        exigir(self.em_max_iter >= 1 and self.em_paciencia >= 1, "em_max_iter y em_paciencia deben ser >= 1")
        exigir(self.tolerancia_recall >= 0, "tolerancia_recall no puede ser negativa")
        exigir(self.h0_reinicios >= 1 and self.h0_max_iter >= 1, "h0_reinicios y h0_max_iter deben ser >= 1")
        exigir(self.remuestreo_razon > 0 and self.remuestreo_bloque >= 1, "remuestreo_razon > 0 y remuestreo_bloque >= 1")
        exigir(len(self.ks) >= 1 and all(k >= 1 for k in self.ks), "ks deben ser enteros >= 1")
        for nombre in ("rf_profundidades", "xgb_profundidades"):
            v = getattr(self, nombre)
            exigir(len(v) >= 1 and all(p is None or p >= 1 for p in v), f"{nombre} deben ser >= 1 (0 = sin límite, solo RF)")
        exigir(None not in self.xgb_profundidades, "XGBoost necesita una profundidad finita")
        exigir(self.rf_arboles >= 1 and self.xgb_arboles >= 1, "el número de árboles debe ser >= 1")
        exigir(0 < self.xgb_tasa <= 1, "xgb_tasa debe estar en (0, 1]")
        exigir(0 < self.smote_fraccion <= 1, "smote_fraccion debe estar en (0, 1]")
        exigir(self.fpr is not None and 0 < self.fpr < 1, f"fpr debe estar en (0, 1): {self.fpr}")
        exigir(self.hueco_episodio > 0, "hueco_episodio debe ser positivo")
        exigir(self.evaluar_en in ("prueba", "validacion"), "evaluar_en debe ser 'prueba' o 'validacion'")
        exigir(self.min_flujos >= 0, "min_flujos no puede ser negativo")
        exigir(len(self.internos) >= 1, "internos necesita al menos un prefijo")
        exigir(not any(c in self.etiqueta for c in '\\/:*?"<>|') and ".." not in self.etiqueta,
               f"etiqueta no puede contener separadores ni caracteres reservados: {self.etiqueta!r}")
        try:
            from .particion import validar_spec
            validar_spec(self.particion)
        except ErrorConfiguracion as x:
            e.append(str(x))
        if e:
            raise ErrorConfiguracion("Parámetros inválidos:\n  - " + "\n  - ".join(e))

    # --------------------------------------------------------------- derivados
    @property
    def es_interno(self) -> Callable[[str], bool]:
        return es_interno_por_prefijos(self.internos, self.externos)

    def a_dict(self) -> dict:
        return json.loads(json.dumps(asdict(self), default=str))

    def huella(self, campos=None) -> str:
        d = self.a_dict()
        d = {k: d[k] for k in (campos or d)}
        return hashlib.sha1(json.dumps(d, sort_keys=True).encode()).hexdigest()[:8]

    def diferencias(self) -> dict:
        """Parámetros que cambian los resultados y difieren de los valores por defecto."""
        actual, base = self.a_dict(), Parametros(dataset=self.dataset).a_dict()
        return {k: v for k, v in actual.items()
                if k not in self._NEUTROS + ("dataset", "dt", "encubrimiento") and v != base[k]}

    def carpeta(self) -> Path:
        """results/<dataset>/<etiqueta>. Sin etiqueta: dt<dt>_<encubrimiento>, más una huella
        si algún otro parámetro difiere del valor por defecto (así no se pisan resultados)."""
        if self.etiqueta:
            nombre = self.etiqueta
        else:
            nombre = f"dt{self.dt}_{self.encubrimiento}"
            dif = self.diferencias()
            if dif:
                nombre += "_" + hashlib.sha1(json.dumps(dif, sort_keys=True).encode()).hexdigest()[:8]
        return RESULTADOS / self.dataset / nombre

    def a_toml(self) -> str:
        """Parámetros efectivos como TOML (sirve de plantilla para --config)."""
        d, base = self.a_dict(), Parametros(dataset=self.dataset).a_dict()
        lineas = ["# Parámetros de un experimento. Las líneas comentadas tienen el valor por defecto:",
                  "# descoméntalas para cambiarlas. Uso: python -m apthmm ejecutar --config <archivo>",
                  f'dataset = "{self.dataset}"', f'etiqueta = "{self.etiqueta}"']
        secciones: dict[str, list] = {}
        for f in fields(self):
            s = f.metadata.get("seccion")
            if s and s != "general":
                secciones.setdefault(s, []).append(f)
        for s, fs in secciones.items():
            lineas += ["", f"[{s}]"]
            for f in fs:
                lineas.append(f"# {f.metadata['ayuda']}")
                prefijo = "" if d[f.name] != base[f.name] else "# "
                lineas.append(f"{prefijo}{f.name} = {_valor_toml(d[f.name], f.metadata['tipo'])}")
        return "\n".join(lineas) + "\n"


def _valor_toml(v, tipo: str) -> str:
    if tipo == "tupla_prof":
        v = [0 if p is None else p for p in v]
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {_valor_toml(x, '')}" for k, x in v.items()) + " }"
    return json.dumps(v, ensure_ascii=False)


def _convertir(nombre: str, tipo: str, v):
    """Normaliza el tipo de un parámetro y explica el error si no se puede."""
    try:
        if v is None:
            return None
        if tipo in ("int", "float") and isinstance(v, bool):
            raise TypeError
        if tipo == "int":
            if float(v) != int(v):
                raise ValueError
            return int(v)
        if tipo == "float":
            return float(v)
        if tipo == "str":
            return str(v)
        if tipo == "lista_str":
            if isinstance(v, str):
                v = [v]
            return [str(x) for x in v]
        if tipo == "tupla_float":
            return tuple(float(x) for x in (v if isinstance(v, (list, tuple)) else [v]))
        if tipo == "tupla_int":
            return tuple(_convertir(nombre, "int", x) for x in (v if isinstance(v, (list, tuple)) else [v]))
        if tipo == "tupla_prof":
            v = v if isinstance(v, (list, tuple)) else [v]
            return tuple(None if x in (None, 0, "none", "None") else _convertir(nombre, "int", x) for x in v)
        if tipo == "dict":
            if not isinstance(v, dict):
                raise TypeError
            return copy.deepcopy(v)
    except (TypeError, ValueError):
        raise ErrorConfiguracion(f"Valor inválido para {nombre} (se esperaba {tipo}): {v!r}") from None
    return v


def leer_toml(archivo: str | Path) -> dict:
    """Lee un archivo de experimento. Las secciones son opcionales y se aplanan."""
    ruta = Path(archivo)
    if not ruta.exists():
        raise ErrorConfiguracion(f"No existe el archivo de configuración: {ruta}")
    try:
        crudo = tomllib.loads(ruta.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as x:
        raise ErrorConfiguracion(f"{ruta}: TOML mal formado ({x})") from None
    secciones = {f.metadata["seccion"]: set() for f in fields(Parametros) if "seccion" in f.metadata}
    for f in fields(Parametros):
        if "seccion" in f.metadata:
            secciones[f.metadata["seccion"]].add(f.name)
    plano: dict[str, Any] = {}
    for k, v in crudo.items():
        if k in secciones and isinstance(v, dict) and k != "general":
            ajenos = set(v) - secciones[k]
            if ajenos:
                raise ErrorConfiguracion(f"{ruta}: [{k}] no admite {sorted(ajenos)}. Admite: {sorted(secciones[k])}")
            plano.update(v)
        else:
            plano[k] = v
    return plano

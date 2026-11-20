# Motor HMM (`src/apthmm`)

Implementa el diseño del cap. 8 del informe con las decisiones de
`docs/plan_experimentacion.md`.

## Instalación (una vez)

```
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

VS Code toma `.venv` como intérprete (`.vscode/settings.json`). Las pruebas aparecen en
la vista Testing y los experimentos en "Ejecutar y depurar" (`.vscode/launch.json`).

## Uso

```
python -m apthmm listar                                   # nombres de las 31 configuraciones
python -m apthmm preparar --dataset dapt                  # carga, ventanas y particiones
python -m apthmm ejecutar --dataset dapt                  # todas (H0, H1, H2, B1, B2)
python -m apthmm ejecutar --dataset unraveled --solo "H1-*" B1-RF-continuo-ctx-pesos
python -m apthmm ejecutar --dataset unraveled --continuar # retoma una corrida interrumpida
python -m apthmm ejecutar --config configs/sens_dt900.toml --grupos H
python -m apthmm resumen  --dataset unraveled
python -m apthmm graficar --dataset unraveled
```

Códigos de salida: 0 bien, 1 alguna configuración falló, 2 error de configuración o de
datos, 130 interrumpido.

## Parámetros

Todo lo ajustable está en `Parametros` (`config.py`). Prioridad: opciones de la línea de
comandos, luego el archivo `--config`, luego los valores del conjunto de datos y por último
los valores por defecto del plan.

```
python -m apthmm parametros --dataset unraveled                       # valores efectivos
python -m apthmm parametros --dataset unraveled --guardar configs/mio.toml
```

La plantilla deja comentados los valores por defecto. Secciones: `[datos]` (ruta, prefijos
de IP internas, `min_flujos`, partición), `[ventanas]` (`dt`, `max_hueco`, encubrimiento,
cortes), `[hmm]` (suavizados, EM, H0, remuestreo), `[base]` (k, árboles, profundidades,
SMOTE, núcleos) y `[evaluacion]` (`fpr`, `hueco_episodio`, `evaluar_en`, semilla).

En `configs/` están las sensibilidades de la Fase 3 (Δt de 1 y 15 min, terciles, p95,
encubrimiento excluido). Usan `evaluar_en = "validacion"`, como pide el plan, para no
elegir la configuración mirando la prueba.

## Carpetas de resultados

`results/<dataset>/<carpeta>/`, donde `<carpeta>` es `--etiqueta` o, si no se da,
`dt<dt>_<encubrimiento>` más una huella de 8 caracteres cuando algún otro parámetro difiere
del valor por defecto. Así dos experimentos distintos no se pisan. Cada carpeta guarda:

| Archivo | Contenido |
|---|---|
| `parametros.json` | Parámetros con que se corrió. Si no coinciden, se detiene (salvo `--forzar`) |
| `registro.log` | Registro completo, con la traza de cada error |
| `errores.json` | Configuraciones que fallaron y el motivo (se borra cuando todas pasan) |
| `resumen.csv` | Una fila por configuración |
| `<config>/metricas.json` | Métricas por etapa, detección temprana, τ y diagnóstico del modelo |
| `<config>/predicciones.parquet` | Probabilidades y predicción por ventana |
| `<config>/curva_ttd_fpr.csv` | Curva TTD vs. FPR |
| `<config>/modelo.npz` | A, B y π (solo HMM) |

## Robustez

- Un fallo en una configuración queda registrado y el lote sigue con la siguiente
  (`--detener-en-error` para depurar). `--continuar` salta las que ya terminaron.
- Los parámetros se validan antes de leer datos. Los errores esperables (ruta inexistente,
  columnas faltantes, partición vacía, TOML mal escrito) se informan en una línea, sin traza.
- Las cachés de `data/cache/` se rehacen solas si cambian los CSV de origen o los parámetros
  que definen las ventanas. `--rehacer-cache` las fuerza.
- Los JSON se escriben de forma atómica y sin `NaN` (quedan como `null`).
- El filtrado no divide por cero ante un símbolo imposible. Baum-Welch y H0 se detienen o
  descartan el reinicio si producen parámetros no finitos. Si SMOTE falla, se entrena sin él
  y queda `smote_aplicado = false` en `metricas.json`.

## Módulos

| Módulo | Qué hace |
|---|---|
| `config.py` | Constantes, conjuntos de datos y `Parametros` (validación, TOML, carpeta de salida) |
| `errores.py` | `ErrorConfiguracion` y `ErrorDatos` |
| `datos.py` | Carga DAPT2020 (incluido el archivo sin encabezado) y Unraveled (repara las filas con comas en `user_agent`) a un formato común |
| `ventanas.py` | Ventanas Δt por host interno, 4 atributos y etiqueta por etapa más avanzada |
| `particion.py` | Partición cronológica (Unraveled) o dentro de cada día (DAPT2020) y corte en secuencias |
| `discretizacion.py` | Cortes por percentiles ajustados en entrenamiento (p50/p95 = 82 símbolos) |
| `hmm.py` | Estimación por conteo, ceros estructurales, filtrado, Viterbi, Baum-Welch restringido (hmmlearn), control no supervisado + algoritmo húngaro |
| `baseline.py` | RF y XGBoost con o sin k ventanas previas, pesos de clase y SMOTE |
| `metricas.py` | F1 por etapa, episodios, TTD, precocidad, detección previa a la exfiltración, retardo por etapa y curva TTD-FPR |
| `experimentos.py` | Orquesta la Tabla 8.4, captura errores por configuración y guarda los resultados |

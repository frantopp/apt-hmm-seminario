# Plan de experimentación (Proyecto de Título 2027)

Decisiones que el Informe Final (cap. 8) deja abiertas, tomadas a partir de una
exploración de los datos locales (20-nov-2026), y plan de trabajo alineado con la
Carta Gantt 2027 (Figura 7.2). Lo que ya está decidido en el informe no se repite aquí.

## 1. Lo que muestran los datos

Recuento propio sobre `data/dapt2020/csv` y `data/unraveled/data/network-flows`.

**DAPT2020**
- Hay un solo host víctima principal, 192.168.3.29, que recorre todas las etapas.
  El movimiento lateral va de 192.168.3.29 hacia 192.168.3.30 (2.303 flujos) y
  192.168.3.34. En total hay 6 hosts internos con al menos 100 flujos.
- Los atacantes usan al menos 8 IP externas distintas (206.207.50.50, 184.98.36.245,
  209.147.138.x, 72.201.228.135).
- `enp0s3-pvt-thursday.pcap_Flow.csv` no trae fila de encabezado y contiene 2.314 de los
  2.451 flujos de movimiento lateral. Las etiquetas benignas vienen como `Benign` y
  `BENIGN`. (Un primer recuento que omitió ese archivo daba solo 137 flujos de lateral.)
- Con ventanas de 5 min y la partición D3 quedan, por etapa, en entrenamiento /
  validación / prueba: reconocimiento 18/3/7, foothold 33/11/9, lateral 36/26/30,
  exfiltración 5/1/4 ventanas.
- Mediana de 39 flujos por ventana de 5 min en el host víctima (percentil 10: 13). Con
  1 min la mediana baja a 8 y el percentil 10 a 1.

**Unraveled**
- 46 hosts internos con más de 1.000 flujos. Las IP 10.8.10.x son infraestructura del
  atacante: 10.8.10.84 es el extremo externo de todos los flujos de foothold, lateral y
  exfiltración del grupo APT, y 10.8.10.87 origina los 34.109 flujos de reconocimiento
  del aficionado.
- Solo 5 hosts internos tienen flujos maliciosos, en 79 host-días atacados:

| Host | Papel en la campaña | Días |
|---|---|---|
| 10.1.3.8 | Foothold continuo (unos 2.880 flujos diarios hacia 10.8.10.84), algo de lateral y exfiltración | 26-may a 2-jul |
| 192.168.0.11 | Lateral (hasta 4.289 flujos diarios), blanco del reconocimiento APT y del aficionado | 3-jun a 2-jul |
| 10.1.3.17 | Exfiltración y encubrimiento | 25-jun a 6-jul |
| 10.1.5.21 | Lateral de baja intensidad y exfiltración | 26-may a 6-jul |
| 10.1.4.16 | Blanco del reconocimiento del aficionado | 27-jun a 30-jun |

- **Cada host cumple casi siempre un solo papel.** La progresión
  reconocimiento → foothold → lateral → exfiltración se ve en la red completa, no dentro
  de un mismo host. En DAPT2020, en cambio, el host 192.168.3.29 sí recorre las etapas.
- Hay 13.169 filas con un número de columnas distinto al del encabezado. Coincide con
  la suma de las 1.493 filas mal formadas y las 11.676 con etiqueta "Normal" del recuento
  anterior, por lo que probablemente son la misma anomalía.

## 2. Decisiones

### D1. Unidad de secuencia: host interno, continuo dentro de cada partición
- Una secuencia es la actividad de **un host interno** (DAPT2020: 192.168.3.x,
  Unraveled: 10.1.x.x y 192.168.0.x) a lo largo de todo un periodo de la partición, sin
  reiniciar la inferencia cada día.
- Cada flujo se asigna a su extremo interno. Si ambos extremos son internos, se asigna
  a los dos. Las IP externas no forman secuencias.
- En Unraveled se usan los 46 hosts con más de 1.000 flujos.

**Por qué.** La alerta que sirve a un analista dice qué equipo propio está
comprometido. Las IP del atacante cambian (8 distintas en DAPT2020) y fragmentarían
las secuencias. No se reinicia cada día porque el foothold de 10.1.3.8 dura 11 días
seguidos: un reinicio diario mediría cuánto tarda el modelo en reconocer una etapa ya
en curso, no la detección del inicio del ataque.

### D2. Episodio de ataque para las métricas de detección temprana
- El conjunto C del informe se define por **episodios**: tramos de un host con ventanas
  maliciosas separados por al menos 6 horas sin actividad maliciosa.
- Se reportan los valores de cada episodio además de la mediana, porque habrá pocos.

**Por qué.** Con 5 hosts atacados, "una secuencia atacada por host" deja menos de 5
casos de prueba. El corte de 6 horas separa las jornadas de actividad del atacante sin
partir una etapa continua como el foothold.

### D3. Partición
- **Unraveled, cronológica por días:** entrenamiento del 26-may al 26-jun, validación
  del 27 al 29-jun y prueba del 30-jun al 6-jul.
  - Entrenamiento: lateral, reconocimiento APT, foothold (22 a 26-jun) y exfiltración
    (21 a 26-jun).
  - Validación y prueba: las cuatro etapas, con el reconocimiento del aficionado. El
    encubrimiento queda en prueba (2-jul).
- **Robustez en Unraveled:** validación cruzada agrupada por día (5 pliegues,
  estratificada por la etapa más avanzada de cada día), como resultado secundario.
- **DAPT2020, cronológica dentro de cada día:** los primeros 60 % del tiempo de cada
  captura van a entrenamiento, el 20 % siguiente a validación y el último 20 % a prueba,
  con una ventana de separación entre tramos.

**Por qué.** En Unraveled el corte cronológico es posible porque todas las etapas
aparecen en las tres particiones, y reproduce el uso real: entrenar con el pasado y
detectar en el futuro. Tiene una consecuencia que hay que reportar: el reconocimiento
de entrenamiento es solo del grupo APT y el de prueba es solo del aficionado, así que
esa etapa mide generalización entre atacantes. La validación cruzada por día controla
que el resultado no dependa de un único corte. En DAPT2020 un corte entre días dejaría
etapas completas fuera del entrenamiento, porque cada etapa ocurre en un día distinto.
Por eso se corta dentro de cada día. Esto confirma que DAPT2020 es solo comparativo,
como ya dice el informe.

### D4. Ventana Δt = 5 minutos, sin solapamiento
Sensibilidad con 1 y 15 minutos, evaluada solo en validación (Fase 3).

**Por qué.** Con 5 min el host víctima de DAPT2020 tiene una mediana de 39 flujos por
ventana, suficiente para que las estadísticas sean estables. Con 1 min el 10 % de las
ventanas tiene un solo flujo. Con 15 min se pierden ventanas de exfiltración, que ya son
pocas, y aumentan las ventanas con dos etapas. Además,
5 min fija la resolución del TTD en un valor razonable para un SOC.

### D5. Etiqueta de la ventana: etapa más avanzada
Orden: reconocimiento < foothold < lateral < exfiltración. Se mantiene la regla del
informe y la regla mayoritaria queda como sensibilidad.

**Por qué.** Con 5 min no hay ventanas mixtas en DAPT2020, así que la regla casi no
cambia nada allí. La etapa más avanzada es la conservadora: no rebaja una ventana que
ya contiene exfiltración.

### D6. Cuatro atributos por ventana y host
| Atributo | Cálculo | Etapa que busca capturar |
|---|---|---|
| A1 Volumen saliente | log(1 + bytes enviados por el host) | Exfiltración, comando y control |
| A2 Duración | Mediana de la duración de los flujos | Foothold (conexiones persistentes) frente a escaneo (cortas) |
| A3 Dispersión de puertos | Número de puertos de destino distintos | Reconocimiento |
| A4 Conexiones fallidas | Proporción de flujos sin respuesta o con RST | Reconocimiento, intentos de lateral |

Las dos herramientas de extracción tienen equivalentes directos:
- **A1:** CICFlowMeter usa `Total Length of Fwd/Bwd Packet` y NFStream usa
  `src2dst_bytes`/`dst2src_bytes`, según el sentido.
- **A2:** `Flow Duration` y `bidirectional_duration_ms`.
- **A3:** `Dst Port` y `dst_port`.
- **A4:** `Total Bwd packets = 0` o `RST Flag Count > 0`, y
  `dst2src_packets = 0` o `bidirectional_rst_packets > 0`.

**Por qué.** Son los cuatro atributos que nombra el informe (tasa de bytes, duración,
puertos y flags TCP). Cada uno apunta a una etapa distinta, y existen en ambos datasets,
algo necesario para aplicar el mismo modelo a los dos.

### D7. Símbolos: 3 niveles por atributo con cortes en p50 y p95
- Cada atributo se discretiza en bajo (≤ p50), medio (p50 a p95) y alto (> p95).
  Los percentiles se calculan sobre las ventanas de entrenamiento con actividad.
- El símbolo es la combinación de los cuatro niveles: 3⁴ = 81 símbolos, más un símbolo
  "sin actividad". M = 82.
- Sensibilidad: 2 niveles (corte en p95, M = 17) y terciles.

**Por qué.** Se mantiene la cuantización por intervalos del informe, que da símbolos
legibles ("volumen alto, muchos puertos, muchas conexiones fallidas"). Esa
interpretabilidad es parte del aporte que defiende la segunda hipótesis. Los cortes en
p50 y p95 se eligen porque el tráfico benigno es el 98,6 % de Unraveled: con terciles,
casi todas las ventanas de ataque caerían en el mismo nivel alto. El p95 aísla la cola
atípica, que es donde vive el ataque. Se descartó k-means porque cambia lo que dice el
informe y pierde la lectura directa de los símbolos.

### D8. Suavizado aditivo con α ajustado en validación
α ∈ {0,01; 0,1; 1}, donde α = 1 es el suavizado de Laplace del informe.

**Por qué.** Con 82 columnas y 6 ventanas de exfiltración en DAPT2020, Laplace con
α = 1 suma 82 pseudoconteos a 6 observaciones. La fila de B de ese estado quedaría casi
uniforme, con más del 85 % de su masa en símbolos que nunca se vieron
(al menos 76 de 88 pseudoconteos). Ajustar α
conserva la idea del informe sin borrar la señal de los estados con pocos datos.

### D9. Ceros estructurales en A
Se fija en cero una transición **entre dos estados de ataque** que no aparece en
entrenamiento. Las transiciones desde y hacia benigno siempre se permiten, con
suavizado.

**Por qué.** En una secuencia por host el ataque alterna con periodos benignos: el host
vuelve a benigno y retoma en cualquier etapa. Prohibir esas transiciones bloquearía
casos reales. Unraveled además muestra órdenes no lineales (exfiltración antes del
lateral). Por eso solo se cierra lo que es a la vez inobservado y un salto directo
entre etapas de ataque.

### D10. Baum-Welch restringido (H2) y control no supervisado (H0)
- **H2:** se inicializa con H1, con un máximo de 50 iteraciones. Se detiene cuando la
  log-verosimilitud en validación baja dos iteraciones seguidas.
- **H0:** 10 reinicios aleatorios con semillas fijas, y se queda el de mayor
  verosimilitud en entrenamiento. Los estados se asignan a las etapas con el algoritmo
  húngaro (`scipy.optimize.linear_sum_assignment`).

**Por qué.** La detención temprana en validación es el control de deriva semántica que
pide el informe. Los reinicios evitan juzgar a H0 por un mal máximo local, para que la
comparación con el anclaje sea justa.

### D11. Remuestreo por secuencia (HMM)
- En entrenamiento se submuestrean tramos benignos de 6 horas sin ataque hasta una razón
  1:2 entre ventanas atacadas y benignas.
- Las secuencias con ataque no se tocan.

**Por qué.** En la estimación por conteo, las filas de B de los estados de ataque solo
usan ventanas de ataque, así que el remuestreo no las cambia. Lo que cambia es la
frecuencia de benigno → ataque en A, es decir, la probabilidad a priori de un ataque.
Por eso se espera que esta condición se comporte de forma parecida a mover el umbral, y
eso mismo es un resultado que vale la pena mostrar. En H2 sí puede cambiar más, porque
Baum-Welch reestima todo.

### D12. Puntos de operación del umbral τ
- **Resultado principal:** la curva TTD vs. tasa de falsas alarmas completa.
- **Puntos fijos:** 1 % de ventanas benignas en DAPT2020 y 0,1 % en Unraveled.

**Por qué.** La curva evita elegir un umbral favorable. Con ventanas de 5 min, un host
tiene 288 ventanas al día: 0,1 % equivale a unas 0,3 falsas alarmas por host al día, una
carga manejable para 46 hosts. En DAPT2020 hay unas 440 ventanas benignas del host
víctima, y 0,1 % sería menos de una ventana, imposible de medir. Por eso allí se usa 1 %.

### D13. Modelos de referencia
- **Random Forest:** 500 árboles. **XGBoost:** con `tree_method="hist"`.
- Ambos con una grilla pequeña de profundidad y número de estimadores, ajustada en
  validación.
- k ventanas previas ∈ {1, 3, 6}, elegido en validación.
- SMOTE con `k_neighbors = min(5, n_minoritaria − 1)`.

**Por qué.** Elegir k en validación le da a la línea base su mejor memoria corta, así
que una ventaja del HMM no se puede atribuir a una línea base débil. El ajuste de SMOTE
es obligatorio: la exfiltración de DAPT2020 tiene menos de 6 ventanas en entrenamiento
y SMOTE falla con el valor por defecto.

### D14. Limpieza
- DAPT2020: leer `pvt-thursday` con el encabezado de los otros archivos y unificar
  `BENIGN` como `Benign`.
- Unraveled: leer cada archivo con su propio encabezado, revisar las 13.169 filas con
  columnas de más o de menos, y documentar si se reparan o se excluyen.
- Encubrimiento → exfiltración, con la variante que lo excluye. Pivoting no existe en
  la versión local de DAPT2020, así que no aplica.

### D15. Herramientas
- Entorno virtual con Python 3.13 (el instalado; todas las librerías tienen versión
  compatible): pandas + pyarrow, numpy, scipy, scikit-learn,
  xgboost, imbalanced-learn, hmmlearn.
- Unraveled se convierte una vez a Parquet.
- El HMM se implementa a mano en numpy (conteo, forward escalado, Viterbi y Baum-Welch
  con ceros fijos). hmmlearn se usa solo para verificar.

**Por qué.** hmmlearn no hace la estimación supervisada por conteo ni expone la
probabilidad filtrada paso a paso como la necesita la alerta en línea. Implementarlo es
poco código y es parte del OE4. Baum-Welch sí se delega en hmmlearn (código en C), con
priors que conservan los ceros estructurales.

## 3. Plan de trabajo

Alineado con la Gantt 2027 (Desarrollo 8-mar a 19-abr, Validación 19-abr a 27-jun,
Cierre hasta el 5-jul).

| Fase | Fechas | Tareas | Entregable |
|---|---|---|---|
| 0 (opcional) | dic-2026 a feb-2027 | Entorno, conversión a Parquet, limpieza (D14), ventaneo (D1, D4) | Ventanas por host de ambos datasets |
| 1 Refinar arquitectura y diseñar plan | 8-mar a 4-abr | Revisar este documento con el profesor guía, fijar semillas y particiones (D3) | Protocolo congelado |
| 2 Implementación | 5-abr a 18-abr | `src/`: datos, ventanas, discretización, hmm, baseline, métricas, experimentos, con pruebas unitarias | H1 corriendo de punta a punta en DAPT2020 (Informe de Avance) |
| 3 Pruebas de sistema | 19-abr a 23-may | Sensibilidad de Δt, etiqueta, niveles y α en validación. H1 vs. H2 vs. H0. Encubrimiento asignado vs. excluido | Configuración congelada |
| 4 Pruebas de métricas | 24-may a 13-jun | Matriz completa en prueba, curvas TTD-FPR, análisis por grupo atacante, validación cruzada por día | Tablas y figuras |
| 5 Análisis y conclusiones | 14-jun a 27-jun | Contraste de las dos hipótesis, redacción | Informe Final (~25-jun) |

**Pruebas unitarias mínimas (Fase 2):**
- Forward contra fuerza bruta en un HMM de 2 estados y 3 pasos.
- Baum-Welch conserva los ceros.
- La discretización no usa datos de validación ni de prueba.
- Las métricas de detección temprana dan el valor esperado en secuencias sintéticas.

**Matriz de la Fase 4, por dataset:**
- HMM: H1 y H2 × 3 condiciones de desbalance, más H0 = 7 configuraciones.
- Línea base: (RF, XGB) × (continuo, discreto) × (con o sin contexto) × 3 tratamientos
  = 24 configuraciones.

## 4. Riesgos

| Riesgo | Qué se hace |
|---|---|
| En Unraveled cada host cumple casi siempre un solo papel, así que la progresión entre etapas casi no se observa dentro de un host. La primera hipótesis puede no sostenerse por host | Se reporta tal cual. Como análisis adicional, se combinan las probabilidades filtradas de todos los hosts (máximo por ventana) para obtener una línea de tiempo de la campaña a nivel de red |
| Pocos episodios atacados en prueba | Valores individuales además de la mediana, más la validación cruzada por día |
| Reconocimiento de entrenamiento solo APT y de prueba solo aficionado | Se presenta como prueba de generalización entre atacantes, por grupo |
| Exfiltración de DAPT2020 con 6 ventanas | α ajustado (D8). Si la prueba tiene menos de 3 ventanas, la etapa se marca como no evaluable en DAPT2020 |
| La Gantt da solo 2 semanas a la implementación | Fase 0 opcional. Si no se hace, se toma una semana de las Pruebas de sistema |

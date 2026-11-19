# Contexto del proyecto — Seminario de Título (apt-hmm-seminario)

> Documento de traspaso para Claude Code. Resume todo lo que existe del proyecto fuera de
> este repo (proyecto "Seminario" en claude.ai, reglamento, rúbrica, decisiones tomadas) y
> cómo está organizado el repo. Responde siempre en **español**.

## 1. Quién y qué

- **Autora:** Francisca Antonia Abarca Pezo (Fran), Ingeniería Civil Informática, PUCV.
- **Profesor guía:** Sebastián Berríos. **Profesora correferente:** Pamela Hermosilla
  (Escuela de Ingeniería Informática, PUCV).
- **Título:** *Modelos Probabilísticos para la Detección de Amenazas Persistentes Avanzadas (APT)*.
  El tema viene de una lista propuesta por el profesor y **ya no se puede cambiar**.
- **Repo:** `github.com/frantopp/apt-hmm-seminario` (privado). Local:
  `F:\Universidad\Proyectos\Seminario\apt-hmm-seminario` (Windows, VS Code, MiKTeX).
- **Venue de publicación objetivo:** *Mathematics* (MDPI).

## 2. Asignaturas y fechas

El proyecto abarca dos semestres:

| Etapa | Período | Hitos |
|---|---|---|
| **Seminario de Título** | 3 ago – nov 2026 | Informe de Avance 11-sep · Presentación de Avance 14-sep · **Informe Final 20-nov** · **Presentación Final 30-nov** |
| **Proyecto de Título** | mar – jul 2027 (estimado; calendario 2027 aún no publicado) | Implementación, experimentos, informe definitivo |

**Reglamento Seminario de Título (marzo 2026), lo esencial:**
- Objetivo: desarrollar un trabajo que dé origen a una **propuesta de proyecto de titulación**.
- Evaluación: Avance 30 % (informe 15 % + presentación 15 %); Final 70 % (**informe 30 %** +
  **presentación 40 %**). Nota < 3,0 en el avance o < 4,0 en el final ⇒ reprobación (RA).
  No presentarse a una instancia ⇒ RA.
- Comisión: profesor guía + correferente. Los informes siguen el formato de la Escuela
  (plantilla `pucv_inf_2024`).
- El profesor guía pidió: SLR como base de la investigación + desarrollo práctico que
  aplique y valide lo aprendido, con **avances cada dos semanas**, y un plan de trabajo
  completo de dos semestres (Gantt).

**Rúbrica de informes escritos (ICI/INF):** Contenido 40 % (introducción, objetivos, marco
teórico actualizado, metodología, propuesta, conclusiones) · Resumen 10 % · Estructura 10 % ·
Presentación 10 % (índices, figuras, tablas, normas) · Redacción y estilo 10 % · Citas y
referencias 10 % · Contribución 10 %.

## 3. Decisiones de investigación tomadas (no reabrir sin que Fran lo pida)

- **Modelo:** Cadenas/Modelos Ocultos de Markov (**HMM**), modelo generativo λ = (A, B, π).
  - Estados ocultos: S = {benigno, reconocimiento, foothold, lateral, exfiltración}.
  - Observables: características estadísticas del **flujo de red** (tasa de bytes, duración,
    distribución de puertos, flags TCP), agregadas por host/sesión en ventanas Δt y
    discretizadas por intervalos → alfabeto V = {v1…vM}.
  - Entrenamiento con **Baum-Welch** (EM); inferencia con **Viterbi**.
  - Salida: secuencia de etapas más probable Q*, confianza de la etapa actual y probabilidad
    de transición a la siguiente fase.
- **Datos:** estrategia dual — **DAPT2020** (comparabilidad con la literatura) y
  **Unraveled** (seis semanas de emulación organizacional, más actual y realista; lo pidió el
  profesor guía). Ambos del mismo grupo (Arizona State University), con etapas etiquetadas.
- **Desbalance:** evaluar con métricas por etapa (**F1, recall, precision**), no accuracy
  global; contrastar datos originales vs. **SMOTE**.
- **Metodología:** **Design Science Research** (Peffers et al., 2007) como marco general;
  SLR según **Kitchenham & Charters (2007)**, reportada con **PRISMA 2020**. SLR gestionada
  con Rayyan y Zotero.
- **Objetivos** (tres dimensiones, como en el informe de ejemplo del profesor):
  - *Estudio:* OE1 SLR · OE2 marco formal de estados ocultos y observables.
  - *Desarrollo:* OE3 arquitectura HMM (componentes, Baum-Welch/Viterbi, flujo de datos) ·
    OE4 prototipo funcional que infiere la progresión de la APT con probabilidades.
  - *Validación:* OE5 experimentos sobre DAPT2020 y Unraveled, métricas por etapa, efecto del
    desbalance y comparación con la literatura.
  - Objetivo general: *Desarrollar un modelo probabilístico basado en HMM que permita detectar
    APT mediante la identificación temprana de su progresión por etapas.*

## 4. Revisión sistemática (ya ejecutada)

- **RQ1** modelos probabilísticos aplicados a APT · **RQ2** HMM aplicados a APT y sus variantes ·
  **RQ3** datasets y sus limitaciones · **RQ4** estrategias contra el desbalance de clases.
  Formuladas con PICOC; criterios CI-1…CI-8 y CE-1…CE-8 (CI-4: desde 2011, salvo RQ4).
- Fuentes: Scopus, Web of Science, IEEE Xplore. **1.076** registros (556 / 267 / 253) →
  **603** tras duplicados → 292 a texto completo → 199 excluidos por falta de acceso (CE-6)
  y 10 fuera de dominio (CE-1) → **corpus final de 83 estudios** (74 revistas, 9 conferencias;
  IEEE Access lidera con 18).
- En texto completo: 32 estudios mencionan modelos de Markov (19 HMM específicamente);
  9 usan DAPT2020 y 9 Unraveled; 41 abordan el desbalance de clases.
- **Cuatro brechas** (→ decisión de diseño):
  1. Los modelos probabilísticos operan sobre alertas o grafos ya correlacionados →
     el modelo opera **directo sobre tráfico de red**.
  2. Los HMM definen observables a partir de alertas de terceros → observables desde
     **estadísticas de flujo**, estados = fases etiquetadas.
  3. Sin benchmark consolidado y baja representatividad temporal → **DAPT2020 + Unraveled**.
  4. ~70 % evalúa con accuracy global → **métricas por etapa** + contraste con SMOTE.
- En el proyecto de claude.ai (no en el repo) están: `SLR.ris` (exportación de la SLR) y
  `cribado_preclasificadov2*.xlsx` (planilla de cribado). Si los necesitas, pídeselos a Fran.

## 5. El repo

```
informe/            Informe LaTeX (plantilla pucv_inf_2024). Hoy contiene el Informe de Avance.
  main.tex          Documento raíz; \include de Portadas/ y seccion/
  .latexmkrc        biber + makeglossaries + crea subcarpetas en build/ (no tocar sin motivo)
  pucv_inf_2024.sty Estilo de la Escuela (biblatex style=apa, backend=biber; glossaries; Times)
  referencias.bib   ~95 entradas (Zotero)
  Portadas/         portada_TFT_nofinal.tex (la que se usa), portada_TFT_final.tex, portada_principal.tex
  seccion/          1-Introduccion … 10-Ia, Resumen/, Dedicatoria/, Simbolos/
  assets/           CartaGantt1.png (seminario), CartaGantt2.png (proyecto 2027)
src/ notebooks/     Código del HMM y experimentos (vacíos por ahora)
data/               Datasets locales, NO versionados (data/dapt2020/, data/unraveled/)
docs/               CONTEXTO.md (este archivo) y referencia/ (reglamento, rúbrica, ejemplos)
build/              PDF compilado, NO versionado
CLAUDE.md           Lo carga Claude Code al abrir el repo; importa docs/CONTEXTO.md
Makefile            make / make watch / make clean
.claude/commands/   /start y /cierre (estado entre sesiones en .claude/sesion/, local)
```

**Capítulos actuales del informe:** Resumen/Abstract · 1 Introducción · 2 Descripción del
Problema · 3 Objetivos · 4 Marco Teórico · 5 Metodología (DSR + SLR, diagramas TikZ, PRISMA) ·
6 Estado del Arte (gráficos pgfplots, tabla xltabular de 83 estudios, síntesis por RQ, brechas) ·
7 Plan de Trabajo (Gantt como imágenes) · 8 Propuesta de Solución · 9 Conclusión · 10 Declaración sobre el uso de herramientas de IA.

**Documentos de referencia en `docs/referencia/`** (léelos cuando la tarea lo requiera):

| Archivo | Qué es |
|---|---|
| `reglamento-seminario-titulo-2026.pdf` | Reglamento interno del Seminario de Título (marzo 2026) |
| `rubrica-informes-escritos.pdf` | Rúbrica oficial de informes escritos ICI/INF (ver sección 2) |
| `ejemplo-informe-final-seminario.pdf` | Informe Final de Seminario de otro grupo (jun. 2026, 92 págs.; guía Hermosilla, correferente Berríos): agente LLM para análisis de logs |
| `ejemplo-presentacion-final-seminario.pdf` | Presentación Final del mismo grupo (39 diapositivas, plantilla PUCV) |

Los ejemplos son de **otro proyecto**: úsalos como modelo de estructura, extensión y nivel
de detalle, nunca como fuente de contenido. El informe de ejemplo agrega en la Propuesta:
arquitectura general con diagrama, componentes, tecnologías consideradas (tablas),
requerimientos de hardware/software, datasets de evaluación, diseño experimental con
métricas, alcance y limitaciones. La presentación sigue: Introducción → Objetivos →
Metodología (RQ, criterios, selección, categorías) → Estado del Arte → Propuesta
(descripción, arquitectura, diseño, limitaciones) → Conclusión.

## 6. Cómo trabajar en este repo

- **Compilar:** `make` (desde la raíz; Git Bash o PowerShell) → `build/informe/main.pdf`.
  `make watch` recompila al guardar; `make clean` si latexmk queda en mal estado.
  Toolchain: MiKTeX + latexmk + biber + Strawberry Perl + GNU Make (scoop).
- **No uses `pdflatex` suelto**: los `\include{Portadas/...}` fallan sin las subcarpetas que
  crea `.latexmkrc` en `build/`.
- La compilación es `-halt-on-error`: errores que Overleaf toleraba aquí detienen el build.
  Corrígelos en el `.tex` sin cambiar el resultado visual.
- Después de editar, **compila y revisa** `build/informe/main.log`: cero errores y ninguna
  cita o referencia `undefined`.
- Convenciones de escritura: español formal; "Tabla"/"Figura"; leyendas con
  *"Fuente: Elaboración propia."*; citas con `\parencite{}` (APA vía biblatex); claves nuevas
  en `referencias.bib` sin duplicar entradas existentes; figuras en `informe/assets/`.
- No inventes cifras, citas ni resultados: todo dato del informe debe salir de la SLR, de
  `referencias.bib` o de experimentos ejecutados en el repo.
- Commits en español, descriptivos. No subas datasets ni PDFs compilados.
- Al empezar una sesión: `/start`. Al terminar: `/cierre`.

## 7. Siguiente etapa

Fran está empezando a armar en este repo la **propuesta preliminar del proyecto** (cierre del
Seminario de Título y base del Proyecto de Título), partiendo del Informe de Avance. Lo que
queda por delante, según el plan:
1. Informe Final y Presentación Final del Seminario (20-nov y 30-nov-2026).
2. Proyecto de Título (2027): implementar el preprocesamiento y el motor HMM en Python
   (`src/`), calibrar con Baum-Welch con y sin SMOTE, y evaluar por etapa sobre DAPT2020 y
   Unraveled.

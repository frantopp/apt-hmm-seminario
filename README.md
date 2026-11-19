# Modelos Probabilísticos para la Detección de Amenazas Persistentes Avanzadas (APT)

Seminario de Título — Ingeniería Civil Informática, Pontificia Universidad Católica de Valparaíso (PUCV).

- **Autora:** Francisca Abarca
- **Profesor guía:** Sebastián Berríos
- **Profesora correferente:** Pamela Hermosilla

## Resumen

Detección de las etapas de una APT a partir de tráfico de red, usando Hidden Markov Models (HMM). Las variables observables se derivan de características estadísticas de flujos de red y los estados ocultos se asocian a las fases de ataque. La evaluación usa DAPT2020 y Unraveled, con métricas desagregadas por etapa (F1-score, Recall).

## Estructura

```
informe/      Informe en LaTeX (plantilla pucv_inf_2024), base: Informe de Avance
  main.tex
  seccion/    Capítulos (Introducción … Propuesta, Conclusión)
  Portadas/   Portadas TFT
  assets/     Figuras (carta Gantt)
src/          Código del modelo (preprocesamiento, HMM, evaluación)
notebooks/    Exploración y experimentos
data/         Datasets locales (no versionados, ver data/README.md)
```

## Compilar el informe

Desde `informe/` (o subiendo la carpeta a Overleaf):

```bash
latexmk -pdf main.tex
```

Usa `biblatex` con `referencias.bib` y glosario (`makeglossaries`).

## Estado

- [x] Informe de Avance (Seminario de Título)
- [ ] Propuesta preliminar del proyecto
- [ ] Implementación del preprocesamiento y modelo HMM
- [ ] Validación experimental

# Modelos Probabilísticos para la Detección de Amenazas Persistentes Avanzadas (APT)

Seminario de Título — Ingeniería Civil Informática, Pontificia Universidad Católica de Valparaíso (PUCV).

- **Autora:** Francisca Abarca
- **Profesor guía:** Sebastián Berrios
- **Profesora correferente:** Pamela Hermosilla

## Resumen

Detección de las etapas de una APT a partir de tráfico de red, usando Hidden Markov Models (HMM). Las variables observables se derivan de características estadísticas de flujos de red y los estados ocultos se asocian a las fases de ataque. La evaluación usa DAPT2020 y Unraveled, con métricas desagregadas por etapa (F1-score, Recall).

## Estructura

```
informe/      Informe en LaTeX (plantilla pucv_inf_2024), base: Informe de Avance
  main.tex
  .latexmkrc  Configuración de compilación (biber, glosario, subcarpetas)
  seccion/    Capítulos (Introducción … Propuesta, Conclusión)
  Portadas/   Portadas TFT
  assets/     Figuras (carta Gantt)
src/          Código del modelo (preprocesamiento, HMM, evaluación)
notebooks/    Exploración y experimentos
data/         Datasets locales (no versionados, ver data/README.md)
build/        PDF compilado (no versionado)
Makefile      make / make watch / make clean
.claude/      Comandos /start y /cierre de Claude Code
.vscode/      Configuración de LaTeX Workshop
```

## Compilar el informe

Se compila igual que `portuaria-organizacion`: **latexmk** (pdfLaTeX + biber + makeglossaries), con la salida en `build/informe/main.pdf`, nunca junto a los `.tex`.

### Requisitos (Windows)

| Herramienta | Cómo | Para qué |
|---|---|---|
| MiKTeX | Instalador de MiKTeX | `pdflatex`, `latexmk`, `biber`, `makeglossaries` |
| GNU Make y Strawberry Perl | `scoop install make perl` | `make` y el Perl que necesitan `latexmk` y `makeglossaries` |
| VS Code + LaTeX Workshop | Extensión `james-yu.latex-workshop` (el repo la recomienda al abrirlo) | Compilar al guardar y ver el PDF en una pestaña |

Activa en MiKTeX la instalación automática de paquetes, para que un paquete faltante (p. ej. `biblatex-apa`) se descargue solo y no deje la compilación esperando:

```sh
initexmf --set-config-value=[MPM]AutoInstall=1
```

### Desde la terminal (Git Bash o PowerShell, en la raíz del repo)

```sh
make            # compila -> build/informe/main.pdf
make watch      # recompila cada vez que guardas (Ctrl+C para salir)
make clean      # borra auxiliares y PDF de build/informe
```

### Desde VS Code

Con LaTeX Workshop instalado, abre cualquier `.tex` de `informe/` y guarda: compila solo con la configuración de `.vscode/settings.json` (mismo `latexmk` y `informe/.latexmkrc`). El PDF se abre con *View LaTeX PDF* (Ctrl+Alt+V).

### Si algo falla

| Problema | Solución |
|---|---|
| `I can't write on file 'Portadas/...aux'` | Compila con `make` o LaTeX Workshop, no con `pdflatex` suelto: `informe/.latexmkrc` crea las subcarpetas en `build/` |
| latexmk dice que ya hubo un error y no recompila | `make clean` y vuelve a compilar |
| Error de biber (versión de `biblatex` no coincide) | Actualiza MiKTeX completo desde la consola de MiKTeX (*Updates*) |
| Citas como **[clave]** en negrita | Faltó la pasada de biber: `make clean && make` |

## Retomar el trabajo entre sesiones (Claude Code)

- `/start` — lee el estado que dejó la sesión anterior, revisa qué cambió en el repo y el estado del PDF, y propone qué sigue. Solo lectura.
- `/cierre [nota]` — escribe `.claude/sesion/ultimo_estado.md` (local, fuera de git) con lo hecho, decisiones, pendientes y siguiente paso.

## Estado

- [x] Informe de Avance (Seminario de Título)
- [ ] Propuesta preliminar del proyecto
- [ ] Implementación del preprocesamiento y modelo HMM
- [ ] Validación experimental

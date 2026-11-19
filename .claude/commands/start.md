---
description: Retoma el trabajo del seminario donde quedó la última sesión (estado, repo, compilación y plan) y propone qué sigue
---

Retoma el trabajo del Seminario de Título (detección de APT con HMM) donde lo dejó la
última sesión. Responde en español.

Este comando es **solo de lectura**: no edites archivos, no hagas commits ni push.

## 1. Estado que dejó la sesión anterior

Lee `.claude/sesion/ultimo_estado.md` completo. Si no existe, dilo y sigue con el paso 2.
Anota de ahí: fecha, rama, último commit, siguiente paso, dudas abiertas y advertencias.

## 2. Qué cambió en el repo desde entonces

- `git fetch -q origin`, `git status -sb` y la rama actual. Si hay cambios sin commitear o
  commits sin subir (`ahead`), avísalo antes que nada.
- `git log --oneline <último commit del estado>..HEAD` (o los últimos 10 si no hay estado)
  y `git log --oneline HEAD..origin/main` por si hay cambios en GitHub que no tienes local.

## 3. Estado del informe

- Si existe `build/informe/main.pdf`, compara su fecha con la del `.tex` más reciente de
  `informe/` (`git log -1 --format=%cd -- informe/`): ¿el PDF está al día?
- Si existe `build/informe/main.log`, revisa errores (`^./.*:[0-9]+:`) y advertencias de
  citas o referencias sin resolver (`undefined`). No compiles: solo informa.

## 4. Plan contra la fecha de hoy

Lee el checklist "Estado" de `README.md` y la tabla de `informe/seccion/7-Plan.tex`. Con la
fecha de hoy: qué hito o entrega viene, qué está atrasado y qué bloquea lo siguiente.

## 5. Entrega

Un resumen breve, en este orden:

1. **Dónde quedamos** (dos o tres líneas, del estado).
2. **Qué cambió desde entonces** (commits, archivos modificados, estado del PDF).
3. **Qué toca ahora**, ordenado por fecha.
4. **Dudas abiertas y riesgos**.

Termina con **una sola pregunta**: por dónde seguimos. Luego detente y espera.

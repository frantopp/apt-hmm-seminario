---
description: Deja escrito el estado de la sesión para que /start lo retome en la próxima
argument-hint: "[nota opcional sobre el siguiente paso]"
---

Cierra la sesión dejando el estado para la próxima. Responde en español.

Sobrescribe `.claude/sesion/ultimo_estado.md` (archivo local, fuera de git; crea la
carpeta si no existe) con el formato de abajo. Verifica cada dato antes de escribirlo
(`git log`, `git status -sb`, `build/informe/main.log`); no lo escribas de memoria. Máximo
unas 60 líneas: es una nota de traspaso, no un informe. Si el usuario agregó una nota
(**$ARGUMENTS**), inclúyela en "Siguiente paso".

```markdown
# Estado de la última sesión

**Fecha:** DD-MM-AAAA HH:MM · **Rama actual:** <rama> (<limpia / con cambios sin commitear>)
**Último commit:** <hash corto> <título> · **Subido a GitHub:** <sí / n commits sin push>
**Compilación:** <build/informe/main.pdf al día, N páginas, sin errores / con errores: …>

## Qué se hizo
- <cambio> (commit <hash> o archivo) …

## Decisiones tomadas
- <qué se decidió sobre el modelo, los datos, el informe o la metodología, en una línea> …

## En curso o sin terminar
- <sección a medias, rama con cambios, experimento sin terminar> …

## Siguiente paso
1. <acción concreta, con fecha si la tiene> …

## Dudas abiertas
- <duda> — para <profesor guía / correferente / revisar en la literatura> …

## Advertencias
- <archivos locales sin versionar, herramientas que fallaron, riesgos conocidos> …
```

Después muestra el archivo al usuario y recuérdale que la próxima sesión parte con
`/start`. No hagas commit: el archivo es local.

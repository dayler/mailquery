# Protocolo de los subagentes

Reglas de este plan que no están en `CLAUDE.md`. Los límites de `CLAUDE.md` valen sin cambios.

## Límites

Sin cambios respecto de `CLAUDE.md`.

Una regla de `CLAUDE.md` queda sustituida por orden del dueño (decisión D-03): el subagente no commitea su evidencia ni la escribe en `docs/plan/`; entrega los datos crudos fuera del repositorio (sección "Evidencia cruda") y el orquestador escribe `evidence/M<NN>.md`. El handoff y las propuestas sí se commitean.

## Ramas y worktrees

- Trabajas solo en el worktree y la rama que te da el orquestador (`feature/id-corto-outlook-m<NN>`). No cambias de rama, no haces merge, rebase ni push, y no creas worktrees ni ramas.
- Los commits van a tu rama, con mensajes en inglés del tipo `feat(native-ids): …`, `refactor(outlook): …`, `test(outlook): …`, `docs(readme): …`. Se permiten commits de trabajo en curso con tests rojos antes de un handoff.
- Ningún mensaje de commit, comentario, docstring ni documento atribuye nada a una herramienta o modelo.

## Comandos y logs

- **Directorio de logs:** `../mailquery-logs/id-corto-outlook/M<NN>/`, relativo a la raíz de tu worktree (los worktrees y el checkout principal están en la misma carpeta), fuera de todo checkout. Créalo si no existe. En Git Bash: `LOG=../mailquery-logs/id-corto-outlook/M<NN>; mkdir -p "$LOG"`. En PowerShell: `$LOG = "..\mailquery-logs\id-corto-outlook\M<NN>"; New-Item -ItemType Directory -Force $LOG | Out-Null`.
- **Python:** el del venv del plan. En Git Bash: `PY=../mailquery-venv-id-corto/Scripts/python` (en macOS o Linux, `bin/python`). En PowerShell: `$PY = "..\mailquery-venv-id-corto\Scripts\python.exe"`. Las rutas son relativas a la raíz de tu worktree, que está junto al checkout principal.
- **Suite completa** (siempre a log):
  - Git Bash: `$PY -B -m unittest discover -s tests -t . > "$LOG/suite.log" 2>&1; echo "exit=$?"`; resumen: `tail -n 3 "$LOG/suite.log"`; fallos: `grep -E "^(FAIL|ERROR):" "$LOG/suite.log" | head -n 40`.
  - PowerShell: `cmd /c "$PY -B -m unittest discover -s tests -t . > $LOG\suite.log 2>&1"; "exit=$LASTEXITCODE"`; resumen: `Get-Content $LOG\suite.log -Tail 3`; fallos: `Select-String -Path $LOG\suite.log -Pattern '^(FAIL|ERROR):' | Select-Object -First 40`.
- **Un grupo o un caso:** el mismo comando con `-k <id en minúsculas con _>` (por ejemplo `-k ut_nid_03`) y log propio (`grupo-<id>.log`). Un solo caso puede ir sin log.
- **Cobertura** (si `coverage` está en el venv): `$PY -B -m coverage run -m unittest discover -s tests -t . > "$LOG/cov.log" 2>&1` y `$PY -m coverage report --include="<módulos tocados>" | tail -n 8`. Si no está, la cobertura se informa como "not run". Es informativa salvo donde tu archivo de milestone fija un umbral; la puerta real es el 85 % total de la CI.
- **Estructura de documentos:** `-k doc_14` y `-k doc_15`, a log.
- **Diff:** `git diff --check <base>...HEAD` y `git diff --stat <base>...HEAD`, donde `<base>` es el "Commit base" de tu archivo de milestone.
- Un gate pasa con exit 0, o cuando su resumen no lista más fallos que los conocidos de la línea base que cita tu archivo de milestone.

## Fases, progreso y estado

- Al empezar una fase la pones en 🟡 en tu archivo de milestone; al terminarla, en 🟢; si te bloquea una contradicción, en 🔴 con el motivo.
- Al terminar cada fase añades una línea con fecha al "Registro de progreso" de tu archivo.
- No tocas el plan maestro ni ningún otro archivo del plan, salvo tu archivo de milestone y tus archivos de `work/`.

## Documentos compartidos

Solo el orquestador los escribe. Un cambio que necesites en ellos va como propuesta en `docs/plan/id-corto-outlook/work/M<NN>-propuestas.md` (archivo, ancla y texto propuesto):

- `docs/changes/id-corto-outlook.md` y cualquier otro archivo de `docs/changes/`.
- `docs/prd/` (nadie lo toca en este plan).
- `docs/tests/` (definiciones y marcas de casos).
- `docs/KNOWN-DEFECTS.md`, `docs/ROADMAP.md`, `docs/PERFORMANCE-BACKLOG.md`.
- Todos los archivos de `docs/plan/id-corto-outlook/` salvo tu archivo de milestone y tus archivos de `work/`.

## Fuera de alcance

Si necesitas escribir un archivo que no está en tu alcance, haces handoff y nombras en tu mensaje final el archivo y el cambio necesario. Si encuentras una contradicción entre tu archivo de milestone, la unidad y el código, no improvisas: la describes en tu evidencia cruda, pones la fase en 🔴 y haces handoff.

## Redacción

- La evidencia, los logs copiados, los tests y los fixtures no contienen datos del correo real: ni `EntryID` reales, direcciones, asuntos, nombres de carpetas o de cuentas, ni rutas del home real. De una corrida SMOKE solo se copian recuentos, longitudes, códigos y exit.
- Los tests usan el doble de Outlook, el store de prueba de Apple Mail y el plugin de prueba, con `HOME` y `USERPROFILE` temporales.

## Evidencia cruda

Escribes `../mailquery-logs/id-corto-outlook/M<NN>/evidencia-cruda.md` (fuera del repositorio, no se commitea) con:

1. Comandos de la suite completa, su resumen (`Ran …`, `OK` o `FAILED (…)`) y el commit sobre el que corrió.
2. Cada grupo de tu milestone ejecutado solo, con su resumen.
3. Goldens creados o actualizados, con la razón de cada cambio de valor.
4. Tests nuevos y casos actualizados, con sus IDs y los ACs que cubren.
5. Salida de `git diff --check` y de `git diff --stat` contra el commit base.
6. Riesgos, deuda aceptada, decisiones que tomaste dentro de lo que permite tu archivo, contradicciones y pendientes.
7. Cobertura de los módulos tocados, o "not run".
8. Propuestas de cambio de marca en `docs/tests/` (`[pendiente]` → implementado, `[por actualizar]` → implementado).

## Handoff

Por presupuesto (`tool-call-budget`), por fuera de alcance o por contradicción: terminas la edición en curso, escribes `docs/plan/id-corto-outlook/work/M<NN>-handoff.md` (hecho, pendiente, siguiente comando, fallos abiertos), haces commit de todo y devuelves el control.

## Mensaje final

Un índice de como mucho `final-message-lines` líneas:

- Transición propuesta (`M<NN>: 🟡 → 🟢`, o `🟡 → 🔴: <motivo>`).
- Rango y número de commits.
- Conteo de la suite completa y de los grupos del milestone, o "not run".
- Cobertura de los módulos tocados, o "not run".
- Rutas de `evidencia-cruda.md`, `docs/plan/id-corto-outlook/work/M<NN>-propuestas.md` y `docs/plan/id-corto-outlook/work/M<NN>-handoff.md` que existan.
- Contradicción bloqueante, resumida, si la hay.

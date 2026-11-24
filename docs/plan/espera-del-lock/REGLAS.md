# Reglas para subagentes — espera-del-lock

**Límites:** los de `CLAUDE.md`, sin cambios.

## Ramas y worktrees

- Rama del milestone: `feature/espera-del-lock-m<NN>`, creada desde el tip de `feature/espera-del-lock-lote-1`. Nunca desde `develop`.
- Worktree: `../mailquery-wt/espera-del-lock-m<NN>`, uno por milestone activo, reseteado al tip del lote; no se crea otro por intento.
- El subagente no integra, no empuja y no abre PR. Commits en inglés, sin atribuciones a herramientas.

## Documentos compartidos

Solo los escribe el orquestador; el subagente propone sus cambios en `work/M<NN>-propuestas.md`:

- `MASTER-PLAN.md`, `INTEGRACION.md`, `REGLAS.md`, `TRAZABILIDAD.md`, `DECISIONES.md`, `REGISTRO.md` y `evidence/` de este plan.
- `docs/changes/espera-del-lock.md`.
- `docs/tests/` y `docs/prd/`.

## Directorio de logs

`../mailquery-logs/espera-del-lock/M<NN>/`, fuera de todo checkout. Se crea antes del primer comando.

## Formas de comando

Suite completa, sin `-v` en la conversación:

```bash
python -B -m unittest discover -s tests -t . > "$LOG/suite.log" 2>&1; echo "exit=$?"; tail -n 4 "$LOG/suite.log"; grep -E "^(FAIL|ERROR):" "$LOG/suite.log" | head -n 40
```

```powershell
python -B -m unittest discover -s tests -t . *> "$LOG\suite.log"; "exit=$LASTEXITCODE"; Get-Content "$LOG\suite.log" -Tail 4; Select-String -Path "$LOG\suite.log" -Pattern '^(FAIL|ERROR):' | Select-Object -First 40
```

- Un grupo solo: se añade `-k <grupo>` (por ejemplo `-k ut_cfg_07`) y se cambia el nombre del log.
- Cobertura: `python -B -m coverage run -m unittest discover -s tests -t .` con la misma redirección, y después `python -m coverage report --include=<módulos tocados>`.
- Estructura de los documentos: `-k doc_14` y `-k doc_15`.
- Espacios: `git diff --check <base del lote>`; resumen: `git diff --stat <base del lote>`.

## Evidencia cruda

El subagente la escribe en `work/M<NN>-evidencia.md` y la confirma en su rama; no escribe en `evidence/`, que redacta el orquestador a partir de ella. El mensaje final cita la ruta y no pega el archivo:

- Comando y línea de resumen de la suite completa, con el commit.
- Comando y línea de resumen de cada grupo del milestone ejecutado solo.
- Goldens creados o cambiados y el motivo, o "ninguno".
- Tests nuevos con su ID y el AC que cubren.
- Salida de `git diff --check` y de `git diff --stat` contra la base del lote.
- Cobertura de los módulos tocados.
- Riesgos, deuda aceptada, decisiones aplicadas y pendientes.

## Redacción

La evidencia y los logs copiados no llevan rutas del perfil del usuario (se escriben como `~`), direcciones de correo, nombres de cuentas ni contenido de mensajes reales.

## Tests

- Solo `unittest`; nombres `test_<grupo>_<caso>_<descripción>`; ningún test usa el `HOME` ni el `~/.mailquery` del usuario; todo subproceso fija `HOME` y, en Windows, `USERPROFILE` a un directorio temporal.
- Los tests pueden citar los IDs de requisito y de caso; el código de `src/` no cita ningún ID ni documento.
- Las diferencias de plataforma van como aserción condicional, sin saltos nuevos.

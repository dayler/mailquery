# Protocolo de los subagentes del plan servidor-mcp

Límites: los de `CLAUDE.md`, sin cambios. Lo que `CLAUDE.md` ya dice (lectura, salida, handoff, presupuesto, mensaje final) no se repite aquí.

## 1. Ramas, worktrees y entorno

- Trabajas en el worktree y la rama que te da el orquestador (`feature/servidor-mcp-m<NN>`), creada desde el tip de `feature/servidor-mcp-lote-<n>`. No cambias de rama, no creas worktrees, no haces merge, rebase ni push.
- **Primer lanzamiento de un milestone.** Solo entonces, el orquestador prepara el worktree asignado (bash; en PowerShell, las mismas órdenes `git`):

  ```sh
  git -C <worktree> switch -C feature/servidor-mcp-m<NN> feature/servidor-mcp-lote-<n>
  git -C <worktree> clean -fdx -e .venv
  ```

- **Relanzamiento.** No se repite la preparación: la rama conserva los commits del intento anterior. El orquestador comprueba `git -C <worktree> status --short` y `git -C <worktree> log --oneline -5` y te relanza con tu archivo de milestone y `work/M<NN>-handoff.md`.
- **Intérprete.** Cada worktree tiene un entorno virtual `.venv` que crea el orquestador en F0, con `css-inline~=0.23.1`, `coverage~=7.17` y, en Windows, `pywin32`, sin instalar `mailquery` (como la matriz de CI). Antes de cualquier comando activas ese entorno (`. .venv/bin/activate` en bash, `.venv\Scripts\Activate.ps1` en PowerShell); en este protocolo y en tu archivo de milestone, `python` es el de ese entorno. La línea base que recibes se midió con él.

## 2. Commits

- Mensajes en inglés, con el estilo del repositorio (`feat(mcp): …`, `refactor(logging): …`, `test(mcp): …`, `docs(readme): …`). Sin líneas de atribución a herramientas o modelos.
- Un commit por fase terminada como mínimo.
- En tu primer commit copias en tu archivo de milestone el commit base y la línea base que te dio el orquestador.

## 3. Documentos compartidos

Solo los escribe el orquestador; tú propones los cambios en `work/M<NN>-propuestas.md`:

- `docs/plan/servidor-mcp/PLAN.md`, `DECISIONES.md`, `RIESGOS.md`, `TRAZABILIDAD.md`, `REGISTRO.md`, `DEFINICIONES-TESTS.md` y `evidence/`.
- `docs/changes/servidor-mcp.md` (tabla de conciliación, documentos consumidores, checklist, desviaciones).
- Todo `docs/tests/` (marcas `[pendiente]` y `[por actualizar]`, textos de casos, matriz, prefijos).
- `docs/prd/` no se toca en este plan.

## 4. Comandos y logs

- **Directorio de logs (`$LOGS`).** Ruta absoluta que te da el orquestador al lanzar: `<padre del repositorio principal>/mailquery-wt/logs/servidor-mcp/M<NN>/`, fuera de todo checkout. Lo creas si no existe. En bash, `LOGS=<ruta>`; en PowerShell, `$LOGS = "<ruta>"`.
- **Suite completa** (bash):

  ```sh
  python -B -m unittest discover -s tests -t . > "$LOGS/suite.log" 2>&1; echo "exit=$?"
  grep -E "^(Ran |OK|FAILED|ERROR: |FAIL: )" "$LOGS/suite.log" | head -60
  ```

- **Suite completa** (PowerShell):

  ```powershell
  python -B -m unittest discover -s tests -t . *> "$LOGS\suite.log"; "exit=$LASTEXITCODE"
  Select-String -Path "$LOGS\suite.log" -Pattern '^(Ran |OK|FAILED|ERROR: |FAIL: )' | Select-Object -First 60
  ```

- **Un grupo o un caso:** `python -B -m unittest discover -s tests -t . -k ut_mcp_03`.
- **Cobertura de los módulos tocados** (bash; en PowerShell, la misma forma con `*>`):

  ```sh
  python -B -m coverage run -m unittest discover -s tests -t . > "$LOGS/coverage-run.log" 2>&1
  python -m coverage report --include="src/mailquery/<módulo>.py" > "$LOGS/coverage.log" 2>&1; tail -20 "$LOGS/coverage.log"
  ```

- **Diff:** `git diff --check <base-del-lote>..HEAD` y `git diff --stat <base-del-lote>..HEAD`.
- **Estructura de la documentación:** `python -B -m unittest discover -s tests -t . -k doc_14` y `-k doc_15`.

## 5. Redacción

- En la evidencia, los logs y los mensajes no aparecen direcciones de correo, nombres de cuentas, asuntos ni rutas del equipo. La ruta del home se escribe `<HOME>` y la del repositorio `<REPO>`.
- Los tests usan `HOME` (y en Windows `USERPROFILE`) temporales; ningún test lee el `~/.mailquery` del usuario.

## 6. Evidencia cruda

No escribes en `docs/plan/servidor-mcp/evidence/`. Escribes los datos en `$LOGS/evidencia-cruda.md`, fuera del repositorio, con estas secciones; el orquestador los copia a `evidence/M<NN>.md`:

1. **Suite completa:** comando, commit (`git rev-parse HEAD`), línea `Ran N tests`, resultado y la lista de fallos y saltos comparada con la línea base.
2. **Grupos del milestone solos:** comando `-k` y resultado de cada grupo.
3. **Goldens:** archivos creados o actualizados, con una línea de justificación cada uno; o "ninguno".
4. **Tests nuevos y cambiados:** IDs de caso, nombre del método y AC o requisito que cubre cada uno.
5. **Diff:** salida de `git diff --check` y de `git diff --stat` contra la base del lote.
6. **Cobertura:** porcentaje de cada módulo tocado.
7. **Riesgos, deuda, decisiones y pendientes:** lo que aceptaste, lo que decidiste dentro del margen de tu archivo y lo que queda abierto.
8. **Lo propio del milestone:** lo que pide la sección "Datos crudos de evidencia" de tu archivo.

## 7. Propuestas

`work/M<NN>-propuestas.md` lleva, por este orden:

- **Marcas de `docs/tests/`:** cada caso que pasa de `[pendiente]` o `[por actualizar]` a implementado, con su método de test; un caso nuevo o un cambio de texto que la implementación hizo necesario, con el texto propuesto.
- **Unidad:** filas `RC-<nn>` que propones pasar a `implementado`, documentos consumidores que propones pasar a `actualizado` o `sin cambio`, y cualquier hallazgo para "Qué cambia".
- **Desviaciones:** si cumplir tu objetivo exige cambiar el requerimiento o un criterio de aceptación de la unidad, no lo implementas: lo describes aquí, haces handoff y el orquestador lo lleva al dueño. Solo una desviación aprobada entra en la unidad.
- **Plan:** decisiones tomadas dentro de tu margen que el orquestador debe registrar.

## 8. Mensaje final

El índice de `CLAUDE.md`, con estas rutas: `$LOGS/evidencia-cruda.md`, `work/M<NN>-propuestas.md` y, si existe, `work/M<NN>-handoff.md`.

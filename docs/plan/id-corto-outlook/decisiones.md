# Decisiones, respuestas del dueño y línea base

## Línea base

- **Al planificar (2026-11-23), commit `384e5a8`, Python del sistema:** `Ran 1451 tests`, `FAILED (failures=10, skipped=7)`, unos 4 minutos. Los 10 fallos son del entorno local, no del código:
  - Sin `css-inline` instalado: UT-CNT-02.10, UT-CNT-03.01, UT-CNT-03.02, UT-CNT-03.10, UT-CW-07.01.
  - Con una distribución `mailquery 2.0.1` instalada en el Python del sistema (los metadatos no coinciden con `3.0.0a1`): TC-01.01, TC-02.07, TC-06.02, PKG-01.03, PKG-02.01.
  - Los SMOKE corren contra el Outlook real del equipo (solo lectura).
- **Línea base de ejecución:** la registra el orquestador en F0 con el venv del plan (D-02), en el tip de la rama de la unidad. Se espera 0 fallos; si aparecen, se anotan aquí con su causa y son los fallos conocidos de todos los milestones.

**Tabla: Línea base de ejecución**

| Fecha | Commit | Python | Resumen | Fallos conocidos | Saltos |
|---|---|---|---|---|---|
| 2026-11-23 | 4361e96 | 3.14.6 (venv del plan) | `Ran 1452 tests`, `OK (skipped=8)` | ninguno | 8: SMOKE e instaladores que no aplican en macOS |

## Respuestas del dueño (HITL)

- **H-01 (2026-11-23) Infraestructura de tests.** Pregunta del encargo: si faltaban tests unitarios, una suite de un solo comando o la forma de probar un AC, había que preguntar. Hallazgo: la suite es `unittest`, corre con `python -B -m unittest discover -s tests -t .`, tiene un doble del modelo de objetos de Outlook con fallos COM, cuelgues y stores inyectables (`tests/fakes/outlook.py`), un plugin de prueba (`tests/fakes/plugin.py`), un lanzador en subproceso para los timeouts (`tests/fakes/run_cli.py`), goldens regenerables con `MAILQUERY_UPDATE_GOLDENS=1` y SMOKE contra el cliente real. Ningún AC necesita Outlook real. No hizo falta preguntar.
- **H-02 (2026-11-23) Revisión independiente.** El dueño pidió revisar el plan con un revisor independiente y resolver lo que se pueda de la forma más simple; solo lo que no se pueda resolver se le pregunta.
- **H-03 (2026-11-23) Item que existe pero no se puede abrir.** Pregunta: la condición "Garantía" de RF-81 dice que `show` y `attachment` de ese item fallan con `message uid … was not found` "como hoy", pero hoy `show` responde desde las tablas de la carpeta y `attachment` con `E_ATTACHMENT_UNREADABLE`. Respuesta del dueño: mantener el comportamiento actual. En F0 el orquestador corrige esa condición de la unidad (el item que no se puede abrir sale de la lista de causas sin error propio y queda "responde como hoy") y la anota en "Desviaciones aprobadas" con el dueño y la fecha.
- Las decisiones del dueño sobre el producto están en la sección "Decisiones" de la unidad y no se repiten aquí.

## Decisiones del plan

Decisiones de implementación que la unidad deja abiertas, resueltas de la forma más simple y compatibles con ella.

- **D-01. Rama de la unidad.** `feature/id-corto-outlook` ya existe (rama del borrador de la unidad, integrada en `develop`, con worktree en `../mailquery-id-corto-outlook`). F0 la avanza con `git merge --ff-only develop`; así queda "creada desde `develop`" sin borrar nada, y ese worktree es el de integración.
- **D-02. Entorno local.** Venv `../mailquery-venv-id-corto/` con `css-inline~=0.23.1` y `coverage~=7.17`, sin instalar `mailquery`, como la CI. Sin venv, los 10 fallos de la línea base al planificar son los conocidos.
- **D-03. Evidencia cruda fuera del repositorio.** Por orden del dueño, el subagente no escribe evidencia en `docs/plan/`: deja los datos crudos en `../mailquery-logs/id-corto-outlook/M<NN>/evidencia-cruda.md` y el orquestador escribe `evidence/M<NN>.md`. El handoff y las propuestas sí se commitean, en `docs/plan/id-corto-outlook/work/`.
- **D-04. API de la librería.** En `src/mailquery/native_ids.py`:
  - `short_id(text: str, length: int) -> str`; `length` fuera de 1…51 o `text` que no es `str` ⇒ `ValueError`.
  - `cache_path(home: Path) -> Path` = `home / "db" / "cache.db"`.
  - `NativeIdCache.open(driver: str, *, home: Path) -> NativeIdCache` y `NativeIdCache.open_in_memory(driver: str) -> NativeIdCache`.
  - Métodos: `assign(native_ids: Sequence[str], *, length: int = 10) -> dict[str, str]`, `register(native_ids: Sequence[str]) -> None`, `resolve(uid_part: str) -> str | None`, `discard(native_id: str) -> None`, `close() -> None`.
  - `PluginNativeIds(home: Path, driver: str)`: acceso de un plugin con `assign`, `register`, `resolve`, `discard` y `close`; abre la base en la primera operación (D-08), es seguro entre hilos (D-15) y convierte sus fallos con el protocolo de RF-50: base ocupada ⇒ `PluginError(Reason.BUSY)`, sin permiso ⇒ `PluginError(Reason.PERMISSION)`, cualquier otro fallo ⇒ una excepción que no es `PluginError` (el núcleo la convierte en `E_PLUGIN_FAILED`).
  - `assign` llama a `short_id` por su nombre del módulo (`native_ids.short_id`), de modo que un test puede sustituirla con `mock.patch("mailquery.native_ids.short_id", …)`.
  - Clasificación de fallos: `E_PERMISSION` si `mkdir`/`chmod` lanzan `PermissionError`, o si `os.access` sobre la carpeta o el archivo existente niega lectura o escritura antes de conectar, o si SQLite falla con `SQLITE_PERM`, `SQLITE_READONLY` o `SQLITE_CANTOPEN` y `os.access` lo niega; `E_LOCKED` si SQLite sigue en `SQLITE_BUSY` o `SQLITE_LOCKED` al vencer `BUSY_TIMEOUT_SECONDS`; `E_IO` cualquier otro fallo, un archivo que no es SQLite, una versión de formato distinta de 0 (sin tablas) o 1, o un conflicto al registrar. Los tests inyectan el fallo de permiso sustituyendo `os.access` o la función interna `native_ids._connect`.
  - Archivo vacío: uno de 0 bytes, o una base con `user_version` 0 y sin tablas; se inicializa como uno nuevo.
  - Constantes: `ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"`, `FORMAT_VERSION = 1` (en `PRAGMA user_version`), `BUSY_TIMEOUT_SECONDS = 5.0` (leída en cada apertura para que un test la acorte).
- **D-05. Textos literales.** En inglés, comparados literalmente por los tests:
  - `E_LOCKED`: mensaje `the native id cache is locked by another process`; hint `close the process that holds ~/.mailquery/db/cache.db and run the command again`.
  - `E_PERMISSION`: mensaje `no permission to read or write the native id cache`; hint `check the permissions of ~/.mailquery/db/ and ~/.mailquery/db/cache.db`.
  - `E_IO`: mensaje `cannot use the native id cache: <detalle>` (`<detalle>`: `not a valid native id cache`, `conflicting uid part` u otro texto sin datos de correo); hint `if you delete ~/.mailquery/db/cache.db, mailquery creates an empty one; uids already printed do not resolve until you repeat the search`.
  - Forma inválida en Windows: mensaje `invalid uid part '<id>': expected a short id` (`<id>` con `repr`); hint ``Outlook uids are short ids as printed by `mailquery search` and `mailquery new`; run `mailquery search` to find the uid of a message``.
  - Hint de repetir la búsqueda (uid fuera de la caché o mensaje ausente confirmado): ``the uid is not in the native id cache or its message no longer exists; run `mailquery search` or `mailquery new` again to get its current uid``.
- **D-06. Home del driver `outlook`.** `OutlookBackend` gana el método interno `bind_home(home: Path)`; `cli._open_drivers` lo llama, si existe, en cada driver interno (como `bind_command`). Sin `bind_home`, el driver usa `tmp_root.parent` si tiene `tmp_root`; si no tiene ninguno de los dos (uso directo del backend fuera de la CLI, como en los tests unitarios), usa `NativeIdCache.open_in_memory`.
- **D-07. "No encontrado" con hint del driver.** `backends/base.py` define `MessageNotFound(LookupError)` con el atributo `hint`. `find_message` de un driver interno puede lanzarla; `run_show` y `cli._run_attachment` la capturan y responden con su error de "no encontrado" actual (mismo código, mensaje y formato del uid) y ese hint. Ningún driver la lanza hasta M05. Es solo para drivers internos: si un plugin externo la lanzara, `call_driver` la convierte en `E_PLUGIN_FAILED` como cualquier excepción.
- **D-08. Acceso de un plugin.** `PluginContext` gana el campo `native_ids: PluginNativeIds | None = None`. `cli._open_drivers` da a cada plugin su propio contexto con `PluginNativeIds(home, <driver>)`. La base se abre en la primera operación: `mailboxes`, `doctor` y `--version` no la crean aunque haya plugins declarados. Cada contexto se cierra (`PluginNativeIds.close()`) en el mismo `finally` que cierra los drivers. El contexto que `doctor` da a un plugin para sus chequeos lleva `native_ids = None`.
- **D-09. Conciliación, merge y borrado del plan.** Fuera de los milestones. Se hacen solo por orden del dueño, en este orden: conciliación en la rama de la unidad (último commit), matriz verde, merge del PR, borrado del plan.
- **D-10. Ganchos opcionales.** `plugins/api.py` define `OPTIONAL_OPERATIONS = frozenset({"printed_messages", "display_native_id"})`, separado de `METADATA_OPERATIONS` para que el registro no los exija, y una función del núcleo que llama a un gancho solo si el driver lo tiene, a través de `call_driver` (errores de RF-50 y tope de 30 s). El núcleo ignora lo que devuelve `printed_messages`. Lo que devuelve el `display_native_id` de un plugin externo se valida con `uid.is_valid_native_id`; si no cumple ⇒ `E_PLUGIN_FAILED` (exit 3). El de un driver interno no se valida (el de `outlook` devuelve siempre un `EntryID` hexadecimal válido).
- **D-11. Cuándo se abre la caché en Outlook.** En la primera consulta (`query`) o resolución (`find_message` y operaciones de adjuntos) de la ejecución. Interpretación de "la abre en `search`, `new`, `show` y `attachment`": la abre cuando esos comandos consultan el driver; un `search` o `new` que termina antes de consultarlo (sin cuentas en el alcance) no la crea. Ningún AC fija ese caso. `mailboxes`, `doctor` y `--version` nunca la abren.
- **D-12. Longitud del id corto y colisiones en los tests.** Constante `SHORT_ID_LENGTH = 10` en `backends/outlook.py`, pasada a `assign`; no se cambia en los tests, porque la validación de entrada exige 10 caracteres. Los tests de colisión de Outlook sustituyen `mailquery.native_ids.short_id`, dentro del proceso, por una función que devuelve el mismo id corto válido de 10 caracteres (por ejemplo `k3f9q2m7xa`) para dos o tres `EntryID` elegidos y el cálculo real para el resto. Los tests de la librería provocan colisiones con `assign(…, length=1)`.
- **D-13. Timeout en AC-66.** El caso de timeout corre en subproceso con `tests/fakes/run_cli.py --hang …` (el watchdog termina el proceso) y después comprueba la fila en `cache.db`.
- **D-14. Sin ciclo de importación.** `native_ids.py` no importa `mailquery.plugins` en el nivel del módulo (lo importa dentro de `PluginNativeIds`), porque `mailquery.plugins` reexporta `short_id`.
- **D-15. Hilos.** Las llamadas a un plugin externo corren en un hilo trabajador por llamada: `PluginNativeIds` abre la conexión con `check_same_thread=False` y serializa las operaciones con un `threading.Lock`.
- **D-16. `--show-native-id`.** `run_show` arma el mensaje igual que sin la opción y, al final, solo sustituye `message.uid` por `<driver>:<forma nativa>` cuando el driver tiene el gancho. Los warnings, los errores, `cached_path` y la caché no cambian.
- **D-17. Aviso de impresos.** En `run_search` (sin agrupar y con `--group-by`), justo antes de devolver la respuesta; en `run_new` (también con `--peek`), antes de escribir el estado. Un aviso por driver con al menos una fila, con los `row["uid"]` de sus filas impresas sin repetir, en el orden de la respuesta. `--count` no avisa.
- **D-18. Item que existe pero no se puede abrir.** Por la respuesta H-03 del dueño: es *indeterminado*, la fila se conserva y `show` y `attachment` responden como hoy: `show` arma la fila desde las tablas de su carpeta (OL-21) y, si no aparece, "no encontrado" con el hint actual; `attachment` responde `E_ATTACHMENT_UNREADABLE`. Es una desviación aprobada de la condición "Garantía" de RF-81; el orquestador la aplica a la unidad en F0 (H-03).
- **D-19. `docs/ROADMAP.md`.** No es documento consumidor ni está en CL-11; su mención de `3.0.0a1` no se cambia en este plan.
- **D-21. Ubicación de worktrees, venv y logs.** El sandbox de esta sesión solo permite escribir dentro del checkout principal, así que los worktrees viven en `.worktrees/` (`unit`, `lote-1`, `lote-2`, `wt-a`, `wt-b`), el venv del plan en `.venv-id-corto/` y los logs en `.logs/id-corto-outlook/M<NN>/`, todos dentro de `mailquery` y excluidos con `.git/info/exclude`. Las rutas relativas de `protocolo.md` se leen desde la raíz del worktree con esa base: el venv es `../../.venv-id-corto/bin/python` y los logs `../../.logs/id-corto-outlook/M<NN>/`. El commit base y las ramas no cambian.
- **D-20. Commit base y línea base en cada milestone.** El orquestador da al subagente, en el mensaje de lanzamiento, el commit base (tip de la rama del lote) y la línea base de la suite; el subagente los copia en la cabecera de su archivo de milestone en su primer commit.

## Decisiones abiertas

Ninguna. La única contradicción encontrada (item que no se puede abrir) la resolvió el dueño en H-03; ningún AC quedó sin forma de probarse con la infraestructura existente.

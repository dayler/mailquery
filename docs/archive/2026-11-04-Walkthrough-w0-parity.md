# Walkthrough — Fase W0: portabilidad, paridad macOS y auditoría de tests

| Campo | Valor |
|-------|-------|
| Fecha | 2026-11-04 |
| Rama | `feature/w0-parity` (git flow, creada desde `develop` @ `cac8776`) |
| Commits | Uno solo para la fase completa (decisión del dueño) |
| Plan | `docs/plans/2026-11-03-v2.0.0-windows-outlook.md` rev. 18 |
| Contrato | `docs/PRD.md` v1.1 + `docs/backends/*.md` (sin modificar) |
| Orquestación | Sesión orquestadora Opus 5.5; un subagente Sonnet 5.5 por tarea (tabla "Orquestación y modelos" del plan) |
| Host | Windows 11 x64, Python 3.14.7, `pywin32` instalado |
| Cierre | Revisión del planificador y OK del dueño **asumidos** por instrucción del dueño; CI verificada **solo en Windows** (instrucciones para macOS al final) |

---

## 1. Tareas hechas

| Tarea | Qué se hizo | Casos de test |
|-------|-------------|---------------|
| W0-T01 | `docs/INTERFACES.md`: la regla "no ejecutar git" pasa a D-01 (el orquestador crea la rama y hace los commits; los subagentes en paralelo usan su propio worktree). | — |
| W0-T02 | Lock portable en `state.py`: `fcntl.flock` en POSIX, `msvcrt.locking` en Windows; mismo `E_LOCKED`. | UT-ST-01.01…07 (renombrados desde `RunLockTest`) |
| W0-T03 | Portabilidad de la suite: modos 0700/0600 solo en POSIX dentro del test (D-07); 11 `skipTest` heredados eliminados; `\`→`/` en `_normalize`; `HOME`/`USERPROFILE` temporales y `encoding="utf-8"` en los subprocess; `Path(...).name == "2714.emlx"`; mock `unexpected_schema` eliminado. | Filas de §7.2 sin tarea propia |
| W0-T04 | Chequeo `home` según SO: POSIX 0700; Windows, existe y es escribible (archivo de prueba en `~/.mailquery/tmp`, D-04). | UT-CLI-13.01, .02 |
| W0-T05 | `build_store(…, extended=False)` en `tests/fixtures/make_fixtures.py`; con `extended=True` añade `Proyectos/Inbox`, carpetas homónimas, carpeta llamada como el path de otra, 2 S/MIME, `.emlx` ausente con adjunto, borrado, `global_message_id` 0, duplicado con buzón agregado, fechas nula/0/1e20/futura y variante WAL con `-shm`. | Sanity `test_store.ExtendedFixtureTests` |
| W0-T06 | JSON formateado (`indent=2`, sin escapes `\u`, LF final) en todas las salidas; `stdout`/`stderr` en UTF-8 y LF al inicio de `main()`. | UT-OUT-01.01, UT-OUT-03.01/.02, UT-CLI-08.01…03 |
| W0-T07 | `-v`/`--version` (RF-31, §12.9) sin efectos; `--backend` y demás opciones inexistentes ⇒ `E_USAGE`. | UT-CLI-01.01…06, 02.01…04, 03.01…03, 04.01 |
| W0-T08 | Logs por tamaño (`RotatingFileHandler`, 5 rotados, 0600), formato §14 con `,mmm` y `backend=`, `MailqueryError.log_message`, warnings solo con número y códigos, líneas de B-29 sin rutas ni uuids; `max_size_mb` 1–1024; `retention_days` ⇒ hint exacto; `config.example.toml` actualizado. | UT-LOG-01…04, UT-CFG-01.01, UT-CFG-02.01, UT-CLI-05.01/.02 |
| W0-T09 | `errors.py`: `E_CLIENT_UNSUPPORTED`, `E_DEPENDENCY_MISSING`, `E_CLIENT_TIMEOUT` (3), `E_CLIENT_BUSY` (5), `E_OUTLOOK_NOT_RUNNING` (6). | UT-CLI-09.01 (23 códigos) |
| W0-T10 | B-01, B-02, B-03, B-13, B-14, B-15, B-20, B-28, B-30 y `excluded_stores: []`: primera corrida de `new` con ventana, lookback de la config en cada corrida, fechas inválidas y futuras ignoradas (reloj inyectable), estado con uids ≥ 1, hint nuevo de `E_STATE_CORRUPT`, `show` limitado a cuentas declaradas y uid validado por `parse_uid` antes del home/config. | UT-SR-07.01…09, 08.01, 09.01…05, 10.01…05, 11.01…08, UT-OUT-02.01…04, UT-CLI-07.01…03, UT-ST-02.01…07, UT-ST-04.01/.02 |
| W0-T11 | B-04…B-08: `W_BODY_UNREADABLE`, sin `W_EMLX_CORRUPT` espurio, `body.readable`, adjuntos de `show` desde el `Envelope Index` + `W_ATTACHMENTS_UNAVAILABLE`, `W_ACCOUNT_LABELS_UNAVAILABLE` en `search`/`new`/`show`. | UT-SR-05.01…08, 06.01…03, 12.01/.02 |
| W0-T12 | `doctor`: B-09 (`not evaluated` según §A.7), B-10 (texto de `state` sin cursor), B-11 (resolución real de cada bloque en `config`), B-12 (`envelope_index` abre con `live_ro`/`copy_ro`). | UT-CLI-10.01…05, 11.01/.02, 12.01/.02 |
| W0-T13 | B-16…B-19, B-21, B-23, B-24, B-25 (copias de `tmp/`), B-26, B-27: términos de filtro §12.2, filtro vacío no acota, hint de `--include-mailbox`, ayuda §12.7, INBOX de primer nivel, `E_DB_BUSY` con un reintento, `ENOSPC` ⇒ `E_INTERNAL`, copias 0600, resolución de carpetas §15.3. | UT-SR-01.01…07, 02.01…03, 03.01…05, 04.01, 13.01…03, 14.01/.02, 15.01/.02, 16.01…04, UT-CLI-06.01…06, UT-ST-05.01/.02, UT-STO-01.01/.02 |
| W0-T14 | Goldens nuevos `show_smime_encrypted` y `show_not_in_scope_error`; tests de golden renombrados a TC-01.01…11; gate de solo lectura TC-03.01 sobre el fixture extendido; auditoría de diffs de goldens (§3). | TC-01.01…11, TC-03.01 |
| W0-T15 | `.github/workflows/tests.yml`: job `unittest` en `ubuntu-latest`, `macos-latest` y `windows-latest` × Python 3.11–3.14, `fail-fast: false`, `pywin32` solo en Windows; job `install-scripts` sin cambios. | Suite completa (verificada solo en Windows) |

Cobertura del catálogo: los **161 casos** de W0 de §7.3 y §7.4 tienen su método con el ID en el nombre (comprobado por búsqueda de `test_<grupo>_<caso>` en `tests/`).

---

## 2. Salida de la suite

Comando: `python -B -m unittest discover -s tests -t . -v` (PowerShell, host Windows).

| Momento | Corridos | OK | Fallidos | Errores | Saltados |
|---------|----------|----|----------|---------|----------|
| Línea base (`cac8776`) | 168 | 152 | 1 | 5 (módulos que no importan por `fcntl`: `test_cli`, `test_integration`, `test_readonly`, `test_search`, `test_state`) | 10 |
| Tras W0-T02 | 346 | 325 | 10 | 1 | 10 |
| Tras W0-T03 | 346 | 331 | 5 | 0 | 10 |
| **Final W0** | **471** | **461** | **0** | **0** | **10** |

- Los 10 saltados son `InstallShTest` sin `sh` en el `PATH` de PowerShell: salto permitido por §7.7. Desde Git Bash (con `sh`) corren y pasan: 471 corridos, 0 saltados.
- La línea base del plan (§2) cita 2 fallos; en esta corrida `InstallShTest.test_print_config_matches_template` no falla porque se salta (sin `sh`).
- Verificaciones adicionales: `python -m compileall -q src` sin errores; `python -m mailquery --version` ⇒ `mailquery 1.3.4 (backend outlook; Python 3.14.7; Windows 10.0.26200 AMD64)`; `--help` con la descripción multiplataforma; `show abc` ⇒ `E_USAGE` exit 2.

---

## 3. Goldens que cambian y su fila de §23.3

| Golden | Cambio | Fila de §23.3 |
|--------|--------|---------------|
| `doctor.json` | `config`: una línea por bloque `<key> → <label> (<uuid>): INBOX[, …]`, unidas por `; ` | `doctor` (B-11) |
| `doctor.json` | `state`: `no state yet; the next new run is a first run and emits the messages received in the last 10min before the newest message` | `doctor` (B-10) |
| `doctor.json` | `home`: `<ROOT>/home (mode 0700)` ⇒ `<HOME>` | Sin fila: normalización del test (§7.2, "Tests de `doctor`": `_normalize` sustituye el `detail` de `home`), no es una salida del producto |
| `mailboxes.json` | `excluded_stores: []` | `mailboxes` |
| `new_first_run.json` | `count` 0 ⇒ 2 (83160, 83170), `W_FIRST_RUN` nuevo, `W_EMLX_MISSING` de 83170 | Primera corrida de `new` sin estado |
| `new_seeded.json` | `previous.last_uid` 0 ⇒ 1 | Estado (`state.json`) |
| `new_seeded.json`, `search_default.json`, `search_all_mail.json`, `new_first_run.json` | `body.readable` | `body` en `search`/`new` |
| `show_smime_encrypted.json` (nuevo) | S/MIME cifrado: `readable=false`, adjuntos del `Envelope Index`, `W_BODY_UNREADABLE` + `W_ATTACHMENTS_UNAVAILABLE` | Warnings |
| `show_not_in_scope_error.json` (nuevo) | `E_ACCOUNT_NOT_IN_SCOPE` | `show` fuera de las cuentas declaradas |

Al cerrar W0, los goldens de Apple Mail quedan congelados (RNF-11).

---

## 4. Decisiones tomadas

Por instrucción del dueño, ante una ambigüedad se eligió lo más simple consistente con el PRD, sin detener la implementación.

| # | Tarea | Decisión |
|---|-------|----------|
| 1 | Proceso | Los worktrees del Agent tool parten de `origin/develop` (`ade3aa9`, plan rev. 8 y PRD v1.0) porque `develop` local no está publicado. Los worktrees de W0-T01/T02 se crearon a mano desde `feature/w0-parity`; un primer intento de W0-T02 sobre la base vieja se descartó sin integrar. |
| 2 | W0-T01 | La parte "no escribir en `~/.mailquery` real ni en `~/Library/Mail`" queda como viñeta propia (seguía a la regla de git con "Tampoco"). |
| 3 | W0-T03 | `cli.main` deja abierto el handler del log; en Windows impide borrar el directorio temporal. Se cierra en los tests, no en el producto. |
| 4 | W0-T03 | Los tests que solo comparan valores de `Path.home()` sin leer ni escribir ahí se dejan como están. |
| 5 | W0-T04 | `test_doctor_tolerates_a_broken_home`: la aserción de que `config` falla es solo POSIX (D-07); en Windows `<archivo>/config.toml` es "no encontrado". Sin cambio de producto (decisión del dueño). |
| 6 | W0-T04 | El reemplazo `home` ⇒ `<HOME>` en `_normalize` (asignado a W0-T12 en §7.2) se adelantó a W0-T04, porque era la única causa de fallo del golden de `doctor`. |
| 7 | W0-T05 | La carpeta de B-27 (nombre `Proyectos/Inbox` en primer nivel) no tiene mensajes; el `-shm` es un archivo vacío (sin escritor vivo); 90163 = ahora real + 30 días. |
| 8 | W0-T06 | UT-CLI-08.01/.02 parchean `cli._execute` dentro del subprocess para producir texto no ASCII (el store sintético es ASCII). |
| 9 | W0-T08 | En W0 el log escribe `backend=apple_mail` también en `win32`: es el único backend implementado (`--version` sí muestra `outlook`, RF-26). |
| 10 | W0-T08 | `schema_ok` en minúsculas (`true`/`false`), como en §14. |
| 11 | W0-T09 | `errors.py` no tiene hints por defecto por código; los hints de §B.7 se pasarán en W3/W4 donde se lancen los errores. |
| 12 | W0-T10 | `parse_uid` acepta `[+-]?dígitos`: `show 0` y `show -1` son enteros y dan "not found" (UT-CLI-07.03). |
| 13 | W0-T10 | Orden de `show`: resolución de `[scope]`, luego "not found", luego alcance de la cuenta; un mensaje sin carpeta o sin cuenta es "not found". |
| 14 | W0-T10 | `iso_timestamp` convierte vía `datetime` UTC con zona: la conversión anterior fallaba en Windows para el epoch 1 con zona UTC-4. |
| 15 | W0-T10 | Primera corrida con `--limit` menor que la ventana: `truncated=true`, `W_RESULTS_TRUNCATED` y hint, como en una corrida normal (RF-15, §12.10). |
| 16 | W0-T10 | Test extra `test_new_without_accounts_and_with_a_cursor_only_warns_no_accounts` para no perder el caso "sin cuentas y con cursor". |
| 17 | W0-T11 | `README.md`: solo se renombró `W_EMLX_UNREADABLE` (2 líneas); la reescritura es de W5-T04. Un `.emlx` corrupto irrecuperable también toma los adjuntos del índice. Orden de warnings en `show`: etiquetas, cuerpo, adjuntos. Corregido `emlx._smime_kind` (un cifrado se detectaba como firmado). |
| 18 | W0-T12 | `config` con varios bloques: una sola línea, bloques unidos por `; `. Si la config no carga, `state` usa el lookback por defecto. |
| 19 | W0-T12 | UT-CLI-12.02 simula el `PermissionError` (en `shutil.copy2`) en todos los SO: sin salto en ningún caso (§7.7). |
| 20 | W0-T13 | `test_failed_write_keeps_previous_state_and_no_temp_file` pasa de `ENOSPC` a `EIO` (B-24 cambia la expectativa de `ENOSPC`, que cubre UT-ST-05.01). |
| 21 | W0-T13 | UT-SR-02.03 usa nombres del fixture en lugar de "Juan Perez"; UT-SR-16.03/.04 reordenan el catálogo en el test o usan una carpeta sintética. Se quitó el fallback por nombre/path/URL de `config._find_mailbox` (INBOX es siempre la bandeja). |
| 22 | W0-T14 | Toda la clase `ReadOnlyStoreTest` usa el fixture extendido (aserciones de conteo como mínimo/subconjunto). `Envelope Index-shm` se excluye de la comparación: SQLite lo inicializa al abrir en solo lectura en Windows (0 ⇒ 32768 bytes); la base, el `-wal`, los `.emlx` y la ausencia de archivos nuevos se siguen comparando. |
| 23 | W0-T15 | Nombre del job con el SO; `python` en lugar de `python3` (como en §7.7); YAML revisado a mano (no hay PyYAML en el host). |

---

## 5. Puntos abiertos

1. **CI fuera de Windows sin verificar.** El workflow de W0-T15 solo se ejecuta tras el push; la suite se verificó en este host Windows. Las aserciones solo POSIX (UT-LOG-02, UT-STO-01, UT-CLI-13.01, modos de UT-ST-01.01, `ensure_app_home` 0700) no se ejercitaron: hay que correr la suite en el Mac (§6) o en CI.
2. **`-shm` en el gate de solo lectura.** Excluido de la comparación (decisión 22). En el store real con Mail abierto el `-shm` ya existe y lo mantiene Mail; conviene confirmarlo en la corrida real de W5.
3. **Revisión del planificador y OK del dueño** asumidos para cerrar la fase (instrucción del dueño).
4. **`develop` sin publicar.** Mientras `develop` local (`cac8776`) no esté en `origin`, los worktrees automáticos parten de una base vieja; las fases siguientes con tareas en paralelo (W5-T01/T02) necesitan crearlos a mano desde la rama de la fase.
5. **Textos de la 1.x fuera de W0.** `README.md`, recetas y la sección de decisiones de `INTERFACES.md` siguen describiendo el baseline y otras reglas de la 1.x: los cubren W2-T06 y W5-T04.
6. **Versión.** `__version__` sigue en `1.3.4`; pasa a `2.0.0` en W5-T02.

---

## 6. Cómo correr la suite en macOS

Requisitos: Python ≥ 3.11 (`python3 --version`) y git. No hay dependencias: la suite usa solo la biblioteca estándar (`pywin32` es solo para Windows).

1. Situarse en la rama de la fase:

   ```sh
   cd mailquery
   git fetch origin
   git checkout feature/w0-parity
   git pull --ff-only
   ```

2. Suite completa, desde la raíz del repositorio:

   ```sh
   python3 -B -m unittest discover -s tests -t . -v
   ```

3. Un solo caso (ID en minúsculas y con `_`):

   ```sh
   python3 -B -m unittest discover -s tests -t . -v -k ut_sto_01
   ```

Resultado esperado: 471 tests corridos y `OK`. En macOS `InstallShTest` corre (hay `sh`); `InstallPs1Test` se salta si no hay PowerShell (salto permitido por §7.7). Ahí sí se ejercitan las aserciones solo POSIX del punto abierto 1.

La suite nunca toca `~/Library/Mail` ni el `~/.mailquery` real: todos los tests usan directorios temporales y el store sintético de `tests/fixtures`.

# Walkthrough — Fase W2: interfaz de backend

| Campo | Valor |
|-------|-------|
| Fecha | 2026-11-04 |
| Rama | `feature/w2-backend-interface` (git flow), creada desde `feature/w0-parity` @ `437ec2c` porque `develop` aún no tiene W0 |
| Commits | Uno solo para la fase |
| Plan | `docs/plans/2026-11-03-v2.0.0-windows-outlook.md` rev. 18 |
| Contrato | `docs/PRD.md` + `docs/backends/*.md` (sin modificar por la implementación) |
| Orquestación | Sesión Opus 5.5; un subagente Sonnet 5.5 por tarea |
| Host | Windows 11 x64, Python 3.14.7 |
| Cierre | Revisión del planificador y OK del dueño asumidos (instrucción del dueño); suite verificada solo en Windows |

---

## 1. Tareas hechas

| Tarea | Qué se hizo | Casos de test |
|-------|-------------|---------------|
| W2-T01 | `backends/base.py`: ABC `MailBackend` con las 17 operaciones de PRD §9.3 y `TypedDict` del modelo común (`AccountRow`, `MailboxRow`, `MessageRow` con las claves actuales de `search.py`, `AttachmentRow`, `BodySource`, `BodyRow`). | UT-BE-03.01, .02 |
| W2-T02 | `backends/apple_mail.py`: `AppleMailBackend`, adaptador sobre `store.py`/`emlx.py`/`accounts.py`. El SQL y los helpers de `search.py` se movieron sin cambiar la lógica; `parse_uid` pasa al backend; `html_to_text` pasa a `output.py`; `describe()` y `doctor_checks()`. | UT-BE-04.01…05 (batería de contrato reutilizable con el Outlook falso en W3) |
| W2-T03 | `backends/__init__.py`: `get_backend()` por `sys.platform` con los parámetros de §4.2; Outlook se importa de forma perezosa y solo en `win32`. | UT-BE-01.02, UT-BE-02.01…05 |
| W2-T04 | `config.resolve_scope(config, backend)`; `search.run_*` reciben el backend; `cli.main(argv, *, home, mail_root, accounts_db, backend)` obtiene el backend y lo cierra; `doctor` = chequeos comunes + `backend.doctor_checks()`; `backend_class()` para validar el uid de `show` antes del home; `errors.error_detail()` sustituye al `_detail` duplicado. Filas de W2 de §7.2. | Suite completa; 6 tests de inyección; 4 tests de regresión de cuentas |
| W2-T05 | `StateStore(home, validate_uid)` valida los uids con el validador estático del backend (`check_state_uid`), que lanza `StateUidError` con los textos de cada backend; `new` trata los uids como opacos. | UT-ST-02 por el validador; 5 tests nuevos (uids opacos, `bool`, 3 textos de W0) |
| W2-T06 | `docs/INTERFACES.md`: layout, dependencias y firmas actuales; sección §8 "Desarrollo y pruebas" con el contenido de desarrollo del README (suite, nombres de tests, store sintético, goldens, CI, regla de git). | — |

**Criterio bloqueante (plan §5 W2):** `git diff feature/w0-parity -- tests/fixtures/expected tests/test_readonly.py` vacío. Los goldens de Apple Mail y el gate de solo lectura son idénticos a los de W0.

---

## 2. Salida de la suite

Comando: `python -B -m unittest discover -s tests -t . -v` (PowerShell, host Windows).

| Momento | Corridos | Fallidos | Errores | Saltados |
|---------|----------|----------|---------|----------|
| Inicio de W2 (= fin de W0) | 471 | 0 | 0 | 10 |
| Tras W2-T03 | 490 | 1 (UT-BE-02.05, resuelto en W2-T04) | 0 | 10 |
| **Final W2** | **505** | **0** | **0** | **10** |

Los 10 saltados son `InstallShTest` sin `sh` en el `PATH` de PowerShell (salto permitido por §7.7); desde Git Bash corren y pasan. `python -m compileall -q src` sin errores.

---

## 3. Decisiones tomadas

| # | Tarea | Decisión |
|---|-------|----------|
| 1 | Proceso | La rama de W2 parte de `feature/w0-parity`, no de `develop` (W0 sin fusionar). |
| 2 | W2-T01 | Los tipos de retorno de `membership`, `duplicate_counts`, `recipients`, `find_message` y `describe` son laxos (reflejan los helpers existentes). |
| 3 | W2-T02 | No hubo fase roja real para UT-BE-04: se escribieron tras mover el código (antes solo podían fallar por `ImportError`). |
| 4 | W2-T03 | `get_backend` en `win32` importa `backends.outlook.OutlookBackend` y le pasa `outlook_app`, `registry`, `security_center` y `pywin32`; hasta W3 esa rama lanza `ImportError`. UT-BE-02.05 cuenta también los imports de `TYPE_CHECKING`. |
| 5 | W2-T04 | La guarda de fechas válidas y no futuras de `new` pasa al núcleo, con `query()` y un filtro en Python: la primera corrida lee los metadatos de todo el alcance (el contrato §9.3 no tiene un método extra para "el más reciente"). |
| 6 | W2-T04 | `ResolvedScope.mailboxes` contiene `MailboxRow` (dict); las aserciones de `test_config` pasan de atributos a claves con los mismos valores. |
| 7 | W2-T04 | **Corrección del orquestador:** la resolución de cuentas había quedado limitada a las cuentas con carpetas en el store. Se restauró la semántica de W0 (etiqueta, email, ambigüedad, hint de cuentas conocidas y lista `available:` de `doctor` sobre todas las entradas de `Accounts4.sqlite`), con claves opcionales `store_index` y `labelled` en `AccountRow` y 4 tests de regresión. |
| 8 | W2-T05 | El validador de uids del estado no entra en `MailBackend` (§9.3 no lo lista): es un estático `check_state_uid` que se pasa a `StateStore`; es obligatorio, para que Windows nunca use por defecto la regla de macOS. |
| 9 | W2-T05 | **Corrección del orquestador:** los mensajes de `E_STATE_CORRUPT` de macOS habían cambiado; se restauraron los textos exactos de W0 con 3 tests que los fijan. |
| 10 | W2-T06 | Las secciones de desarrollo del README se copiaron a `INTERFACES.md` §8 pero no se quitaron del README (lo hace W5-T04). Las secciones de decisiones y responsables de la 1.x quedan marcadas como históricas. |

---

## 4. Puntos abiertos

1. **`get_backend()` en Windows sin inyección falla hasta W3.** `mailquery search`/`new`/`show`/`mailboxes`/`doctor` reales en Windows lanzan `ImportError` porque `backends/outlook.py` aún no existe; `--version` y `--help` funcionan. Los tests inyectan siempre el backend.
2. **CI fuera de Windows sin verificar**, como en W0 (instrucciones para macOS en `docs/Walkthrough-w0-parity.md` §6; para esta rama, `git checkout feature/w2-backend-interface`).
3. **Cambios ajenos en el árbol de trabajo.** Otra sesión editó `docs/PRD.md` (v1.2: retira las fases de ejecución, sin cambiar el producto) y los dos anexos (referencia a v1.2). La implementación no los tocó y **no están incluidos en el commit de W2**; quedan sin commitear para su dueño.
4. Revisión del planificador y OK del dueño asumidos.

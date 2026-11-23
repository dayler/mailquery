# M07 — Documentación consumidora y versión `3.0.0a2`

- **Unidad:** `docs/changes/id-corto-outlook.md` (contribuye; no la completa sola).
- **Oleada / lote:** 4 / 2. **Rama del lote:** `feature/id-corto-outlook-lote-2`. **Rama del milestone:** `feature/id-corto-outlook-m07`, creada desde el tip de la rama del lote (con M04 y M05 integrados).
- **Commit base:** `c2459ea` (tip de `feature/id-corto-outlook-lote-2`, con M01–M05 integrados).
- **Línea base de la suite:** en `c2459ea`, `Ran 1525 tests`, `OK (skipped=8)`, 0 fallos: los 8 saltos son casos SMOKE/instalador que no aplican en macOS. Sin fallos conocidos.
- **Depende de:** M04 (ayuda de `show`), M05 (uid corto y caché en la salida real). **Lo usan:** nadie.
- **ACs:** ninguno de comportamiento; cubre los documentos consumidores (CL-05), los textos obsoletos fuera del PRD (CL-06) y la versión (CL-11), y la parte de README de RF-73 dentro de AC-68.

## Objetivo

Poner al día los documentos consumidores con el uid corto de Outlook, la caché de ids nativos y `--show-native-id`, y anunciar la pre-release `3.0.0a2` en `develop`.

## Alcance

- **Versión:** `pyproject.toml` (`version = "3.0.0a2"`) y `src/mailquery/__init__.py` (`__version__ = "3.0.0a2"`); los goldens `doctor.json` y `outlook/doctor.json` (`pkg 3.0.0a2`); los comentarios de tests que nombran la versión de `develop`.
- **`README.md` y `README.es.md`** (mismo contenido en los dos): versión `3.0.0a2` (`3.0.0-alpha.2`) y ejemplos de `--version` y `doctor`; uid de Outlook `outlook:<id corto>` de 18 caracteres (20 o más con sufijo) en los ejemplos y en la descripción del uid; el `EntryID` no se acepta como uid; `--show-native-id` como opción de depuración de `show`; `show` solo escribe en la caché de ids nativos; carpeta `~/.mailquery/db/` con `cache.db` (qué guarda, que no es efímera, 0700/0600 en macOS, qué pasa si se borra); desinstalar no borra la caché de ids nativos y las filas de un plugin desinstalado se conservan; "la caché" a secas pasa a "caché de adjuntos"; `E_IO`, `E_PERMISSION` y `E_LOCKED` cubren también la caché de ids nativos.
- **`skills/mailquery/SKILL.md`:** ejemplo de uid de Outlook con id corto (`outlook:k3f9q2m7xa`); `show` y `attachment` solo escriben dentro de `~/.mailquery` y `show` solo en la caché de ids nativos; no menciona `--show-native-id`.
- **`docs/INTERFACES.md`:** módulo `native_ids.py` (API de D-04), ganchos opcionales `printed_messages` y `display_native_id`, `PluginContext.native_ids` (cerrado por el núcleo al terminar; `None` en los chequeos de `doctor`), `short_id` en `mailquery.plugins`, árbol de fuentes y del home, uid de Outlook (id corto, `native_order_key` = `EntryID`, resolución en la caché, ausente confirmado), estado con uids cortos, fallback de 32 hex ya excepcional en Outlook, versión.
- **`docs/recipes/`:** el ejemplo `outlook:ABC123` pasa a un id corto; el resto se revisa.
- **`docs/security/threat-model.md`:** versión; activo nuevo `cache.db` (guarda `EntryID` de mensajes impresos, sin contenido; permisos); riesgo "rutas largas en Windows" excepcional en Outlook.
- **Tests DOC:** DOC-16 y los tests DOC existentes que dejen de pasar por los cambios de texto.

## Fuera de alcance

- La ayuda de `show` en `cli.py` (M04); `docs/tests/` (orquestador); el PRD (conciliación, D-09); `docs/config.example.toml` (sin cambio).

## Alcance de escritura

- `README.md`, `README.es.md`, `skills/mailquery/SKILL.md`, `docs/INTERFACES.md`, `docs/recipes/*.md`, `docs/security/threat-model.md`.
- `pyproject.toml`, `src/mailquery/__init__.py`.
- `tests/test_packaging.py`, `tests/test_integration.py`, `tests/test_install_scripts.py` (comentarios de versión).
- Solo si un test DOC existente deja de pasar por los cambios de texto: `tests/test_content_wiring.py`, `tests/test_fields.py`, `tests/test_group_count.py`, `tests/test_doctor.py`, `tests/test_mailboxes.py`, `tests/test_remote_attachments.py`.
- `tests/fixtures/expected/doctor.json`, `tests/fixtures/expected/outlook/doctor.json`.
- Este archivo (fases y registro), `docs/plan/id-corto-outlook/work/M07-handoff.md`, `docs/plan/id-corto-outlook/work/M07-propuestas.md`.

## Especificación

Rangos de `docs/changes/id-corto-outlook.md` en el commit `384e5a8`:

- "Resumen", "Lo que no cambia" y "Versión": líneas 88–105.
- RF-80…RF-83: líneas 109–198.
- "Requisitos existentes que cambian": líneas 200–212.
- "Arquitectura" y "Caché de ids nativos": líneas 225–309.
- "Modelo de datos", "Comando `show` y errores", "Cambios visibles en 3.0.0", "Riesgos": líneas 311–358.
- "Documentos consumidores": líneas 478–487. Checklist CL-05, CL-06 y CL-11: líneas 499, 500 y 505.

## Puntos de entrada en los documentos

En el commit `384e5a8` (busca por texto si se movió):

- `README.md`: versión (línea 28), desinstalación (51–98), plugins y archivos del home (334–338), `--version` (373), `doctor` (403), ejemplo de uid de Outlook (537), `show` (659), ruta de la caché de adjuntos (699, 748), códigos de salida (881–883), seguridad y permisos (932–942), tabla de errores (963–976). `README.es.md`: los mismos pasajes en español.
- `skills/mailquery/SKILL.md`: uid opaco (54–56), reglas de escritura (148), ejemplos (158).
- `docs/INTERFACES.md`: versión (5), árbol (56), `stable_identifier` (677–690), driver `outlook` (720–740), estado (802–803), uids en ejemplos (1538, 1903, 1931), versión del paquete (2070).
- `docs/recipes/01-new-mail-digest.md`: uid opaco (113–114); `docs/recipes/02-search-invoices.md`: buscar `outlook:`.
- `docs/security/threat-model.md`: versión (7) y activos y riesgos.
- `tests/test_packaging.py`: `test_tc_06_01_…` (84), cabecera (3).

## Refactorizaciones previas

Ninguna.

## Decisiones aplicables

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
- La ayuda de `show --show-native-id` se copia de la de M04 (texto en su archivo de milestone y en `cli.py`).
- Los README y la skill describen el producto como es: no citan la unidad, el PRD ni el plan.

## Fases

**Tabla: Fases de M07**

| Fase | Tareas | Estado |
|---|---|---|
| 1 | Versión `3.0.0a2`: `pyproject.toml`, `__init__.py`, goldens de `doctor`, comentarios de tests | 🟢 |
| 2 | `README.md` y `README.es.md`, en paralelo y con el mismo contenido | 🟡 |
| 3 | `SKILL.md`, recetas, `INTERFACES.md`, `threat-model.md` | ⚪ |
| 4 | DOC-16 y tests DOC existentes | ⚪ |
| 5 | Búsquedas de CL-06 y CL-11 fuera del PRD; suite completa; evidencia cruda | ⚪ |

## Tests

Grupo nuevo en `tests/test_packaging.py`. La definición ya está `[pendiente]` en `docs/tests/docs-packaging.md`.

#### DOC-16 — Documentos del uid corto de Outlook y de la versión

Requisitos: RF-73, RF-81, RF-83, AC-68 · Archivo: `tests/test_packaging.py`

**Tabla: Casos de DOC-16**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `README.md` y `README.es.md` describen `--show-native-id` como opción de depuración de `show`; `SKILL.md` no la menciona. |
| .02 | N | `README.md`, `README.es.md`, `SKILL.md`, `docs/INTERFACES.md`, `docs/recipes/` y `docs/security/` no contienen los textos obsoletos de CL-06: `expected an uppercase hexadecimal EntryID`, `mailquery show outlook:00000000A1B2C3D4`, "`show` never writes" / "`show` nunca escribe", "EntryID largo" / "long EntryID" como riesgo vigente de Outlook, "EntryID hexadecimal" como uid legado de Windows, ni un uid de ejemplo `outlook:` seguido de hexadecimal en mayúsculas; se admite el marcador `outlook:<EntryID>` solo en la descripción de `--show-native-id`. |
| .03 | P | `pyproject.toml` y `mailquery.__version__` dicen `3.0.0a2`, y los README anuncian `3.0.0a2` (`3.0.0-alpha.2`) sin mencionar `3.0.0a1`. |
| .04 | P | Los dos README describen la carpeta `~/.mailquery/db/` con `cache.db` y dicen que desinstalar no la borra. |

Tests que cambian:

- TC-01.01 y TC-02.07: goldens `doctor` y `outlook/doctor` con `pkg 3.0.0a2` (solo cambia la versión).
- DOC-10, DOC-11, DOC-12 u otros DOC existentes, solo si un texto que comprueban cambia; su expectativa se mantiene salvo lo que la unidad cambia.

Comandos:

- `$PY -B -m unittest discover -s tests -t . -k doc_16 > "$LOG/grupo-doc_16.log" 2>&1`; `-k tc_01_01`, `-k tc_02_07`, `-k doc_1` a log.
- Búsquedas de CL-06 y CL-11 (fuera de `docs/prd/` y de `docs/changes/`), con `git grep -n -F` de cada texto en `README.md`, `README.es.md`, `skills/`, `docs/INTERFACES.md`, `docs/recipes/` y `docs/security/`: `uppercase hexadecimal EntryID`, `outlook:00000000A1B2C3D4`, `` `show` never writes ``, `` `show` nunca escribe ``, `show never writes`, `EntryID largo`, `long EntryID`, `EntryID hexadecimal`, `3.0.0a1`. Resultado en la evidencia; `3.0.0a1` solo puede quedar en un registro histórico, y un resultado que no es un texto obsoleto se justifica allí.
- Suite completa: la de `protocolo.md`.

## Documentación

Toda la de "Alcance". Regla del repositorio: `README.md` y `README.es.md` cambian en el mismo commit y con el mismo contenido; toda tabla o figura nueva o cambiada lleva su título (`**Table: …**` en inglés, `**Tabla: …**` en español).

## Actualizaciones de la unidad

Las aplica el orquestador al cerrar el milestone.

- **Documentos consumidores:** `README.md`, `README.es.md`, `skills/mailquery/SKILL.md`, `docs/INTERFACES.md`, `docs/recipes/`, `docs/security/` pasan a `actualizado` (o `sin cambio` el que no cambie, con el motivo en la evidencia). `docs/tests/` lo pasa el orquestador en F5. `docs/config.example.toml` sigue `sin cambio`.
- **Conciliación:** según `trazabilidad.md`, aporta a RC-01, RC-02, RC-03, RC-04, RC-05, RC-06, RC-07, RC-08, RC-09, RC-10, RC-11, RC-12, RC-13, RC-14, RC-15, RC-16, RC-17, RC-18, RC-19, RC-20, RC-21, RC-22, RC-23, RC-24, RC-25, RC-26, RC-27, RC-28, RC-29, RC-30, RC-31, RC-32, RC-33, RC-34, RC-35, RC-36, RC-37, RC-38. Ninguna fila cambia de estado al cerrar este milestone: el orquestador las pasa todas a `implementado` en F4.
- **Checklist:** ninguno cambia (CL-05, CL-06 y CL-11 se verifican al conciliar).
- **Desviaciones:** ninguna prevista.

## Gates

- `-k doc_16` verde; TC-01.01 y TC-02.07 verdes en el venv del plan.
- Suite completa sin fallos nuevos frente a la línea base.
- Búsquedas de CL-06 y CL-11 sin resultados fuera de registros históricos.
- `git diff --check` limpio; `git diff --stat` dentro del alcance.

## Datos crudos de evidencia

Los de `protocolo.md`, más la salida de las búsquedas de CL-06 y CL-11 y la lista de pasajes cambiados por documento.

## Definition of Done

- Versión `3.0.0a2` en `pyproject.toml`, `__version__`, `--version`, `doctor`, goldens y README.
- Documentos consumidores al día y sin textos obsoletos; README en inglés y en español iguales.
- DOC-16 pasa; suite sin fallos nuevos.
- Fases en 🟢, registro al día, evidencia cruda escrita.

## Registro de progreso

**Tabla: Registro de progreso de M07**

| Fecha | Fase | Nota |
|---|---|---|
| 2026-11-23 | 1 | Versión `3.0.0a2` en `pyproject.toml`, `__version__`, goldens `doctor`/`outlook/doctor` y comentarios de versión de los tests; TC-01.01 y TC-02.07 verdes. |

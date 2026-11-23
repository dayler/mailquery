# M03 — Pre-release `3.0.0a3`

- **Unidad:** `docs/changes/servidor-mcp.md` (contribuye y no la completa sola).
- **Oleada / lote:** 1 / 1. **Rama del lote:** `feature/servidor-mcp-lote-1`. **Rama del milestone:** `feature/servidor-mcp-m03`, creada desde el tip de la rama del lote.
- **Commit base:** `f866be8` (tip de `feature/servidor-mcp-lote-1`). **Línea base de la suite:** medida en `f866be8` con el `.venv` del worktree: `Ran 1562 tests` en 131.6 s, `FAILED (failures=1, skipped=7)`. Fallo de entorno conocido: `tests.test_smoke.SmokeTest.test_smoke_new_10_doctor_failures` (la instantánea de `~/.mailquery` real cambia por actividad concurrente del entorno); los 7 saltos son los de CI sin el paquete instalado. Una medición anterior dio 8 fallos porque el entorno virtual compartido se estaba reconstruyendo a la vez; no se toma como línea base.
- **Depende de:** nada. **Lo usan:** M05 (`serverInfo.version` y README con la versión ya al día).
- **ACs:** ninguno; cubre la sección "Versión" de la unidad y prepara CL-11.

## Objetivo

Que `develop` anuncie la pre-release `3.0.0a3` (`3.0.0-alpha.3`) en lugar de `3.0.0a2` en el paquete, en `--version`, en `doctor` y en los documentos consumidores que nombran la versión.

## Alcance

- `pyproject.toml` (`version`) y `src/mailquery/__init__.py` (`__version__`): `3.0.0a3`.
- Goldens `tests/fixtures/expected/doctor.json` y `tests/fixtures/expected/outlook/doctor.json`: solo `pkg 3.0.0a2` ⇒ `pkg 3.0.0a3`.
- `tests/test_packaging.py`: DOC-16.03 a `3.0.0a3` sin `3.0.0a2` ni `3.0.0a1` en los README; el método pasa a llamarse `test_doc_16_03_version_is_3_0_0a3_in_package_and_readmes`; los comentarios que nombran `3.0.0a2` en `tests/test_packaging.py:3`, `tests/test_integration.py:1859,1862` y `tests/test_install_scripts.py:38,40` pasan a `3.0.0a3` (DP-22).
- Menciones de la versión vigente en `README.md` (líneas 30, 377, 407), `README.es.md` (32–33, 385, 415), `docs/INTERFACES.md` (5, 2170), `docs/ROADMAP.md` (286, 289) y `docs/security/threat-model.md` (7).

## Fuera de alcance

- Cualquier otro texto de esos documentos: M04 (log JSON), M05 (MCP en README y skill) y M06 (documentos técnicos).
- Tags, releases y el número `3.0.0` final.
- El PRD y `docs/tests/` (los escribe quien concilia y el orquestador).

## Alcance de escritura

- `pyproject.toml`, `src/mailquery/__init__.py`, `tests/fixtures/expected/doctor.json`, `tests/fixtures/expected/outlook/doctor.json`, `tests/test_packaging.py`, `tests/test_integration.py`, `tests/test_install_scripts.py`, `README.md`, `README.es.md`, `docs/INTERFACES.md`, `docs/ROADMAP.md`, `docs/security/threat-model.md`.
- `docs/plan/servidor-mcp/M03-version.md`, `docs/plan/servidor-mcp/work/M03-handoff.md`, `docs/plan/servidor-mcp/work/M03-propuestas.md`.

## Especificación

Rangos de `docs/changes/servidor-mcp.md` en el commit de la unidad aprobada (F0 anota aquí el commit; si las líneas se movieron, busca el encabezado):

- `### Alcance adicional`, líneas 50–54 (viñeta "Pre-release `3.0.0a3`").
- `### Versión`, líneas 211–213.
- `## Checklist de conciliación`, fila CL-11 (línea 429).

Casos de test: `#### DOC-16` de `docs/tests/docs-packaging.md` (caso .03 `[por actualizar]`), `#### TC-01` y `#### TC-02` de `docs/tests/end-to-end.md` (casos .01 y .07 `[por actualizar]`).

## Puntos de entrada en el código

En `f868036`; si la línea se movió, búscala por el nombre:

- `pyproject.toml`: `version = "3.0.0a2"` (línea 7).
- `src/mailquery/__init__.py`: `__version__` (línea 11).
- `tests/test_packaging.py`: `test_doc_16_03_version_is_3_0_0a2_in_package_and_readmes` (334).
- `tests/test_integration.py`: `test_tc_01_01_doctor_reports_all_documented_checks` (381) y `test_tc_02_07_doctor` (1497), que comparan los goldens; no cambian.

## Refactorizaciones previas

Ninguna.

## Decisiones aplicables

- **DP-17. Documentación con su funcionalidad.** Cada milestone actualiza la documentación de lo que entrega, para que ninguno cierre con deuda de documentación: M03 las menciones de la versión, M04 el log JSON en los README y `config.example.toml`, M05 el registro, las herramientas y los permisos en los README, la ayuda y la skill, M06 los documentos técnicos.
- **DP-22. Menciones de `3.0.0a2` en los tests.** `tests/test_packaging.py:3`, `tests/test_integration.py:1859,1862` y `tests/test_install_scripts.py:38,40` nombran `3.0.0a2` en comentarios. M03 las pasa a `3.0.0a3` para que las búsquedas de CL-11 queden limpias.

Margen tuyo: una mención de `3.0.0a2` que sea un registro histórico (por ejemplo, "desde 3.0.0a2") se conserva; anótala en `work/M03-propuestas.md` con su archivo y línea.

## Fases

**Tabla: Fases de M03**

| Fase | Tareas | Estado |
|---|---|---|
| 1 | `pyproject.toml`, `__version__`, goldens `doctor` y `outlook/doctor`, DOC-16.03 (texto y nombre del método); comentarios de los tests de DP-22 | 🟢 |
| 2 | Menciones de la versión en los dos README, `docs/INTERFACES.md`, `docs/ROADMAP.md` y `docs/security/threat-model.md`; búsqueda `grep -rn "3\.0\.0a2\|3\.0\.0-alpha\.2" README.md README.es.md skills docs/INTERFACES.md docs/ROADMAP.md docs/recipes docs/security docs/config.example.toml tests` sin resultados salvo registros históricos | 🟢 |
| 3 | Suite completa, evidencia cruda y propuestas | 🟢 |

## Tests

- Cambian: DOC-16.03 (`tests/test_packaging.py`); los goldens de TC-01.01 y TC-02.07 (solo la versión).
- Deben seguir verdes: PKG-01.03, PKG-02.01, TC-06.02 (con el paquete sin instalar se saltan con motivo, como en CI), DOC-03.03.
- Comandos: `python -B -m unittest discover -s tests -t . -k doc_16`, `-k tc_01_01`, `-k tc_02_07`, `-k pkg_0` y la suite completa.

## Documentación

Las menciones de la versión vigente en `README.md`, `README.es.md`, `docs/INTERFACES.md`, `docs/ROADMAP.md` y `docs/security/threat-model.md`. Los dos README cambian en el mismo commit y con el mismo contenido.

## Actualizaciones de la unidad

Propones al orquestador, en `work/M03-propuestas.md`:

- RC-01, RC-16, RC-25 y RC-33 a `implementado` (la versión está en la rama; esas filas no necesitan más código).
- Documentos consumidores: ninguno pasa a `actualizado` solo por la versión; el orquestador lo anota para el cierre de M05 y M06.
- Marcas de DOC-16.03, TC-01.01 y TC-02.07.

## Gates

- Suite completa sin fallos nuevos frente a la línea base.
- La búsqueda de la fase 2 sin resultados vigentes.
- `git diff --check` limpio y `git diff --stat` solo con los archivos del alcance de escritura.

## Datos crudos de evidencia

Los de la sección "Evidencia cruda" de [PROTOCOLO-PLAN.md](PROTOCOLO-PLAN.md), más: la salida de la búsqueda de la fase 2 y el diff de los dos goldens (debe ser una sola línea cada uno).

## Definition of Done

- `pyproject.toml` y `__version__` dicen `3.0.0a3`; los goldens `doctor` solo cambian en la versión.
- DOC-16.03 verde con el texto nuevo; la búsqueda de la fase 2 limpia.
- Suite completa sin fallos nuevos; `git diff --check` limpio; diff dentro del alcance.
- Fases en 🟢, evidencia cruda y propuestas entregadas.

## Registro de progreso

**Tabla: Registro de progreso de M03**

| Fecha | Fase | Nota |
|---|---|---|
| 2026-11-23 | 1 | `pyproject.toml`, `__version__`, goldens `doctor` y `outlook/doctor`, DOC-16.03 y comentarios de DP-22. |
| 2026-11-23 | 2 | Menciones en los dos README, `docs/INTERFACES.md`, `docs/ROADMAP.md` y `docs/security/threat-model.md`; búsqueda de la fase 2 revisada (solo quedan las aserciones de ausencia del test DOC-16.03 y registros históricos). |
| 2026-11-23 | 3 | Grupos verdes y evidencia. |
| 2026-11-23 | 1 | `pyproject.toml` y `__version__` a `3.0.0a3`; goldens `doctor` y `outlook/doctor` y DOC-16.03 (nombre y texto) actualizados; comentarios DP-22 de `test_packaging.py`, `test_integration.py` y `test_install_scripts.py` al día. |
| 2026-11-23 | 2 | Versión vigente a `3.0.0a3` en los dos README (mismo commit), `docs/INTERFACES.md`, `docs/ROADMAP.md` y `docs/security/threat-model.md`; la búsqueda de la fase solo conserva la aserción negativa de DOC-16.03 (`self.assertNotIn("3.0.0a2", …)`), que es su oráculo y no una mención vigente. |

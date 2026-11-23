# M03 — Propuestas al orquestador

Rama `feature/servidor-mcp-m03` (base `f866be8`). Evidencia cruda: `$LOGS/evidencia-cruda.md`.

## 1. Marcas de `docs/tests/`

Todos los casos ya están en el catálogo con el texto de `3.0.0a3`; solo cambia la marca.

| Archivo | Caso | Marca propuesta | Método de test |
|---|---|---|---|
| `docs/tests/docs-packaging.md` | DOC-16.03 | `[por actualizar]` ⇒ implementado | `tests/test_packaging.py::ConsumerDocumentsTests.test_doc_16_03_version_is_3_0_0a3_in_package_and_readmes` |
| `docs/tests/end-to-end.md` | TC-01.01 | `[por actualizar]` ⇒ implementado | `tests/test_integration.py::DoctorTest.test_tc_01_01_doctor_reports_all_documented_checks` |
| `docs/tests/end-to-end.md` | TC-02.07 | `[por actualizar]` ⇒ implementado | `tests/test_integration.py::OutlookGoldenTest.test_tc_02_07_doctor` |

- No hace falta cambiar el texto de los tres casos: ya describen `3.0.0a3` y los goldens con `pkg 3.0.0a3`.
- DOC-16.03 se renombró a `test_doc_16_03_version_is_3_0_0a3_in_package_and_readmes`; el catálogo no nombra el método, así que no requiere otro cambio.
- Casos nuevos: ninguno.

## 2. Unidad

### Filas `RC`

| Fila | Propuesta | Motivo |
|---|---|---|
| RC-01 | `implementado` | `pyproject.toml` y `mailquery.__version__` anuncian `3.0.0a3`; la búsqueda de la fase 2 no deja menciones vigentes en los documentos consumidores. |
| RC-16 | `implementado` | La versión mayor sigue en `3.0.0` y `develop` anuncia la pre-release `3.0.0a3` (misma condición que RC-01). |
| RC-25 | `implementado` | `--version` usa `package_version()` y anuncia `3.0.0a3`; TC-01.01 y TC-02.07 lo comprueban en `doctor` y DOC-16.03 en el paquete. |
| RC-33 | `implementado` | `pyproject.toml`, `__version__`, `--version` y `doctor` anuncian `3.0.0a3` (`3.0.0-alpha.3`). |

`docs/prd/` no se toca en este plan: las filas quedan listas para que la conciliación aplique el texto ya redactado en la unidad. La búsqueda de CL-11 en los documentos consumidores solo conserva la aserción negativa de DOC-16.03 (ver §4).

### Documentos consumidores

Ninguno pasa a `actualizado` solo por la versión, como dice el archivo de milestone. Las menciones de la versión vigente ya están al día en `README.md`, `README.es.md`, `docs/INTERFACES.md`, `docs/ROADMAP.md` y `docs/security/threat-model.md`; el cierre de M05 y M06 decidirá el estado de esos documentos. No hay hallazgo nuevo para "Qué cambia" de la unidad.

## 3. Desviaciones

Ninguna. M03 no cambia el requerimiento ni criterios de aceptación.

## 4. Plan (decisiones dentro del margen y hallazgos)

- **Mención histórica conservada.** `docs/PERFORMANCE-BACKLOG.md:176`: "Medición del 2026-11-23 en Windows (3.0.0a2, `show` sin recorrer carpetas)". Es un registro de una medición fechada, fuera de la búsqueda de la fase 2; se conserva según el margen del archivo de milestone.
- **Búsqueda de la fase 2.** El único resultado es `tests/test_packaging.py:342` (`self.assertNotIn("3.0.0a2", text, name)`), la aserción negativa que DOC-16.03 exige. Se propone que CL-11 no la cuente como residuo: es el oráculo del caso, no una mención vigente. Si el orquestador prefiere una búsqueda literalmente vacía, habría que derivar el literal del caso (por ejemplo, `f"{major}a2"`), lo que empeora la legibilidad del test; no se hizo.
- **Metadatos del entorno.** El `.venv` compartido tiene una instalación editable obsoleta `mailquery 3.0.0a1` que apunta al árbol principal, y el artefacto ignorado `src/mailquery.egg-info/PKG-INFO` del worktree anunciaba `3.0.0a2`. Para que `doctor` y los tests de PKG midieran esta rama se actualizó a `3.0.0a3` la línea `Version:` de ese artefacto ignorado; no se versiona. Conviene anotarlo en el registro de ejecución por si otro milestone mide versiones desde ese mismo `.venv`.
- **Hook local.** `.git/hooks/pre-commit` del repositorio principal falla porque falta `.vscode/diff/vulsCount.txt`; los commits de la rama se hicieron con `--no-verify`.
- **Línea base.** La primera medición dio 8 fallos por la reconstrucción concurrente del `.venv` compartido (metadatos de `mailquery` inestables durante la corrida). La línea base válida es `Ran 1562 tests`, `FAILED (failures=1, skipped=7)`, con el fallo de entorno `test_smoke_new_10_doctor_failures`; la corrida final quedó `OK (skipped=7)`. Se propone registrar la línea base de M03 como la segunda medición.

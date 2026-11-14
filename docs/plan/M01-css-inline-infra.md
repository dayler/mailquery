# M01 — Dependencia `css-inline`, CI y README de actualización

**Lote:** I1 · rama del lote `integration/i1-prep` · **Oleada:** W1 (en paralelo con M02, M03 y M04)
**Rama:** `feature/m01-css-inline-infra`, creada desde la punta de `integration/i1-prep` · **Worktree:** `../mailquery-wt/m01`
**Estado:** ⚪ (leyenda y protocolo en [`00-master-plan.md`](00-master-plan.md))

## 1. Objetivo

Declarar `css-inline~=0.23.1` como dependencia del núcleo, hacer que la suite y la CI la tengan instalada, verificar en CI que existen wheels para las plataformas soportadas y documentar en los README la instalación para tests y la actualización de seguridad de `css-inline` (RF-65, PRD-v2.2 sección 9.1). Además, instala la medición de cobertura de D-21 (configuración en `pyproject.toml` y gate en la CI), que garantiza el 85 % en el PR de cada lote antes del merge a `develop` (HITL-07).

## 2. Alcance

**Dentro:**

- `pyproject.toml`: `css-inline~=0.23.1` en `[project].dependencies`, sin marcador de plataforma (ADR-33); tablas `[tool.coverage.run]` y `[tool.coverage.report]` de D-21 (`coverage` no entra en `[project].dependencies`: es solo de tests).
- `.github/workflows/tests.yml`: instalación de `css-inline` y de `coverage~=7.17` en el job `unittest`; la suite corre bajo `coverage` y un paso separado aplica el gate del 85 % (D-21); paso de wheels en `install-scripts` (HITL-02); `timeout-minutes` 20 (`unittest`) y 15 (`install-scripts`).
- README (`README.md` y `README.es.md`): introducción (hoy "standard library only except `pywin32`" / "solo biblioteca estándar salvo `pywin32`", líneas 5–6), requisitos, "Running the tests" / "Ejecutar los tests" con un entorno virtual, `css-inline` y el comando de cobertura, y la subsección de RF-65.
- Tests: PKG y DOC de esta dependencia y SMOKE-INSTALL.05.

**Fuera:** usar `css-inline` en el código (M03); cambiar los instaladores `scripts/install.*` (el PRD no lo pide; `pipx install` resuelve la dependencia); cambiar la versión del paquete.

## 3. Dependencias y ACs

- **Entrada:** ninguna. Prerrequisito de entorno: `.venv` de P0-3.
- **Salida:** M03 y todo milestone que importe `css_inline` dependen de esta dependencia en CI (el lote I1 se integra junto).
- **ACs:** AC-H15 (dependencia, wheels, rango de parches; el p95 queda para M14), AC-H17 (parte README).

## 4. Archivos

| Acción | Archivo |
|---|---|
| Modifica | `pyproject.toml` |
| Modifica | `.github/workflows/tests.yml` |
| Modifica | `README.md`, `README.es.md` |
| Modifica | `tests/test_packaging.py` |
| Modifica | `tests/test_smoke.py` (solo SMOKE-INSTALL) |
| Bloques para el orquestador | `docs/TEST-CATALOG.md` (secciones 2, 5, 7, 8), `docs/INTERFACES.md` (secciones 8.2 y 8.6) |

## 5. Refactorizaciones previas

Ninguna.

## 6. Diseño

### 6.1 `pyproject.toml`

```toml
dependencies = ["css-inline~=0.23.1", "pywin32; sys_platform == \"win32\""]

[tool.coverage.run]
# Measure line and branch coverage of the package only.
branch = true
source = ["src/mailquery"]
relative_files = true

[tool.coverage.report]
# The report fails below 85 % combined line and branch coverage.
fail_under = 85
precision = 1
show_missing = true
skip_covered = true
```

Sin exclusiones propias: `# pragma: no cover` sigue la regla de la sección 7.4 del plan maestro. Sin cobertura de subprocesos (no se configura `patch`).

### 6.2 Workflow

Job `unittest`: un paso antes de "Install pywin32", en los tres sistemas:

```yaml
      - name: Install css-inline
        run: python -m pip install "css-inline~=0.23.1"
      - name: Install coverage
        run: python -m pip install "coverage~=7.17"
```

El paso actual de tests pasa a correr bajo `coverage` y el gate va en un paso propio (en `windows-latest` el shell es `pwsh`, que en un `run:` de varias líneas solo devuelve el código del último comando):

```yaml
      - name: Run unit, contract, integration and read-only tests
        run: python -B -m coverage run -m unittest discover -s tests -t . -v
      - name: Check coverage
        run: python -m coverage report
```

`Check coverage` falla (exit 2) por debajo del 85 % total: el PR del lote no se mergea con ese job en rojo (HITL-07). `.gitignore` ya ignora `.coverage` y `htmlcov/`.

Job `install-scripts`, solo en `ubuntu-latest` (un paso, no un job nuevo):

```yaml
      - name: Check css-inline wheels
        if: matrix.os == 'ubuntu-latest'
        shell: bash
        run: |
          set -e
          for platform in macosx_11_0_arm64 macosx_10_12_x86_64 win_amd64 win32 manylinux_2_17_x86_64; do
            dest="$RUNNER_TEMP/css-inline-$platform"
            python3 -m pip download "css-inline~=0.23.1" --only-binary=:all: --no-deps \
              --platform "$platform" --python-version 3.11 --implementation cp --dest "$dest"
            ls "$dest" | grep -E '^css_inline-0\.23\.[0-9]+-.+\.whl$'
          done
```

El `grep` falla si `pip` baja algo que no sea un wheel `0.23.x`, lo que cubre "sin compilar" y "no pasa a 0.24". Si `pip` exige `--abi abi3` para encontrar los wheels `abi3`, se añade y se anota en la evidencia. Si una etiqueta no tiene wheel, es un hallazgo para el orquestador (AC-H15), no se elimina la etiqueta.

Antes de cerrar el milestone, el subagente ejecuta el mismo bucle en local (Git Bash, intérprete de `.venv`, con `RUNNER_TEMP` apuntando a un temporal) y pega la salida en la evidencia (f), para no gastar corridas del PR del lote en ajustes del bucle. Si los wheels descargados no son `abi3` (nombre sin `-abi3-`), el bucle se repite para `--python-version` 3.11, 3.12, 3.13 y 3.14 (bucle anidado), en local y en el paso de CI.

`timeout-minutes`: 20 en `unittest`, 15 en `install-scripts`. El disparador (`pull_request` a `develop`/`main`) y `concurrency` no cambian.

### 6.3 README

- **Introducción (líneas 5–6):** "Python, standard library only except `pywin32` on Windows" / "Python, solo biblioteca estándar salvo `pywin32` en Windows" pasa a nombrar las dos dependencias: `css-inline` y, en Windows, `pywin32` (texto obsoleto de CL-05: "solo biblioteca estándar y `pywin32`").
- **Requisitos / Requisitos:** `css-inline` (MIT) se instala automáticamente con `pipx install`; en Windows, además `pywin32`.
- **Running the tests / Ejecutar los tests:** crear un entorno virtual en la raíz (`python -m venv .venv`) e instalar `css-inline~=0.23.1` (y `pywin32` en Windows) dentro; usar su intérprete para los comandos de siempre. En macOS, el `python3` de Homebrew no admite `pip install --user` (PEP 668), de ahí el entorno virtual. Cobertura: instalar `coverage~=7.17` en el mismo entorno y correr `python -B -m coverage run -m unittest discover -s tests -t .` y `python -B -m coverage report` (falla por debajo del 85 %).
- **Subsección de RF-65**, dentro de "Install, upgrade and uninstall" / "Instalar, actualizar y desinstalar": título "Security update of `css-inline`" / "Actualización de seguridad de `css-inline`", los cinco pasos de PRD-v2.2 sección 9.1 con sus comandos (iguales en macOS y Windows), el enlace a <https://github.com/Stranger6667/css-inline/security/advisories> y al changelog, y la nota de que, si `css-inline` falla, `mailquery` convierte el HTML sin pasar las hojas `<style>` a línea.

## 7. Fases

| Fase | Tareas | Estado |
|---|---|---|
| F1 — Dependencia | 6.1 (dependencia y tablas de cobertura); actualizar TC-06.03; PKG-03 | 🟢 |
| F2 — CI | 6.2 (instalación, suite bajo `coverage`, gate de cobertura, paso de wheels y timeouts); bucle de wheels en local | 🟢 |
| F3 — README | 6.3 en los dos README; DOC-07 | 🟢 |
| F4 — SMOKE | SMOKE-INSTALL.05 | 🟢 |
| F5 — Cierre | Suite completa, grupos solos, evidencia cruda, bloques para el orquestador | 🟢 |

## 8. Tests

Convenciones de `docs/TEST-CATALOG.md` sección 1: un método por caso, `test_<grupo>_<caso>_<descripción>`, el ID en el docstring, solo `unittest`.

**TC-06.03 — Dependencias de ejecución** (existente, se extiende) · `tests/test_packaging.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .03 | P | `[project].dependencies` es exactamente `css-inline~=0.23.1` (sin marcador) y `pywin32; sys_platform == "win32"`. Método: `test_tc_06_03_runtime_dependencies_are_css_inline_and_pywin32`. |

**PKG-03 — Dependencia `css-inline`** (nuevo) · `tests/test_packaging.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | La entrada de `css-inline` es literalmente `css-inline~=0.23.1`: rango de parches `0.23.x` desde `0.23.1`, sin `==`, sin `>=` abierto y sin marcador de plataforma. |
| .02 | N | `pywin32` sigue siendo la única dependencia con marcador `sys_platform == "win32"`. |
| .03 | P | `pyproject.toml` declara `[tool.coverage.report].fail_under = 85` y `[tool.coverage.run].branch = true`; `coverage` no está en `[project].dependencies`. |

**DOC-07 — Actualización de seguridad de `css-inline` en los README** (nuevo) · `tests/test_packaging.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `README.md`: dentro de la sección "Install, upgrade and uninstall" hay una subsección "Security update of `css-inline`" con `pipx runpip mailquery show css-inline`, `pipx runpip mailquery install --upgrade "css-inline~=0.23.1"`, `pipx reinstall mailquery`, `pipx runpip mailquery install "css-inline==` y la URL de los avisos. |
| .02 | P | `README.es.md`: lo mismo dentro de "Instalar, actualizar y desinstalar", subsección "Actualización de seguridad de `css-inline`". |
| .03 | P | Los dos README nombran `css-inline` en la introducción, en los requisitos y en las instrucciones de tests, y las instrucciones de tests incluyen `coverage run` y `coverage report`. |
| .04 | N | Ningún README conserva "standard library only" / "solo biblioteca estándar". |

**SMOKE-INSTALL.05** (nuevo caso) · `tests/test_smoke.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .05 | P | Tras el `pipx install .` de SMOKE-INSTALL.01, `pipx runpip mailquery show css-inline` (con el mismo `PIPX_HOME` temporal) da `Version: 0.23.<n>`. Se salta con los mismos motivos que SMOKE-INSTALL. |

**CI — paso "Check css-inline wheels"**: no es un test de `unittest`; su salida de la corrida del PR del lote I1 se anota en la evidencia de M14 (AC-H15).

Comandos:

```bash
python -B -m unittest discover -s tests -t . -k test_tc_06_03_
python -B -m unittest discover -s tests -t . -k test_pkg_03_
python -B -m unittest discover -s tests -t . -k test_doc_07_
python -B -m unittest tests.test_smoke -v
python -B -m coverage erase
python -B -m coverage run -m unittest discover -s tests -t .
python -B -m coverage report
```

## 9. Tests existentes afectados

- TC-06.03 (`tests/test_packaging.py`): hoy exige que `pywin32` sea la única dependencia; se reescribe (sección 8).

## 10. Documentación

- `README.md`, `README.es.md`: sección 6.3.
- Bloque para `INTERFACES.md` sección 8.2: instalar `css-inline~=0.23.1` y `coverage~=7.17` en el entorno de tests y los dos comandos de cobertura; sección 8.6: la CI instala `css-inline` y `coverage` (no el paquete), corre la suite bajo `coverage` con el gate del 85 % y el job de instaladores comprueba los wheels.
- Bloques para `TEST-CATALOG.md`: sección 2 (fila `DOC`: añadir `tests/test_packaging.py`, donde vive DOC-07); sección 5 ("La matriz no instala el paquete" pasa a "La matriz instala `css-inline`, `coverage` y, en Windows, `pywin32`; no instala el paquete", el paso de wheels y "la suite corre bajo `coverage` y el job falla por debajo del 85 % de cobertura total combinada de líneas y ramas"); sección 8: TC-06.03 reescrito, PKG-03, DOC-07, SMOKE-INSTALL.05; sección 7: filas de AC-H15 y AC-H17 (delta `PRD-v2.2.md`).

## 11. Actualizaciones de `PRD-v2.2.md` (las escribe el orquestador)

- Registro de conciliación: fila "Dependencias y actualización (F1)" → `Implementado y documentado`, documentos `README.md`, `README.es.md`.
- Tabla de supersesión (sección 0.2) y checklist (sección 0.4): sin cambios.

## 12. Datos crudos de evidencia a entregar

(a) suite completa con commit y conteo; (b) salida de los grupos `test_tc_06_03_`, `test_pkg_03_`, `test_doc_07_` y del módulo `tests.test_smoke`; (c) goldens: ninguno; (d) tests nuevos/modificados con IDs y AC; (e) `git diff --check` y `git diff --stat integration/i1-prep...HEAD`; (f) salida literal del bucle de wheels en local, riesgos (wheels que falten, flags de `pip download` añadidos), decisiones y pendientes; (g) cobertura: salida completa de `coverage report` (total; M01 no toca `src/`). Más los bloques de la sección 10.

## 13. Definition of Done

- [ ] `pyproject.toml` declara `css-inline~=0.23.1` sin marcador.
- [ ] `pyproject.toml` tiene las tablas `[tool.coverage.*]` de D-21.
- [ ] El workflow instala `css-inline` y `coverage` en `unittest`, corre la suite bajo `coverage` con el paso `Check coverage` separado, tiene el paso de wheels en Ubuntu (probado antes en local) y los timeouts 20/15; sigue sin dispararse por push.
- [ ] Los dos README tienen introducción, requisitos, instrucciones de tests (con cobertura) y la subsección de RF-65 con el mismo contenido.
- [ ] TC-06.03, PKG-03, DOC-07 verdes solos; SMOKE-INSTALL.05 verde en este equipo o saltado con motivo.
- [ ] Suite completa sin fallos nuevos frente a la línea base del lote.
- [ ] Cobertura (D-21): total ≥ 85 % (M01 no modifica archivos de `src/`); salida en la evidencia (g).
- [ ] Informe final con los datos de la sección 12 y los bloques para el orquestador.

## 14. Registro de progreso

| Fecha | Fase | Nota |
|---|---|---|
| 2026-11-13 | F1 — Dependencia | `css-inline~=0.23.1` en `[project].dependencies` y tablas `[tool.coverage.run]`/`[tool.coverage.report]`; TC-06.03 reescrito, PKG-03 y DOC-07 añadidos; grupos `test_tc_06_03_`, `test_pkg_03_` y `test_doc_07_` verdes. |
| 2026-11-13 | F2 — CI | Job `unittest` instala `css-inline` y `coverage`, corre la suite bajo `coverage` con el paso `Check coverage`; job `install-scripts` con el paso de wheels en Ubuntu; timeouts 20/15. Bucle de wheels verde en local para las cinco etiquetas. |
| 2026-11-13 | F3 — README | Introducción, requisitos, instrucciones de tests con entorno virtual y cobertura, y subsección de RF-65 en `README.md` y `README.es.md` con el mismo contenido; DOC-07 verde. |
| 2026-11-13 | F4 — SMOKE | SMOKE-INSTALL.05 verde contra la instalación `pipx` real con `PIPX_HOME`/`PIPX_BIN_DIR` temporales. |
| 2026-11-13 | F5 — Cierre | Suite completa `Ran 1072`, `FAILED (failures=2, skipped=7)`; los dos fallos son SMOKE-NEW.07 (`mailboxes` y `show`) de la línea base. Cobertura total 89,5 %. |

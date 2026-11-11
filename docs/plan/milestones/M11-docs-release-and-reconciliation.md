# M11 — Documentación, cierre de fase y conciliación

| Campo | Valor |
|-------|-------|
| Fase | F — Documentación y cierre de fase (sin publicación) |
| Depende de | M01–M10 |
| Bloquea a | — (cierre de fase; el release del `3.0.0` queda fuera del plan) |
| ACs | AC-19 (docs), AC-21; cierre de AC-01..AC-21 |
| Grupos de test | DOC-01..06, PKG-02, INS-SMOKE-01, TC-04, TC-05, TC-06, TC-07 (extendido); actualización de `GOOD_VERSION` y del regex de `SMOKE-INSTALL.02` para derivarlos de `__version__` (sin cambio de versión) |
| Write scope | `README.md`, `README.es.md`, `docs/INTERFACES.md`, `docs/config.example.toml`, `docs/recipes/01-*.md`, `docs/recipes/02-*.md`, `skills/mailquery/SKILL.md`, `skills/README.md`, `docs/security/threat-model.md`, `docs/PERFORMANCE-BACKLOG.md`, `scripts/install.sh`, `scripts/install.ps1`, `skills/install.sh`, `skills/install.ps1`, `src/mailquery/cli.py` (solo docstring de “five commands”), `tests/test_packaging.py`, `tests/test_install_scripts.py`, `tests/test_integration.py`, `tests/test_smoke.py` |
| No tocar | `src/mailquery/*.py` salvo el docstring de `cli.py`; `pyproject.toml` (la versión no cambia en esta fase); `tests/fixtures/expected/doctor.json` y `outlook/doctor.json` (los edita solo M02); `.github/workflows/tests.yml` (lo edita solo M01); `docs/PRD.md`; `docs/PRD-v2.1.md` (solo el orquestador actualiza §0.7); `docs/plan/PLAN-MASTER.md` (solo el orquestador) |
| Estado | ⚪ |

## 1. Objetivo

Cerrar la fase: documentación de usuario y de interfaz coherente con el contrato implementado, empaquetado e instaladores correctos, pruebas de documentación y recetas, y el estado de conciliación en `PRD-v2.1 §0.7` (sin tocar `PRD.md`, cuya conciliación es una tarea futura). **No se publica:** el paquete sigue en `2.0.1`, sin bump, sin tag de release y sin merge a `main`; los features quedan en `develop` hasta completar el resto del alcance del `3.0.0` (plan maestro §9.3, D15).

## 2. Contexto normativo

- PRD-v2.1 §0.2 nota de consumidores, §0.3 (conciliación), §0.4/§0.4.1 (cambios visibles), §0.5 (versión del delta: el bump queda para el release futuro), §11.1/§11.4/§11.9 (ayudas y versión), §13.1/§13.2 (config), §21.1 (harness), §22.x-equivalentes del delta, AC-21 y el cierre de fase de §9.3 del plan maestro.
- Base 2.0.1: `README.md:18-19,190-361,332-355,374-388`; `README.es.md` equivalentes; `docs/INTERFACES.md:194,215-216,575-590,813-877`; `docs/config.example.toml:2,9-16,24-35`; `docs/recipes/01-*.md:37-56,162-184`; `02-*.md:40-76,151-154,203-226`; `skills/mailquery/SKILL.md:41-52`; `skills/README.md:60-71`; `scripts/install.sh:218-257`; `scripts/install.ps1:16,179,294-299`; `tests/test_smoke.py:226-230` (regex de versión `2.0.1`); `tests/test_install_scripts.py:249-334` (`GOOD_VERSION` literal); `tests/test_packaging.py:19-40`.

## 3. Tareas

| ID | Tarea | Archivos | Detalle |
|----|-------|----------|---------|
| M11-T01 | Empaquetado sin bump de versión | `tests/test_packaging.py`, `tests/test_install_scripts.py`, `tests/test_smoke.py` | **No se cambia la versión**: `pyproject.toml` y `__version__` siguen en la vigente (`2.0.1`), y no se tocan los goldens `doctor`. `PKG-02` se cierra comprobando: `[project.entry-points."mailquery.backends"]` definitivo con los dos backends internos, console script intacto, `requires-python` sin cambios y `__version__` sincronizada con la metadata del paquete. Los tests de instaladores construyen `GOOD_VERSION` con `mailquery.__version__` pero como **línea completa** de `-v` (`mailquery <v> (backend outlook; Python ...; Windows ...)`), no solo la versión; el regex de `SMOKE-INSTALL.02` usa `__version__`. `mailquery -v` sigue conteniendo `backend <nativo>`. |
| M11-T02 | `README.md` | `README.md` | Manual de usuario del incremento (publicación futura dentro del `3.0.0`): qué es y garantía de solo lectura (núcleo y plugins); instalación/actualización/desinstalación y `pipx inject mailquery <paquete>` para plugins; seis comandos (`doctor`, `mailboxes`, `search`, `new`, `show`, `attachment`) con ejemplos; `uid` string `"<driver>:<native_id>"` y aceptación del legado; `[scope."<driver>:<cuenta>"]` y fallback nativo; `[attachments]` y caché `~/.mailquery/attachments/` (permisos, `--force`, bloqueo del mensaje, limpieza externa); `attachment` con `--index`/`--all`; `show.attachments` con `cached_path`; `doctor` con `driver` y `--version` con `drivers`; capacidades de plugins y `doctor`; exit codes y errores nuevos; problemas típicos. Sin referencias a “cinco comandos”, uid entero ni a un `3.0.0` ya publicado; cualquier versión mostrada en ejemplos coincide con `mailquery.__version__`. |
| M11-T03 | `README.es.md` | `README.es.md` | Misma estructura y contenido que `README.md` en español, coherente sección a sección (mismos comandos, ejemplos, exits y rutas). |
| M11-T04 | Recetas y skills | `docs/recipes/01-*.md`, `02-*.md`, `skills/mailquery/SKILL.md`, `skills/README.md` | Recetas: comandos con uid prefijado, `attachment` donde aporte (p. ej. facturas), quitar la afirmación de que `attachments` solo trae `name`, mantener exits 3/5/6 y la frontera de contenido no confiable. SKILL.md: tabla de seis comandos, uid string, `attachment`, `show.attachments`, errores nuevos y `pipx inject`. `skills/README.md`: instalación de plugins y referencia a `attachment`. |
| M11-T05 | Instaladores | `scripts/install.sh`, `scripts/install.ps1`, `skills/install.sh`, `skills/install.ps1` | Textos y comprobaciones del incremento, sin bump de versión: sin “cinco comandos”; plantilla de config con `[attachments]` documentada; mención de `pipx inject`; el chequeo final de `install.ps1` (`mailquery -v` contiene `backend outlook`) sigue siendo válido; `--help`/`--dry-run`/`--print-config` sin cambios de contrato. |
| M11-T06 | Interfaz y ejemplos finales | `docs/INTERFACES.md`, `docs/config.example.toml`, `docs/security/threat-model.md`, `docs/PERFORMANCE-BACKLOG.md` | Revisión final de `INTERFACES.md` contra el código (API 1, backend v1, `uid`, config, estado, multi-driver, errores, adjuntos, caché, logs, goldens, fakes, CI) y cabecera que marque el contrato como **no publicado** (versión vigente `2.0.1`; contrato del futuro `3.0.0`). `config.example.toml` válido con el esquema cerrado, `[attachments]` y ejemplos de `[scope]` con y sin prefijo. `threat-model.md`: excepción COM, capacidades de plugins y fog de adjuntos, sin contradicciones. `PERFORMANCE-BACKLOG.md`: presupuestos de `attachment` (caché < 50 ms, extracción Apple < 200 ms / Outlook < 600 ms, plugins sin presupuesto) y sin referencias obsoletas a versiones anteriores. |
| M11-T07 | Pruebas de documentación y recetas | `tests/test_integration.py` | DOC-01..06, TC-04 (cada comando de cada receta con exit 0 en ambos backends; el `<uid>` de un comando `attachment` se toma de un mensaje **con adjunto conocido** de un fixture/`search`, no de `messages[0]` genérico), TC-05 extendido a `attachment`, TC-06 (packaging: entry points, versión, console script) y TC-07 extendido: recorre la ayuda raíz + los 6 subcomandos (7 invocaciones), incluye `attachment --help` y afirma la ausencia de `cinco comandos`/`five commands` (también en el docstring de `cli.py`). DOC-01.04 comprueba ambas cadenas. Los tests leen los documentos reales y fallan con texto obsoleto. |
| M11-T08 | Evidencia de cierre de fase y conciliación | (sin código; verificación de CI) | Ejecutar la suite completa en macOS y Windows (hosts del dueño), SMOKE-INSTALL/SMOKE-NEW/SMOKE-ATT-AM/SMOKE-ATT-OL, gates TC-03/OL-30 y la CI del PR de I4: debe lanzar la matriz completa y los 3 jobs de `install-scripts` (15 jobs, §7.5 del plan maestro). No hay corrida de tag ni de release en esta fase. Re-medir los presupuestos de §12.2 (caché-hit de `attachment`, extracción Apple/Outlook, p95 de `mailboxes`/`show` de `SMOKE-NEW.07`) y el escaneo de solo stdlib de `attachments/**`, `plugins/**` y `backends/registry.py`. Preparar el contenido de `docs/plan/evidence/M11.md` (comandos, conteos, goldens, versión vigente `2.0.1` sin bump, `git diff --stat`); la URL del run del PR de I4 la añade **el orquestador**. Con eso el orquestador actualiza `PRD-v2.1 §0.7` (filas de features 🟢; RC-25, CL-05, CL-09, CL-12 y CL-08 en lo que dependa de ellas ⚪ pendientes del release futuro) y el dashboard del plan maestro. Verificar que no hay tag `v3.0.0` ni merge a `main`, que `docs/PRD.md` no cambió y que este plan solo cambió en dashboard/registro/evidencias. |

## 4. Casos de prueba

### DOC-01 — `README.md` (AC-21)

- .01 P Contiene los seis comandos y ningún texto con “cinco comandos”/“five commands”.
- .02 P Describe el `uid` como string prefijado y la aceptación del uid legado; no hay ejemplos con uid entero.
- .03 P Documenta `[scope."<driver>:<cuenta>"]`, `[attachments]`, `attachment`, `show.attachments`, `doctor driver`, `--version drivers` y los exit codes/errores nuevos.
- .04 N No contiene marcas obsoletas: `five commands`, `baseline` como concepto vigente, `retention_days`, uid entero en JSON, `attachments` solo con `name`, ni presenta `3.0.0` como versión publicada.
- .05 P Los bloques de ejemplo de JSON y comandos coinciden con el contrato implementado (uid string, `cached_path`, `drivers:`).

### DOC-02 — `README.es.md` (AC-21)

- .01 P Misma estructura y mismo conjunto de comandos, flags, rutas y exit codes que `README.md`.
- .02 N No contiene las mismas marcas obsoletas que DOC-01.04.
- .03 P Los ejemplos de uid y de `attachment` usan el formato prefijado.

### DOC-03 — Coherencia entre documentos (AC-21)

- .01 P `README.md`, `README.es.md`, recetas, `SKILL.md`, `config.example.toml` y las ayudas coinciden en comandos, exits, formato de uid y ruta de caché.
- .02 N Ningún documento promete escribir fuera de `~/.mailquery` ni abrir red desde el núcleo.
- .03 P Donde se muestra `--version`, el ejemplo usa `mailquery.__version__` (hoy `2.0.1`) y la forma con `drivers:`; no se anuncia `3.0.0` como publicado.

### DOC-04 — `skills/mailquery/SKILL.md` (AC-21)

- .01 P Tabla de seis comandos con `attachment`; uid string; `show.attachments` con `cached_path`; errores nuevos.
- .02 P Indica que el harness no debe ejecutar ni abrir los archivos recuperados y que el bloqueo es del mensaje completo.
- .03 N No presenta el uid como entero ni omite `attachment`.

### DOC-05 — Ayudas del CLI (AC-21)

- .01 P La ayuda raíz lista los seis comandos y la línea de exits de §11.1.
- .02 P `attachment --help` coincide con §11.4 (usage, positional, options, examples, notes).
- .03 P La ayuda raíz y las seis ayudas de subcomando (7 invocaciones) pasan `parse_args` (sin invocar el store).
- .04 N Ninguna ayuda menciona cinco comandos ni un formato de uid entero.
- .05 N TC-07 recorre las 7 ayudas (raíz + 6), no solo 5, e incluye `attachment --help`.

### DOC-06 — `config.example.toml` (AC-21)

- .01 P Parsea con el cargador real, esquema cerrado, defaults documentados y `[attachments]` comentada.
- .02 P Incluye un ejemplo de `[scope]` con prefijo y otro sin prefijo, y ninguna sección desconocida.
- .03 N No conserva claves de versiones anteriores.

### PKG-02 — Empaquetado (sin bump de versión)

- .01 P `pyproject.toml` y `__version__` coinciden y siguen en la versión vigente (`2.0.1`, sin bump); grupo `mailquery.backends` con `apple_mail` y `outlook`; console script intacto.
- .02 P Los tests de instaladores construyen `GOOD_VERSION` con `mailquery.__version__` pero como línea completa de `-v` (`mailquery <v> (backend outlook; Python 3.14.0; Windows 10.0.26200 AMD64)`), no solo la versión.
- .03 P `SMOKE-INSTALL.02` acepta la salida de `-v` de la versión actual sin fijar un literal (se deriva de `__version__`).

### INS-SMOKE-01 — Instaladores

- .01 P Sintaxis, `--help`, `--print-config` y `--dry-run` de `install.sh` y `install.ps1` y de `skills/install.*` siguen pasando.
- .02 P La plantilla de configuración documenta `[attachments]` y sigue siendo TOML válida con defaults.
- .03 P Se menciona `pipx inject mailquery <paquete>` para plugins y `mailquery -v` conserva `backend <nativo>`.

### TC-04 — Recetas

- .01 P Cada línea `mailquery …` de `01-new-mail-digest.md` termina con exit 0 en ambos backends; `<uid>` = `messages[0].uid` de `new --peek` (o el que indique la receta).
- .02 P Cada línea de `02-search-invoices.md` termina con exit 0 en ambos backends; cuando use `attachment`, el `<uid>` viene de un mensaje con adjunto conocido (fixture o búsqueda `--has-attachments`), no de `messages[0]` genérico.
- .03 N Las recetas no prometen extracción remota, `--out` ni ejecución de archivos.

### TC-05 — Paridad de forma JSON (extendido)

- .01 P `search`, `new`, `show` y `mailboxes` tienen el mismo conjunto recursivo de claves en ambos backends.
- .02 P `attachment` de éxito y de error tiene el mismo conjunto de claves en ambos backends (con `attachments: "local"`).
- .03 N El objeto de error sigue siendo `{code, message, hint}` sin campos nuevos.

### TC-06 — Packaging (AC-01, AC-18)

- .01 P `pyproject.toml` declara la versión vigente (sin bump), el console script y el grupo `mailquery.backends` con los dos backends internos.
- .02 P `mailquery.__version__` coincide con la metadata del paquete; entry points resolubles con metadata inyectada.
- .03 N Sin dependencias de runtime nuevas (`pywin32` solo en Windows).

### TC-07 — Documentación y ayudas (AC-21)

- .01 P Recorre la ayuda raíz + 6 subcomandos (7 invocaciones) y todas parsean.
- .02 P `attachment --help` coincide con §11.4.
- .03 N Ninguna ayuda/documento dice `cinco comandos`/`five commands`, muestra uid entero o promete escritura fuera de `~/.mailquery`.
- .04 P TC-07.04 de la base se extiende a 6 comandos + raíz (hoy recorre 5) y se ejecuta en M11.

## 5. Documentación del milestone

Es el milestone de documentación: todos los documentos de la tabla §8 del plan maestro quedan actualizados y revisados. El orquestador aplica en `PRD-v2.1 §0.7` el estado de las filas de features (🟢 con su evidencia) y deja ⚪ las de publicación (RC-25, CL-05, CL-09, CL-12 y CL-08 en lo que dependa de ellas), y actualiza el dashboard del plan maestro con la evidencia de M11-T08.

## 6. Criterios de cierre

1. Suite completa verde en macOS y Windows (hosts del dueño), matriz de CI verde en el PR de I4 (15 jobs; conteos y URL en `docs/plan/evidence/M11.md`) y SMOKE verdes o saltadas con motivo documentado.
2. DOC-01..06, PKG-02, INS-SMOKE-01, TC-04, TC-05, TC-06 y TC-07 verdes solos.
3. Documentación e instaladores coherentes con el incremento, sin anunciar un `3.0.0` publicado; versión del paquete sin bump (`2.0.1`), sin tag de release y sin merge a `main`; goldens `doctor` sin edición en M11.
4. `PRD.md` sin cambios; `PRD-v2.1 §0.7` con las filas de features 🟢 y las de publicación (RC-25, CL-05, CL-09, CL-12 y CL-08 en lo que dependa de ellas) ⚪ pendientes del release futuro del `3.0.0`.
5. Ningún documento consumidor con referencias obsoletas (lista de §9.3 del plan maestro).

## 7. Handoff y HITL

- Reportar: evidencia de cierre de fase (suite, CI del PR de I4, SMOKE, gates), documentos actualizados, versión vigente sin bump confirmada, estado de conciliación propuesto y confirmación de que no hay tag de release ni merge a `main`.
- HITL: si falta un host para los SMOKE (p. ej. Windows), el dueño decide si se cierra la fase con riesgo aceptado documentado o se bloquea; si la conciliación exige editar `PRD.md`, no hacerlo y recordar que es una tarea futura. El release del `3.0.0` no se decide en este milestone.

## 8. Riesgos del milestone

| Riesgo | Mitigación |
|---|---|
| Documentación desincronizada con el código | DOC-01..06 leen los documentos reales y fallan con texto obsoleto; M11 es el último milestone |
| Versión fijada en tests/smoke | Usar `mailquery.__version__` en los tests en lugar de literales; el bump a `3.0.0` llega con el release futuro |
| Confundir cierre de fase con release del `3.0.0` | Sin bump, sin tag y sin `main` (D15); criterios 3 y 4 lo verifican; la versión anunciada es `__version__` |
| Cerrar con clientes reales sin verificar | Gate M11 con SMOKE en macOS/Windows; si falta un host, decisión HITL del dueño |
| Conciliación con `PRD.md` adelantada por error | Prohibido tocar `PRD.md`; el registro queda ⚪ pendiente en §0.7 |

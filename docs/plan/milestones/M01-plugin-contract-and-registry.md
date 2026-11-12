# M01 — Contrato de plugin, registro de drivers y uid base

| Campo | Valor |
|-------|-------|
| Fase | A — Fundaciones del contrato |
| Depende de | — |
| Bloquea a | M02–M11 |
| ACs | AC-01, AC-02 (validación de capacidades), AC-05 (formato y parseo), AC-18 (`--version`) |
| Grupos de test | UT-PL-01..04, UT-UID-01, PKG-01; actualización de UT-CLI-01..03, UT-CLI-09 y `tests/test_outlook.py` (`OL-02.06`). M01-T08 no añade casos: su verificación es el run del PR de I1 |
| Write scope | `src/mailquery/plugins/**` (nuevo), `src/mailquery/backends/registry.py` (nuevo), `src/mailquery/backends/base.py`, `src/mailquery/backends/__init__.py`, `src/mailquery/backends/apple_mail.py` (solo metadatos de driver), `src/mailquery/backends/outlook.py` (solo metadatos de driver), `src/mailquery/uid.py` (nuevo), `src/mailquery/errors.py`, `src/mailquery/cli.py` (solo `--version` y selección), `pyproject.toml`, `docs/INTERFACES.md`, `tests/fakes/plugin.py` (nuevo), `tests/test_plugins.py` (nuevo), `tests/test_uid.py` (nuevo), `tests/test_packaging.py`, `tests/test_backends.py`, `tests/test_cli.py`, `tests/test_outlook.py` (solo `OL-02.06` y metadatos del backend), `.github/workflows/tests.yml` (solo disparadores, `concurrency` y `timeout-minutes`, M01-T08) |
| No tocar | `docs/PRD.md`, `docs/PRD-v2.1.md`, `docs/plan/**`, `search.py`, `config.py`, `state.py` |
| Estado | ⚪ |

## 1. Objetivo

Dejar congelado el contrato que usan todos los milestones: descubrimiento de backends por entry points, API pública de plugin (API 1), validación de `driver`/capacidades, formato del `uid` prefijado y `--version` aditivo. Este milestone **no** cambia el comportamiento de los comandos de datos: solo añade la capa de contrato y sus errores.

## 2. Contexto normativo

- PRD-v2.1 §6.1: RF-35 (registro), RF-38 (contrato y capacidades), RF-40 (uid), RF-41 (`doctor`/`--version`), ADR-17, ADR-19, ADR-22, ADR-23.
- §10.2 puntos 1 y 2 (uid y etiquetas), §11.3 filas 1, 2 y 5 (validación temprana, driver desconocido/carga), §11.7 (códigos nuevos, propiedad `code`/`exit`), §11.9 (`--version`).
- §13.1 (solo la columna de `driver` de `[scope]`; el parseo completo es M02), §14 AC-01/AC-02/AC-05/AC-18.
- Base 2.0.1: `backends/__init__.py:15-72` (selección por plataforma), `backends/base.py:124-213` (ABC de 17 métodos), `errors.py:14-96` (catálogo), `cli.py:200-230` (`--version`), `pyproject.toml:31-32` (solo console script), `tests/test_outlook.py:877` (`OL-02.06`, `backend.name`).

## 3. Tareas

| ID | Tarea | Archivos | Detalle |
|----|-------|----------|---------|
| M01-T01 | API pública de plugin (API 1) | `src/mailquery/plugins/__init__.py`, `plugins/api.py` (nuevos) | `PluginContext(home, tmp_dir)`; `PluginError(reason, hint="", detail="", log_message="")`; enum cerrado `Reason` con los valores de §11.7; constante `PLUGIN_API = 1`; tipos de capacidades y de metadata del driver. Un plugin externo solo debe necesitar este paquete para implementar el contrato (PRD §9.3). |
| M01-T02 | Protocolo de backend v1 | `src/mailquery/backends/base.py`, `docs/INTERFACES.md`, `tests/test_outlook.py` (solo `OL-02.06`) | Definir el tipo de contrato nuevo `Uid = str` y mantener un alias interno transitorio para el uid legado (`int \| str`) hasta M03, para no cambiar la emisión de los comandos en este milestone. Renombrar `name` → `driver` en `MailBackend` y actualizar `OL-02.06` (`tests/test_outlook.py:877`), que es la única aserción de `backend.name`, y `cli.py:550` (`event=start backend=%s`, `selected.name` → `selected.driver`). Añadir a `MailBackend` los metadatos `driver`, `plugin_api`, `capabilities` y la operación de orden nativo (`native_order`), el parseo de la parte nativa del uid (`parse_native_id`) y las dos operaciones de adjuntos que consumirán M06–M10: metadatos ordenados con `index`, `name`, tamaño esperado, `native_order_key` y motivo de no disponibilidad; y stream de bytes decodificado. Cada fila de mensaje de las operaciones de listado incluye `native_order_key` (string); la capacidad `native_order` fija si se compara como entero o como texto (contrato C1). Documentar firmas exactas en `INTERFACES.md`. No renombrar las otras 17 operaciones existentes. |
| M01-T03 | Registro de backends | `src/mailquery/backends/registry.py` (nuevo), `backends/__init__.py` | Descubrimiento por el grupo de entry points `mailquery.backends` con `importlib.metadata`; validación de `driver` (`[a-z0-9_]{1,64}`, único, `apple_mail`/`outlook` reservados), `plugin_api = 1` y capacidades (presencia, enum válido, reglas cruzadas `attachments: remote ⇒ network`, `body_local: false ⇒ network`); carga perezosa (solo drivers declarados o referenciados por uid); detección de duplicados; metadata de versión sin importar el módulo. Fallback estático para los backends internos cuando el paquete corre desde `src/` sin instalar (CI y desarrollo), de modo que los tests no dependan de `pip install`. Métodos: resolver driver, listar instalados, listar declarados, cargar uno solo, metadata para `--version`. Errores `E_PLUGIN_INCOMPATIBLE` (exit 3) y `E_DRIVER_UNKNOWN` (exit 2). |
| M01-T04 | Auto-registro de backends internos | `backends/apple_mail.py`, `backends/outlook.py`, `pyproject.toml` | `apple_mail` y `outlook` implementan los nuevos metadatos, `parse_native_id` (entero y hex mayúsculas respectivamente) y se registran por la misma vía que un plugin (entry points + fallback estático). `pyproject.toml` gana `[project.entry-points."mailquery.backends"]` con ambos. No cambiar la lógica de lectura ni la selección por plataforma de los comandos. |
| M01-T05 | `uid` prefijado | `src/mailquery/uid.py` (nuevo), `docs/INTERFACES.md` | Formato/parseo/validación: split en el primer `:`; `driver` con `[a-z0-9_]{1,64}`; `native_id` con `[A-Za-z0-9._=-]{1,1024}`, sin punto inicial, sin `..` y sin espacios; aceptación del uid legado sin prefijo resuelto con el driver nativo; helper de identificador estable de 32 hex (`SHA-256` del uid UTF-8) que usará M06/M07 para rutas largas; validación disponible antes de crear el home/leer config/abrir store. Errores `E_USAGE`/`E_DRIVER_UNKNOWN`. |
| M01-T06 | Códigos de error y `--version` | `errors.py`, `cli.py`, `tests/test_cli.py` (UT-CLI-09), `docs/INTERFACES.md` | Añadir al catálogo de `errors.py` los códigos de §11.7 con su exit. Nuevos (9): `E_DRIVER_UNKNOWN` 2, `E_ATTACHMENTS_DISABLED` 2, `E_PLUGIN_INCOMPATIBLE` 3, `E_PLUGIN_FAILED` 3, `E_ATTACHMENT_UNAVAILABLE` 3, `E_ATTACHMENT_UNREADABLE` 3, `E_ATTACHMENT_BLOCKED` 4, `E_ATTACHMENT_TOO_LARGE` 4, `E_IO` 3. Se conservan los existentes, incluidos `E_ACCOUNT_NOT_IN_SCOPE`, `E_CLIENT_TIMEOUT`, `E_CLIENT_BUSY` y `E_PERMISSION` (ampliados, no nuevos). Actualizar `UT-CLI-09.01` (hoy 23 códigos) a los **32** de §11.7 y añadir una comparación de `errors._EXIT_ERRORS` contra la tabla completa; los casos de CLI de cada código nuevo se completan en M08. `--version` conserva el prefijo, toma la versión del paquete (`mailquery.__version__`/metadata, nunca un literal) y añade `; drivers: <driver> <versión>, ...` dentro del paréntesis, alfabético; los backends internos se filtran por plataforma (DP-02) y los plugins externos se listan siempre. Sin leer config ni importar plugins. `mailquery <cmd> -v` sigue siendo `E_USAGE`. |
| M01-T07 | Doble de plugin y tests | `tests/fakes/plugin.py` (nuevo), `tests/test_plugins.py`, `tests/test_uid.py`, `tests/test_packaging.py`, `tests/test_backends.py`, `tests/test_cli.py`, `tests/test_outlook.py` (solo `OL-02.06`) | Doble de plugin instalable con metadata/capacidades/`native_order_key`/fallos configurables y helper para inyectar entry points en tests. Actualizar los tests de versión, de interfaz de backend (`tests/test_backends.py:259,462,478` y `OL-02.06` de `test_outlook.py:877`: `backend.name` → `backend.driver`) y `UT-CLI-09.01`; añadir PKG-01. Los tests que necesiten el paquete instalado usan metadata inyectada o se saltan con motivo. |
| M01-T08 | CI por lote | `.github/workflows/tests.yml` | Cambiar solo el disparo: quitar `push` en `develop` y `main` y dejar únicamente `pull_request` a `develop`/`main` (el PR de cada lote es el que ejecuta la matriz; esta fase no tiene tags ni release, así que no se añade disparo por tag). Añadir `concurrency` con `cancel-in-progress` y `timeout-minutes: 30` en los jobs. **No tocar la matriz** (`3 OS × 3.11–3.14`, `fail-fast: false`, `discover -s tests`), ni los 3 jobs de `install-scripts`, ni añadir pasos de instalación del paquete: los tests deben seguir sin `pip install`. Verificación: el subagente entrega el diff y la lista de disparadores resultante; el orquestador comprueba en el PR de I1 que se lanzan 15 jobs y que un push adicional a la rama del PR cancela el run anterior en lugar de acumular uno nuevo. |

## 4. Casos de prueba

Todos los casos siguen la convención de §7.1 del plan maestro (P/N/B, `test_<grupo>_<caso>_<descripción>`). Mapeo de IDs existentes: `UT-PL-03` **renombra** los casos de `--version` de `UT-CLI-01..03` (no se duplican); `PKG-01` extiende el `TC-06` de packaging, que M11 cierra.

### UT-PL-01 — Registro de drivers (AC-01, RF-35)

- .01 P El grupo `mailquery.backends` expone `apple_mail` y `outlook`; el registro los lista con `driver`, `plugin_api` y versión **sin importar** los módulos.
- .02 P Fallback de desarrollo: con el paquete sin instalar, los backends internos se resuelven igual.
- .03 P Metadata inyectada: un plugin externo que cumple el contrato (driver válido, API 1, capacidades) se registra por la misma vía y aparece en el listado; no se exige `pip install` en CI.
- .04 N Un plugin declara un nombre reservado (`apple_mail`/`outlook`) ⇒ `E_PLUGIN_INCOMPATIBLE`.
- .05 N `driver` que no cumple `[a-z0-9_]{1,64}` (`Apple_Mail`, `apple-mail`, vacío, 65 caracteres) ⇒ `E_PLUGIN_INCOMPATIBLE`.
- .06 N `plugin_api` ausente o `≠ 1` ⇒ `E_PLUGIN_INCOMPATIBLE`; el hint incluye esperado/encontrado.
- .07 N Un plugin declarado no importa (dependencia faltante) ⇒ `E_PLUGIN_INCOMPATIBLE`; los demás drivers siguen siendo listables.
- .08 P Carga perezosa: un comando con solo el driver nativo declarado no importa el resto; `--version` no importa ninguno.
- .09 P Orden alfabético en `drivers:` con dos drivers (plugin fake + nativo) y filtrado por plataforma de los internos.
- .10 N `driver` duplicado (interno + plugin o dos plugins) ⇒ `E_PLUGIN_INCOMPATIBLE`, exit 3.

### UT-PL-02 — Capacidades (AC-02, RF-38)

- .01 P Mapa válido (`network`, `readonly`, `body_local`, `attachments`, `native_order`) aceptado y expuesto.
- .02 N Falta una capacidad ⇒ `E_PLUGIN_INCOMPATIBLE`.
- .03 N Valor fuera de enum (`attachments: "zip"`, `readonly: "yes"`, `native_order: "alpha"`) ⇒ `E_PLUGIN_INCOMPATIBLE`.
- .04 N `attachments: "remote"` sin `network: true` ⇒ `E_PLUGIN_INCOMPATIBLE`.
- .05 N `body_local: false` sin `network: true` ⇒ `E_PLUGIN_INCOMPATIBLE`.
- .06 P Varios drivers, cada uno con su mapa, se validan por separado.

### UT-PL-03 — `--version` (AC-18, DP-02)

- .01 P Formato exacto: prefijo de la versión instalada (`mailquery.__version__`, sin literal) con `; drivers: <driver> <versión>, ...` alfabético dentro del paréntesis.
- .02 P En macOS lista los drivers internos disponibles (`apple_mail`; no `outlook`); en Windows al revés (plataforma parcheada). Un plugin externo se lista siempre.
- .03 N Sin efectos: no crea `~/.mailquery`, no lee `config.toml`, no escribe log, no toma lock, no abre el store.
- .04 P Un plugin instalado aparece listado aunque sea incompatible; `doctor` es quien reporta el problema (M02).
- .05 N No importa módulos de plugin (metadata de distribución); un plugin instalado sin metadata de plataforma no se filtra.
- .06 P Sin paquete instalado (modo desarrollo), `--version` usa la versión de `__version__`/metadata de respaldo y no falla.

### UT-PL-04 — API de plugin y archivos autónomos (AC-01, RF-39)

- .01 P `PluginContext(home, tmp_dir)` y `PluginError(reason, hint, detail, log_message)` con el enum cerrado de `reason`; el doble de plugin solo necesita el paquete `mailquery.plugins`.
- .02 N El núcleo no lee `~/.mailquery/<driver>.toml` ni `~/.mailquery/logs/<driver>.log`: con esos archivos presentes, comandos y `doctor` se comportan igual.
- .03 N El núcleo no crea, rota ni borra `<driver>.toml`, `logs/<driver>.log` ni `tmp/plugin-<driver>/`.
- .04 P Escaneo de imports: `src/mailquery/plugins/**` y `backends/registry.py` solo usan stdlib y el propio paquete (RNF-12).

### UT-UID-01 — Formato y parseo (AC-05, RF-40)

- .01 P `apple_mail:83143` ⇒ driver `apple_mail`, nativo `83143`; `outlook:ABC123` ⇒ driver `outlook`, nativo `ABC123`.
- .02 P `native_id` acepta `[A-Za-z0-9._=-]`; el punto se acepta en posiciones interiores (`a.b`) pero se rechaza como primer carácter (`.a`) y la secuencia `..`; split en el primer `:` (`a:b:c` ⇒ nativo `b:c`, inválido por `:`).
- .03 N Driver vacío, con mayúsculas, guion o > 64 ⇒ `E_USAGE` (el formato del uid es inválido); un driver válido pero no instalado ⇒ `E_DRIVER_UNKNOWN` (caso separado).
- .04 N `native_id` con `/`, espacio, `:` o > 1024; punto inicial; `..`; cadena vacía ⇒ `E_USAGE`.
- .05 P Entrada legada: entero sin prefijo en macOS ⇒ driver nativo `apple_mail` con ese nativo; hex mayúsculas sin prefijo en Windows ⇒ `outlook`.
- .06 N La validación de un uid inválido ocurre antes de crear el home, leer la config y abrir el store; no escribe estado ni caché.
- .07 P Identificador estable de ruta: 32 hex en minúsculas = primeros 32 caracteres de `SHA-256(uid UTF-8)`; determinista entre plataformas.

### PKG-01 — Empaquetado y entry points (AC-01)

- .01 P `pyproject.toml` declara el grupo `mailquery.backends` con `apple_mail` y `outlook`.
- .02 P Con el paquete instalado, `importlib.metadata` expone ambos entry points; sin instalación, la metadata inyectada y el fallback estático producen el mismo resultado. El caso instalado se salta con motivo si el paquete no está instalado (CI no lo instala).
- .03 P `version` sigue sincronizada con `mailquery.__version__` y el console script `mailquery` no cambia.

## 5. Documentación del milestone

- `docs/INTERFACES.md`: sección de API pública de plugin (API 1, `PluginContext`, `PluginError`, enum de `reason`), protocolo de backend v1 (firmas exactas, capacidades, orden nativo, `parse_native_id`, operaciones de adjuntos), formato de `uid` y grupo de entry points.
- No se toca README, recetas ni PRD.

## 6. Criterios de cierre

1. Suite completa sin fallos nuevos; UT-PL, UT-UID y PKG verdes también ejecutados solos.
2. Contrato C1 documentado en `INTERFACES.md` y usado por los tests del doble de plugin.
3. Sin cambios de comportamiento de los comandos de datos (`search`, `new`, `show`, `mailboxes`, `doctor`); los goldens existentes no cambian salvo `--version`, que no es golden. `OL-02.06` y `UT-CLI-09.01` quedan verdes con el nuevo catálogo.
4. Sin dependencias nuevas; sin red; sin tocar el home real.
5. `.github/workflows/tests.yml` conserva la matriz y los 3 jobs de `install-scripts`; el orquestador valida el disparo en el PR de I1. `docs/plan/evidence/M01.md` lo pone el orquestador; no se crea tag `prd-v2.1-M01` (D16).

## 7. Handoff y HITL

- Al cerrar, reportar al orquestador: firmas congeladas de C1, códigos de error añadidos, tests nuevos, archivos tocados.
- HITL: si el protocolo de backend v1 no puede mantener las 17 operaciones existentes sin romper a los backends internos de forma no trivial, o si un plugin no puede implementar `parse_native_id` sin acceder al store, preguntar antes de rediseñar el contrato.

## 8. Riesgos del milestone

| Riesgo | Mitigación |
|---|---|
| El descubrimiento por entry points no funciona en CI sin instalar | Fallback estático + tests que inyectan metadata; PKG-01 cubre ambos caminos |
| Cambiar `Uid` a `str` rompe tests existentes de estado y `show` | El milestone no cambia el comportamiento: mantiene el parser legado en los backends hasta M03; los tests de formato viven en `test_uid.py` |
| El doble de plugin no representa un plugin real | Debe declararse solo con el paquete público `mailquery.plugins` y usarse desde `tests/fakes/plugin.py` sin imports internos del núcleo salvo los públicos del contrato |
| El cambio de disparadores deja el PR del lote sin matriz o sin `install-scripts` | M01-T08 conserva `pull_request` a `develop`/`main` y los 3 jobs de `install-scripts`; el orquestador verifica los 15 jobs en el PR de I1 y revierte al disparo anterior si falta alguno |

# M02 — Configuración multi-driver, `[attachments]` y `doctor driver`

| Campo | Valor |
|-------|-------|
| Fase | B — Identidad y configuración |
| Depende de | M01 |
| Bloquea a | M03–M11 |
| ACs | AC-02 (detalle en `doctor`), AC-03, AC-14 (solo config), AC-18 (`doctor`) |
| Grupos de test | UT-DRV-01..05; actualización de UT-CLI-10..12, las listas ordenadas de `test_cli.py`/`test_integration.py`, `_OUTLOOK_DOCTOR_CHECKS` de `tests/test_outlook.py` y el conteo de `doctor` |
| Write scope | `src/mailquery/config.py`, `src/mailquery/cli.py` (solo `doctor` y carga de config), `src/mailquery/backends/registry.py` (solo helpers de drivers declarados), `docs/INTERFACES.md`, `docs/config.example.toml`, `tests/test_config.py`, `tests/test_cli.py`, `tests/test_integration.py` (conteo y listas ordenadas de `doctor`), `tests/test_outlook.py` (solo `_OUTLOOK_DOCTOR_CHECKS` y el texto de `doctor`), `tests/fixtures/expected/doctor.json`, `tests/fixtures/expected/outlook/doctor.json`, `tests/fixtures/make_fixtures.py` (config de fixtures) |
| No tocar | `search.py`, `state.py`, `uid.py`, `plugins/**`, `PRD.md`, `PRD-v2.1.md`, `docs/plan/**` |
| Estado | ⚪ |

## 1. Objetivo

Implementar el esquema cerrado de `config.toml` del incremento PRD-v2.1 (contrato del futuro `3.0.0`): `[scope."<driver>:<cuenta>"]` con fallback al driver nativo, resolución de cuenta dentro de cada driver, tabla `[attachments]` con sus defaults/rangos y el chequeo `driver` de `doctor` con su composición y dependencias.

## 2. Contexto normativo

- PRD-v2.1 §6.1 RF-36 (scope) y RF-37 (ejecución multi-driver, solo la parte de configuración), §6.2 RF-42/49 (config de `[attachments]`), §11.3 filas 3 y 4, §11.6 (`doctor driver` completo), §13.1/§13.2 (propiedades, validación y ejemplos), AC-02/AC-03/AC-14/AC-18.
- Base 2.0.1: `config.py:358-407` (`[scope]` actual), `config.py:436-505` (`resolve_scope`), `config.py:508-589` (resolución por label/email/UUID), `config.py:642-682` (resolución de carpetas), `cli.py:916-1018` (orden y evaluación de `doctor`), `cli.py:1021-1107` (dependencias), goldens `doctor.json`.

## 3. Tareas

| ID | Tarea | Archivos | Detalle |
|----|-------|----------|---------|
| M02-T01 | Esquema `[scope."<driver>:<cuenta>"]` | `config.py` | La clave se divide en el **primer** `:`. Izquierda = driver; debe cumplir `[a-z0-9_]{1,64}` y estar instalado (`E_DRIVER_UNKNOWN`, exit 2). Sin `:` = driver nativo del SO (`apple_mail` en macOS, `outlook` en Windows; en otras plataformas `apple_mail` solo para desarrollo/CI). Una etiqueta de cuenta con `:` debe declarar el prefijo; sin prefijo produce `E_DRIVER_UNKNOWN` (limitación documentada). Bloques que resuelven a la misma `(driver, cuenta)` se combinan (unión de `mailbox_list`). Un bloque de un driver declarado pero no instalado hace fallar **todos** los comandos de datos; no se ignora. |
| M02-T02 | Resolución de cuenta por driver | `config.py` | Generalizar `resolve_scope` para resolver dentro de las `accounts()` de cada driver: para backends internos, las formas del PRD.md §15.2 (label casefold, email único, UUID completo, prefijo de UUID ≥ 8); para plugins, `label`/`uuid` opacos y estables (el mínimo de 8 no aplica). Errores `E_CONFIG_ACCOUNT_UNKNOWN`, `E_ACCOUNT_AMBIGUOUS`; stores excluidos siguen produciendo `W_STORE_EXCLUDED` (solo Outlook). Un driver instalado pero sin ningún bloque `[scope]` que lo declare queda fuera de alcance: el helper expone la comprobación y el error `E_ACCOUNT_NOT_IN_SCOPE`; los comandos `show`/`attachment` que lo usan se prueban en M03 (parte `show`) y M08 (parte `attachment`), no aquí. |
| M02-T03 | Tabla `[attachments]` | `config.py`, `docs/config.example.toml` | Nueva tabla con `enabled` (bool, default `true`), `max_file_size_mb` (1–500, default 100), `max_total_size_mb` (1–1024, default 200, `>= max_file_size_mb`), `max_count` (1–500, default 50). Esquema cerrado: clave/sección desconocida ⇒ `E_CONFIG_INVALID`; rango inválido, tipo inválido o `max_total_size_mb < max_file_size_mb` ⇒ `E_CONFIG_INVALID` (exit 2). `config.example.toml` refleja la tabla comentada y los ejemplos de §13.2. |
| M02-T04 | Chequeo `driver` en `doctor` | `cli.py`, `backends/registry.py`, `docs/INTERFACES.md` | Insertar `driver` después de `home` y antes de los chequeos del backend. `ok=true` si todos los drivers declarados (más el nativo cuando hay bloques sin prefijo) están instalados, tienen `driver` válido/único, `plugin_api = 1` y capacidades válidas. `detail` por driver: `<driver> (api=1; pkg <versión>; network=…; readonly=…; body_local=…; attachments=…; native_order=…)` unidos por `; `. Config inválida ⇒ `driver` valida solo el nativo y añade `declared drivers: unknown (config failed)`; sin config o sin bloques ⇒ `no declared drivers`. Orden macOS: `python`, `home`, `driver`, `store`, `envelope_index`, `schema`, `readonly_strategy`, `accounts_db`, `config`, `state`, `lock`; Windows: `python`, `home`, `driver`, `pywin32`, `outlook`, `stores`, `readonly_strategy`, `object_model_guard`, `config`, `state`, `lock`. `config` depende de `driver` (`not evaluated: driver failed`) **y conserva**, para el backend nativo, sus dependencias de `schema` (macOS) y `stores` (Windows) del PRD.md §12.8; el driver se evalúa primero, así que si `driver` y `schema`/`stores` fallan a la vez, `config` informa `not evaluated: driver failed`. Los chequeos específicos de backend solo se evalúan para el driver nativo. `doctor` sigue saliendo con exit 0. |
| M02-T05 | Tests y goldens | `tests/test_config.py`, `tests/test_cli.py`, `tests/test_integration.py`, `tests/test_outlook.py` (solo `doctor`), `tests/fixtures/expected/doctor.json`, `tests/fixtures/expected/outlook/doctor.json`, `tests/fixtures/make_fixtures.py` | UT-DRV-01..05. Los goldens `doctor.json` y `outlook/doctor.json` se actualizan primero, en rojo: insertan `driver` tras `home` y reflejan la composición; se actualizan el conteo de texto de `doctor` y `_OUTLOOK_DOCTOR_CHECKS` (11 chequeos) de `test_outlook.py`, las listas ordenadas de `test_cli.py` (`test_doctor_is_common_checks_plus_the_backend_checks`, `test_doctor_reports_all_required_checks`) y `tests/test_integration.py:343-357` (TC-01.01). Los fixtures de config se amplían con bloques con prefijo y con `[attachments]`; los tests existentes de `resolve_scope` se adaptan a la firma con registro. |

## 4. Casos de prueba

### UT-DRV-01 — Esquema de `[scope]` (AC-03)

- .01 P `[scope."apple_mail:you@icloud.com"]` ⇒ driver `apple_mail`, cuenta resuelta dentro de sus cuentas.
- .02 P `[scope."you@icloud.com"]` ⇒ driver nativo del SO.
- .03 P Etiqueta con `:` declarada con prefijo explícito funciona; sin prefijo ⇒ `E_DRIVER_UNKNOWN` (limitación documentada).
- .04 N Driver con mayúsculas, guion, vacío o > 64 ⇒ `E_DRIVER_UNKNOWN`.
- .05 N Driver bien formado pero no instalado ⇒ `E_DRIVER_UNKNOWN`; todos los comandos de datos fallan (no se ignora).
- .06 P Dos bloques que resuelven a la misma `(driver, cuenta)` combinan `mailbox_list`.

### UT-DRV-02 — Resolución de cuentas por driver (AC-03)

- .01 P Backend interno: label, email único y UUID completo/prefijo ≥ 8 dentro del driver.
- .02 P Plugin: `label`/`uuid` opacos, incluido label corto (< 8) que en un backend interno sería ambiguo.
- .03 N Cuenta inexistente ⇒ `E_CONFIG_ACCOUNT_UNKNOWN`; ambigua ⇒ `E_ACCOUNT_AMBIGUOUS`.
- .04 N Store excluido de Outlook declarado ⇒ `W_STORE_EXCLUDED` con la etiqueta/ruta, sin abortar.

### UT-DRV-03 — Driver instalado no declarado (AC-03)

- .01 N Los comandos de datos no consultan un driver instalado sin bloques `[scope]`.
- .02 N El helper de alcance devuelve `E_ACCOUNT_NOT_IN_SCOPE` (exit 2) para un driver instalado sin bloque `[scope]`, con el hint de declarar la cuenta. Los casos de los comandos `show` y `attachment` con ese prefijo viven en M03 y M08, donde los comandos existen.
- .03 N Un prefijo de driver no instalado ⇒ `E_DRIVER_UNKNOWN` (exit 2).

### UT-DRV-04 — `[attachments]` (AC-14, RF-42/49, §13)

`UT-DRV-04` prueba config/parseo; `UT-ATC-05` (M08) prueba el comando con esa config. No son el mismo caso y no se duplican.

- .01 P Sin tabla ⇒ defaults `enabled=true`, `100`/`200`/`50`.
- .02 P Valores válidos personalizados se aceptan y exponen.
- .03 N `enabled` no booleano; `max_file_size_mb` 0, 501, `"100"`, `true`; `max_total_size_mb` 0, 1025; `max_count` 0, 501 ⇒ `E_CONFIG_INVALID`.
- .04 N `max_total_size_mb < max_file_size_mb` ⇒ `E_CONFIG_INVALID` con hint.
- .05 N Clave desconocida en `[attachments]` o sección desconocida ⇒ `E_CONFIG_INVALID`.

### UT-DRV-05 — `doctor driver` (AC-02, AC-18, §11.6)

- .01 P Orden de chequeos de macOS y de Windows con `driver` tras `home`.
- .02 P `detail` por driver con `api`, `pkg`, `network`, `readonly`, `body_local`, `attachments` y `native_order`.
- .03 N Un driver declarado incompatible ⇒ `driver` `ok=false` con motivo/hint; `config` `not evaluated: driver failed`; exit 0.
- .04 N `config.toml` inválido ⇒ `driver` valida solo el nativo con `declared drivers: unknown (config failed)`; el error lo reporta `config`.
- .05 P Sin config o sin bloques ⇒ `driver` valida el nativo con `no declared drivers`.
- .06 N Varios drivers declarados (nativo + plugin) ⇒ `detail` los lista todos; si uno falla, `driver` falla y `config` no se evalúa; los chequeos del nativo siguen su curso salvo dependencia.
- .07 N `driver` y `schema`/`stores` fallan a la vez ⇒ `config` informa `not evaluated: driver failed` (el driver se evalúa primero); `schema`/`stores` conservan su dependencia del backend nativo.
- .08 P `driver` aparece exactamente en la posición 3 de la lista ordenada, tanto en macOS como en Windows (plataforma parcheada).

## 5. Documentación del milestone

- `docs/INTERFACES.md`: esquema de configuración, resolución de scope por driver, `[attachments]`, orden/dependencias y `detail` del chequeo `driver`.
- `docs/config.example.toml`: `[attachments]` comentada y ejemplos de `[scope]` con y sin prefijo.

## 6. Criterios de cierre

1. Suite verde sin fallos nuevos; UT-DRV verdes solos; goldens `doctor.json` y `outlook/doctor.json` actualizados solo por el chequeo `driver`; `_OUTLOOK_DOCTOR_CHECKS` y las listas ordenadas de `doctor` actualizadas.
2. Comportamiento de `[scope]` sin prefijo idéntico al de 2.0.1 en macOS/Windows (regresión de los tests existentes).
3. `config.example.toml` parsea con el esquema nuevo y con defaults.
4. Sin tocar `search.py`, `state.py` ni el comportamiento de los comandos de datos fuera del error `E_ACCOUNT_NOT_IN_SCOPE` ya previsto.

## 7. Handoff y HITL

- Reportar: firma final de `resolve_scope`/registro, forma exacta del `detail` de `driver`, tests y golden.
- HITL: si la resolución de cuentas de plugins exige información que el contrato de backend de M01 no expone (p. ej. `accounts()` no devuelve `label`/`uuid` estables), preguntar antes de ampliar el contrato; si un bloque `[scope]` con driver válido pero cuenta con `:` no puede distinguirse del separador, documentar la limitación y no inventar sintaxis.

## 8. Riesgos del milestone

| Riesgo | Mitigación |
|---|---|
| Cambiar la resolución de cuentas rompe Apple Mail 2.0.x | Mantener las formas de §15.2 intactas para backends internos; los tests actuales de `test_config` son la regresión |
| `doctor` cambia su orden y rompe goldens/test de otros módulos | El golden se actualiza en este milestone; M11 verifica que no quede ningún orden antiguo en docs |
| Config inválida + driver no instalado: precedencia ambigua | Aplicar §11.3 fila 3: `E_CONFIG_INVALID` para sintaxis y claves, `E_DRIVER_UNKNOWN` para driver de bloque; documentar el caso en `INTERFACES.md` |

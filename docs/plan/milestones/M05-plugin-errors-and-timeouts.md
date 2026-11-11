# M05 — Protocolo de errores de plugin y timeouts

| Campo | Valor |
|-------|-------|
| Fase | C — Núcleo de datos multi-driver |
| Depende de | M01, M04 |
| Bloquea a | M07, M08–M11 |
| ACs | AC-16; AC-17 (timeout de metadatos de 30 s); AC-19 (log de plugin) |
| Grupos de test | UT-ERR-01..04 |
| Write scope | `src/mailquery/plugins/api.py`, `src/mailquery/plugins/__init__.py`, `src/mailquery/backends/registry.py` (envoltura de llamadas), `src/mailquery/search.py` (solo envoltura de llamadas a drivers), `src/mailquery/cli.py` (solo ruta de log de error), `src/mailquery/output.py` (solo reutilizar `sanitize_text`), `src/mailquery/logging_setup.py` (solo si hace falta), `docs/INTERFACES.md`, `tests/test_plugins.py`, `tests/fakes/plugin.py` (fallos y cuelgues), `tests/test_multidriver.py` (casos de error de runtime) |
| No tocar | `state.py`, `config.py`, `attachments/**` (no existe aún), `PRD.md`, `PRD-v2.1.md`, `docs/plan/**` |
| Estado | ⚪ |

## 1. Objetivo

Implementar el protocolo de errores de los drivers externos: el núcleo posee `code`, `exit` y la plantilla de `message`; el plugin solo aporta `reason`, `hint`, `detail` y `log_message`. Incluye el saneado y los límites de esos campos, el mapeo cerrado `reason` → `code`, el timeout de 30 s por operación de metadatos y las reglas de log.

## 2. Contexto normativo

- PRD-v2.1 §6.3 RF-50, §7 RNF-15/RNF-16, §11.3 fila 14, §11.7 completo (diccionario, propiedad, mapeo `reason`→código, plantillas), §12.1 (log del plugin), §14 AC-16/AC-17/AC-19.
- Base 2.0.1: `errors.py:14-96` (jerarquía y catálogo), `cli.py:1115-1148` (reporte y log de error), `search.py` y `backends/*` (puntos de llamada a drivers), `tests/fakes/plugin.py` (M01).
- Contratos de entrada: C1 (API 1, enum `Reason`) y C4 (puntos de llamada multi-driver de M04).

## 3. Tareas

| ID | Tarea | Archivos | Detalle |
|----|-------|----------|---------|
| M05-T01 | Envoltura de llamadas y mapeo `reason`→error | `plugins/api.py`, `backends/registry.py`, `search.py` | Una única función de envoltura para las operaciones de un driver externo captura `PluginError`, excepciones y tipos inválidos y los traduce al código/exit del núcleo según §11.7, con el contexto de operación (adjuntos o resto). El plugin nunca elige `code` ni `exit`; un `reason` desconocido/inválido, una excepción no mapeada o un tipo de retorno inválido ⇒ `E_PLUGIN_FAILED` (exit 3), nunca `E_INTERNAL`. Un error del núcleo sigue siendo `E_INTERNAL` (exit 1). |
| M05-T02 | Saneado, límites y plantillas | `plugins/api.py`, `output.py` (solo si hace falta reutilizar `sanitize_text`) | `hint` ≤ 300 bytes, `detail` ≤ 200 bytes, `log_message` ≤ 200 bytes, en UTF-8; se eliminan controles; el `detail` se añade al `message` después del motivo separado por `: `. Plantillas por motivo de §11.7 en inglés, dueño del núcleo. El objeto `error` del JSON sigue siendo `{code, message, hint}` sin campos nuevos. |
| M05-T03 | Timeout de metadatos (30 s) | `plugins/api.py`, `backends/registry.py`, `search.py` | Toda operación de metadatos de **cualquier** driver (nativo o externo) pasa por la envoltura con un plazo de 30 s; al vencer ⇒ `E_CLIENT_TIMEOUT` (exit 3), sin reintento automático y sin resultados parciales. El mecanismo más simple: hilo daemon con `deadline` inyectable; un hilo de plugin que no responde no se puede matar y el proceso termina igualmente (riesgo aceptado, PRD §15). El backend nativo conserva además su watchdog COM de 30 s existente. La extracción de 120 s se implementa en M08. |
| M05-T04 | Log de errores de plugin | `cli.py`, `logging_setup.py` (solo si hace falta) | Se registra en nivel `error` el `log_message` saneado en lugar del `message` cuando existe; nunca se registran `hint` ni `detail`; sin traceback para fallos de plugin (solo `E_INTERNAL` registra traceback). Se mantiene la prohibición de uids, nombres, rutas, cuentas, asuntos, cuerpos y términos. |
| M05-T05 | Tests y doble con fallos | `tests/test_plugins.py`, `tests/fakes/plugin.py`, `tests/test_multidriver.py` | El doble de plugin gana fallos configurables (`PluginError` con cada `reason`, excepción no mapeada, retorno inválido, cuelgue con plazo corto inyectable). UT-ERR-01..04. |
| M05-T06 | Documentación | `docs/INTERFACES.md` | Protocolo de errores: enum de `reason`, mapeo a código/exit, plantillas, saneado y límites, timeout de metadatos y reglas de log. |

## 4. Casos de prueba

### UT-ERR-01 — Mapeo `reason`→`code`/exit (AC-16, §11.7)

- .01 P Tabla completa en operación de adjuntos: `invalid_uid`/`not_found` ⇒ `E_USAGE` (2); `not_local`/`not_downloaded`/`unsupported`/`network` ⇒ `E_ATTACHMENT_UNAVAILABLE` (3); `corrupt`/`smime`/`unreadable` ⇒ `E_ATTACHMENT_UNREADABLE` (3); `permission`/`auth` ⇒ `E_PERMISSION` (3); `busy` ⇒ `E_CLIENT_BUSY` (5); `timeout` ⇒ `E_CLIENT_TIMEOUT` (3).
- .02 P Tabla completa en el resto de operaciones: `invalid_uid`/`not_found` ⇒ `E_USAGE`; el resto de motivos de adjunto ⇒ `E_PLUGIN_FAILED`; `permission`/`auth`, `busy`, `timeout` conservan su código.
- .03 N `reason` desconocido, vacío o no string ⇒ `E_PLUGIN_FAILED` (3), nunca `E_INTERNAL`.
- .04 N El plugin intenta fijar `code`/`exit` (p. ej. atributo extra o excepción con código propio) ⇒ se ignora; el código pertenece siempre al conjunto cerrado del núcleo.
- .05 P El objeto `error` es `{code, message, hint}` y el `command` y `generated_at` siguen el contrato de §12.5 del PRD.md.

### UT-ERR-02 — Saneado, límites y plantillas (AC-16/AC-19)

- .01 P `hint` de 301 bytes, `detail` de 201 y `log_message` de 201 se truncan a ≤ 300/200/200 bytes sin partir un carácter.
- .02 N Controles (`\x00`, `\r`, `\n`, ANSI, `\u202e`) en `hint`/`detail`/`log_message` se eliminan.
- .03 P El `message` usa la plantilla del motivo y añade el `detail` saneado después de `: `; caso table-driven con las 8 plantillas de §11.7 (`not available in the local store`, `could not be retrieved from its origin`, `cannot be recovered by driver '<driver>'`, `is corrupt or unreadable`, `is S/MIME protected and cannot be extracted`, `cannot be read: permission denied`, `is temporarily unavailable`, `did not respond within the timeout`) y sus motivos (`not_local`, `not_downloaded`, `unsupported`, `network`, `corrupt`, `unreadable`, `smime`, `permission`, `busy`, `timeout`).
- .04 P El log registra el `log_message` saneado y nunca el `hint` ni el `detail`.
- .05 N `hint`/`detail` con uid, nombre de archivo, ruta, cuenta o término **nunca** llegan al log; el `log_message` se sanea (controles, ≤ 200 bytes). La obligación de que el plugin no incluya PII en `log_message` se prueba en el doble, no como saneado del núcleo.
- .06 P Los `hint` de §11.7 se respetan: `E_DRIVER_UNKNOWN` lista los drivers instalados e indica `pipx inject mailquery <paquete>`; `E_PLUGIN_FAILED` sugiere `run "mailquery doctor"`; el hint de un motivo de adjunto es el del motivo.

### UT-ERR-03 — Fallos no mapeados (AC-16)

- .01 N Excepción no mapeada en una operación ⇒ `E_PLUGIN_FAILED` (3), sin traceback de plugin en el JSON.
- .02 N Tipos de retorno inválidos (fila no dict, `native_id` no string, lista de adjuntos mal formada) ⇒ `E_PLUGIN_FAILED`.
- .03 P Un fallo inesperado del núcleo (no del plugin) sigue siendo `E_INTERNAL` (exit 1), sin cambio.
- .04 N El comando falla sin resultados parciales y cierra los drivers abiertos.

### UT-ERR-04 — Timeout de metadatos (AC-17, RNF-16)

- .01 N Una operación de metadatos de plugin que supera 30 s (plazo inyectado) ⇒ `E_CLIENT_TIMEOUT` (3), sin reintento automático.
- .02 N El timeout no deja resultados parciales ni estado escrito.
- .03 P Una operación por debajo del plazo no se interrumpe.
- .04 N Una operación de metadatos del backend nativo también está envuelta: con plazo inyectado superado ⇒ `E_CLIENT_TIMEOUT` (3), sin tocar el watchdog COM de Outlook.
- .05 N El timeout de una operación durante el merge cierra los drivers abiertos y no emite `messages[]` parcial.

## 5. Documentación del milestone

- `docs/INTERFACES.md`: protocolo de errores de plugin, enum de `reason`, mapeo, plantillas, saneado/límites, timeout de metadatos y log.

## 6. Criterios de cierre

1. Suite verde sin fallos nuevos; UT-ERR verdes solos.
2. Todo error de plugin sale con código del núcleo y exit documentado; ningún camino plugin produce `E_INTERNAL`.
3. El log no incorpora `hint`/`detail` ni PII; el timeout se prueba con plazo inyectado, también en el driver nativo.
4. Sin cambios en `state.py`, `config.py` ni en el contrato de adjuntos de M06.

## 7. Handoff y HITL

- Reportar: forma de la envoltura, tabla de mapeo implementada, límites y mecanismo de timeout, tests y doble.
- HITL: si el timeout por hilo daemon no es aceptable para el dueño por el riesgo de hilo colgado, o si el mapeo por contexto no se puede aplicar sin conocer si la operación es de adjuntos, preguntar antes de cambiar el contrato de llamadas.

## 8. Riesgos del milestone

| Riesgo | Mitigación |
|---|---|
| Hilo de plugin colgado tras el timeout | Daemon + fin del proceso; riesgo aceptado por el PRD §15 |
| Error de plugin enmascarado como `E_INTERNAL` | Test .01/.03 de UT-ERR-01 y .01 de UT-ERR-03 |
| El saneado del núcleo borra información útil del plugin | Se conserva el `log_message` saneado en el log; el `detail` se añade al `message` |

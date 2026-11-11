# M09 — Backend Apple Mail: adjuntos

| Campo | Valor |
|-------|-------|
| Fase | E — Adaptadores de backend |
| Depende de | M08 |
| Bloquea a | M10, M11 |
| ACs | AC-09, AC-10, AC-11, AC-12, AC-15, AC-20 (integración real) |
| Grupos de test | UT-AM-01..04, TC-08 (goldens nuevos), SMOKE-ATT-AM; extensión de TC-03 |
| Write scope | `src/mailquery/backends/apple_mail.py`, `src/mailquery/emlx.py`, `docs/INTERFACES.md`, `tests/fixtures/make_fixtures.py`, `tests/fixtures/expected/attachment_*.json` y `tests/fixtures/expected/show_2714_with_cache.json` (nuevos), `tests/test_backends.py`, `tests/test_integration.py`, `tests/test_readonly.py` (solo TC-03), `tests/test_smoke.py` (solo SMOKE-ATT-AM) |
| No tocar | `cli.py`, `search.py`, `attachments/**`, `backends/outlook*`, `state.py`, `config.py`, `tests/fixtures/expected/show_*.json` existentes (son de M03/M08), `PRD.md`, `PRD-v2.1.md`, `docs/plan/**` |
| Estado | ⚪ |

## 1. Objetivo

Implementar el contrato de adjuntos del backend Apple Mail: metadatos ordenados con `index` estable, nombres originales, disponibilidad local, motivos (`not_local`, `unsupported`, `corrupt`, `smime`) y entrega de bytes decodificados desde el store local, sin escribir en el store. Añadir los fixtures, goldens y el gate de solo lectura que demuestran el flujo completo sobre el almacén sintético y una SMOKE en macOS.

## 2. Contexto normativo

- PRD-v2.1 §4 (I-1 y adjuntos), §6.1 RF-38 (contrato), §6.2 RF-43/45/46/47/48, §10.3, §10.4, §11.3 filas 8–14, §11.5 A–E, §14 AC-09/AC-10/AC-11/AC-12/AC-15/AC-20, §15 (externalizados de `.partial.emlx` y riesgo aceptado).
- Base 2.0.1: `backends/apple_mail.py:245-246,541-546,675-688` (`attachments.name`, `has_attachments`), `emlx.py:127,371-385` (MIME y nombres), `search.py:471-493,518` (`show.attachments`), `tests/fixtures/make_fixtures.py:122-268` (13 mensajes base), `:270-350` (`extended`), `test_readonly.py:168-282` (gate).
- Contratos de entrada: C1 (protocolo v1) y C8 (comando/JSON). El motor (C6/C7) ya está implementado.

## 3. Tareas

| ID | Tarea | Archivos | Detalle |
|----|-------|----------|---------|
| M09-T01 | Metadatos y capacidades | `backends/apple_mail.py` | Declarar `driver = "apple_mail"`, `plugin_api = 1`, capacidades `network: false`, `readonly: "structural"`, `body_local: true`, `attachments: "local"`, `native_order: "numeric"`; `parse_native_id` valida el entero legado. El backend sigue siendo solo lectura sobre el store. |
| M09-T02 | Metadatos de adjuntos | `backends/apple_mail.py`, `emlx.py` | Entregar la lista ordenada con `index` 1..N (mismo orden que `show`), `name` original, tamaño esperado si está disponible y motivo de no disponibilidad. Con cuerpo legible, los nombres salen del MIME (mismo `walk()` que 2.0.1, sin duplicados); con cuerpo ilegible **no S/MIME**, del `Envelope Index` como en 2.0.1 (`W_ATTACHMENTS_UNAVAILABLE` de `show` se mantiene solo para cuerpo ilegible). **S/MIME es la excepción**: `show` devuelve `attachments: []` (RF-43) y `attachment` propaga `smime` ⇒ `E_ATTACHMENT_UNREADABLE`; no se listan nombres del índice para S/MIME. Motivos: `.emlx`/archivo ausente ⇒ `not_local`; adjunto externalizado de `.partial.emlx` no verificable ⇒ `unsupported`; MIME/base64 corrupto ⇒ `corrupt`; sin adjuntos ⇒ `[]` sin motivo. |
| M09-T03 | Stream de bytes decodificado | `emlx.py`, `backends/apple_mail.py` | Operación que devuelve el flujo de bytes **decodificado** (base64/quoted-printable) del adjunto por `index`, sin escribir en disco ni en el store y sin cargar todo el mensaje si no hace falta. Un error de decodificación/lectura se propaga como `corrupt`/`unreadable` para que el motor decida `E_ATTACHMENT_UNREADABLE`. |
| M09-T04 | Integración con `show` y `attachment` | `tests/fixtures/make_fixtures.py`, `tests/fixtures/expected/show_2714_with_cache.json` (nuevo) | Comprobar que `show` y `attachment` comparten índices y nombres, que `cached_path` se calcula con el nombre sanitizado y que el flujo completo escribe bajo `~/.mailquery/attachments/`. Los goldens `show_*` existentes **ya fueron actualizados en M08** y no se reescriben aquí; el único golden nuevo es `show_2714_with_cache.json`, con una caché pre-sembrada de forma determinista y `cached_path` no nulo. |
| M09-T05 | Fixtures de adjuntos | `tests/fixtures/make_fixtures.py` | Añadir un flag `build_store(..., attachments=False)` (default sin cambios) y, con `attachments=True`, los casos: mensaje con 3 adjuntos (dos con el mismo nombre), nombres hostiles (traversal, RLO, `CON.fdp.exe`, doble extensión), adjunto con contenido ejecutable (MZ), adjunto vacío (0 bytes), S/MIME cifrado con fila de adjuntos, `.partial.emlx` con adjunto externalizado, mensaje sin adjuntos, nombres Unicode/largos y un adjunto de ~1,5 MiB para el límite. Los 18 goldens existentes se generan con el default y no cambian por este milestone. |
| M09-T06 | Goldens de `attachment` | `tests/fixtures/expected/attachment_saved.json`, `attachment_cached.json`, `attachment_blocked_name.json`, `attachment_blocked_content.json`, `attachment_too_large.json`, `show_2714_with_cache.json` (nuevos) | Flujos de punta a punta: extracción nueva, acierto de caché (primera corrida documentada que siembra la caché; la segunda genera el golden), bloqueo por nombre (ejemplo C) y por contenido (ejemplo D), límite excedido conocido (exit 4) y `show` con caché previa. El límite usa una config de fixture con `max_file_size_mb = 1` y el adjunto de ~1,5 MiB de M09-T05. Rutas normalizadas a `<ROOT>`/`<HOME>` según el normalizador real (`self.fx.root` ⇒ `<ROOT>`), `sha256`/`size_bytes` fijos de los fixtures. |
| M09-T07 | Gate de solo lectura | `tests/test_readonly.py` (solo TC-03) | Extender TC-03 al nuevo comando: barrido de `show`/`attachment` (éxito, caché, bloqueado, límite, S/MIME) sobre el fixture `extended`; hashes y `mtime` del store sin cambios; ninguna escritura fuera de `~/.mailquery`; permisos del almacén intactos; staging limpio. TC-03 es de macOS; OL-30 (Windows) es de M10 y no se toca aquí. |
| M09-T08 | SMOKE-ATT-AM (macOS) | `tests/test_smoke.py` | Clase `SmokeAttAppleMail` con skip de plataforma (no macOS ⇒ skip) y `HOME` temporal: localizar un mensaje con adjunto local de `mailboxes`/`search` (si no hay, skip), ejecutar `show` y `attachment --index 1`; verificar exit 0, archivo bajo `~/.mailquery/attachments`, `0600`, `sha256` calculado por el test sobre el archivo, y que los contadores del store no cambian. Sin umbrales de tiempo duros (el presupuesto de caché es de M11). |
| M09-T09 | Documentación | `docs/INTERFACES.md` | Sección Apple Mail: capacidades, índice, nombres, motivos, decodificación, límites y relación con `show`/`attachment`. |

## 4. Casos de prueba

### UT-AM-01 — Bloqueo con fixtures reales (AC-09/AC-10)

- .01 N Mensaje con un adjunto hostil y otro seguro: `--index` del seguro, `--index` del hostil y `--all` ⇒ `E_ATTACHMENT_BLOCKED` (exit 4); nada escrito.
- .02 N Nombres con traversal, separadores, `..`, `C:`, ADS, RLO/controles y reservado de Windows desde el fixture ⇒ bloqueo del mensaje.
- .03 N Adjunto con `MZ` en los primeros bytes ⇒ bloqueo del mensaje; un archivo seguro del mismo mensaje no se escribe.
- .04 N Mensaje con un adjunto no solicitado hostil: `--index` de un seguro ⇒ bloqueo (regla de todos los nombres).
- .05 P Mensaje con todos los adjuntos permitidos ⇒ extracción correcta.

### UT-AM-02 — Índices, nombres y sanitización (AC-07/AC-11)

- .01 P Tres adjuntos con dos nombres repetidos ⇒ índices 1..N estables y distintos archivos `<NN>_<sanitized>`.
- .02 P `show` y `attachment` devuelven el mismo `index` y el mismo `name` original para cada adjunto.
- .03 P Sanitización sobre nombres Unicode/largos del fixture: NFKC, reemplazos, límites de 150/153 bytes y ruta final correcta.
- .04 P `cached_path` de `show` apunta al archivo regular publicado.

### UT-AM-03 — Extracción y disponibilidad (AC-12/AC-15/AC-20)

- .01 P Primera extracción `cached: false`; segunda `cached: true`; `--force` re-extrae.
- .02 N Adjunto cuyo `.emlx` no existe ⇒ `E_ATTACHMENT_UNAVAILABLE` (`not_local`).
- .03 N Adjunto externalizado de `.partial.emlx` no verificable ⇒ `E_ATTACHMENT_UNAVAILABLE` (`unsupported`).
- .04 N `--all` con un adjunto externalizado no verificable falla sin parciales; `--index` de un adjunto local seguro del mismo mensaje tiene éxito y no evalúa el externalizado no solicitado.
- .05 N S/MIME cifrado ⇒ `E_ATTACHMENT_UNREADABLE` (`smime`), nunca `E_USAGE`; `show` devuelve `[]`.
- .06 N MIME/base64 corrupto ⇒ `E_ATTACHMENT_UNREADABLE` (`corrupt`).
- .07 P Adjunto de 0 bytes se guarda con `size_bytes: 0` y `sha256` del vacío.
- .08 P Archivo de caché borrado antes de `attachment` ⇒ se re-extrae una vez.
- .09 N Un fallo en `--all` no deja archivos parciales ni caché nueva incompleta.

### UT-AM-04 — Solo lectura e integración (AC-12, RNF-13)

- .01 P Tras `attachment` (éxito, caché, bloqueo, límite), hashes y `mtime` del store no cambian.
- .02 P Todas las escrituras quedan bajo `~/.mailquery` (`attachments/`, `tmp/`, log/lock/estado); staging limpio.
- .03 P Directorios `0700` y archivos `0600` en POSIX; sin `+x` (condición POSIX explícita; en Windows se prueba la herencia de ACL y no se relajan permisos).
- .04 P El backend declara las capacidades de §6.1/RF-38 y `attachments: "local"`; `doctor` las muestra (M02).

### TC-08 — Goldens de adjuntos Apple Mail (nuevos)

- .01 P `attachment --index 2` ⇒ `attachment_saved.json` (`cached:false`, ruta/tamaño/sha256).
- .02 P Primera corrida que siembra la caché y segunda corrida ⇒ `attachment_cached.json` (`cached:true`, mismo hash); la siembra se documenta en el test.
- .03 N Mensaje con adjunto de nombre hostil ⇒ `attachment_blocked_name.json` (exit 4, sin cambios en caché).
- .04 N Mensaje con contenido ejecutable (`MZ`) ⇒ `attachment_blocked_content.json` (exit 4, sin cambios en caché).
- .05 N `max_file_size_mb` excedido con tamaño conocido ⇒ `attachment_too_large.json` (exit 4).
- .06 P `show` de un mensaje con caché previa ⇒ `show_2714_with_cache.json` con `cached_path` absoluto.

### SMOKE-ATT-AM (macOS)

- .01 P `show <uid>` de un mensaje con adjunto local ⇒ exit 0 y `attachments[]` con `index`/`name`.
- .02 P `attachment <uid> --index 1` ⇒ exit 0, archivo `0600` bajo `~/.mailquery/attachments`, `sha256` coincide con el archivo, store sin cambios.
- .03 P Segunda corrida ⇒ `cached:true` (sin umbral de tiempo).
- .04 B Sin mensaje con adjunto local o sin Apple Mail ⇒ skip documentado (no fallo); la clase declara el skip por plataforma.

## 5. Documentación del milestone

- `docs/INTERFACES.md`: contrato Apple Mail de adjuntos (capacidades, índice, motivos, decodificación, fixtures y límites), con la excepción S/MIME `show: []`.

## 6. Criterios de cierre

1. Suite verde sin fallos nuevos; UT-AM y TC-08 verdes solos; SMOKE-ATT-AM ejecutada o saltada con motivo.
2. Gate de solo lectura extendido en verde para `attachment` (TC-03; OL-30 es de M10).
3. El flujo completo funciona sobre el fixture y los goldens nuevos son deterministas.
4. Sin cambios en el motor, la CLI ni el contrato JSON.

## 7. Handoff y HITL

- Reportar: motivos implementados, comportamiento de `.partial.emlx`, goldens nuevos, resultado de la SMOKE y del gate.
- HITL: solo si Apple Mail entrega nombres distintos entre `show` y `attachment` para el mismo mensaje; el externalizado no verificable ya está decidido (`unsupported`, D12/riesgo aceptado).

## 8. Riesgos del milestone

| Riesgo | Mitigación |
|---|---|
| Adjuntos externalizados no verificables en producción | Motivo `unsupported` + riesgo aceptado PRD §15; SMOKE best-effort |
| Fixtures que no representan el MIME real | Se construyen con el mismo parser de 2.0.1 y se validan contra `show`; SMOKE con cliente real |
| El mensaje bloqueado pierde adjuntos legítimos | Comportamiento normativo (PRD §15); se documenta en M11 |

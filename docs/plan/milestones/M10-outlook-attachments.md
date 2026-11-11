# M10 — Backend Outlook: adjuntos

| Campo | Valor |
|-------|-------|
| Fase | E — Adaptadores de backend |
| Depende de | M08, M09 |
| Bloquea a | M11 |
| ACs | AC-10, AC-12, AC-15, AC-17 (Outlook), AC-19, AC-20 (integración); RNF-13/RNF-16 |
| Grupos de test | UT-OL-ATT-01..04, TC-09 (nuevos), SMOKE-ATT-OL (Windows); extensión de OL-30 |
| Write scope | `src/mailquery/backends/outlook.py`, `src/mailquery/backends/outlook_com.py`, `docs/INTERFACES.md`, `docs/security/threat-model.md`, `tests/fakes/outlook.py`, `tests/test_outlook.py`, `tests/test_integration.py`, `tests/fixtures/expected/outlook/attachment_*.json` (nuevos), `tests/test_readonly.py` (solo OL-30), `tests/test_smoke.py` (solo SMOKE-ATT-OL) |
| No tocar | `cli.py`, `search.py`, `attachments/**`, `backends/apple_mail.py`, `state.py`, `config.py`, `tests/fixtures/expected/outlook/show*.json` (son de M03/M08), `PRD.md`, `PRD-v2.1.md`, `docs/plan/**` |
| Estado | ⚪ |

## 1. Objetivo

Implementar el contrato de adjuntos del backend Outlook clásico: metadatos locales, disponibilidad sin forzar descarga, materialización controlada del adjunto ya descargado mediante la excepción de COM (`Attachment.SaveAsFile`/`GetTemporaryFilePath`), entrega de bytes, motivos y timeouts, con el doble de Outlook y la SMOKE de Windows.

## 2. Contexto normativo

- PRD-v2.1 §0.2 (fila de la excepción COM), §4 (I-1 y adjuntos), §6.1 RF-38, §6.2 RF-43/45/46/47/48, §7 RNF-13/RNF-16, §11.3 fila 14, §11.5 E/F, §14 AC-10/AC-12/AC-15/AC-17/AC-19, §15 (riesgos de COM, materialización y OMG).
- Base 2.0.1: `backends/outlook.py:729-740,1419-1430` (nombres y adjuntos ocultos), `backends/outlook_com.py` (proxy `ReadOnlyCom`, lista blanca, `Watchdog`, `call_com`, detección), `tests/fakes/outlook.py:822-1078` (`AttachmentSpec` y specs), `:1638-1761` (`FakeOutlook`), `tests/test_outlook.py` (OL-01, OL-30), `tests/test_readonly.py`.
- Contratos de entrada: C1 (protocolo v1) y C8 (comando/JSON). La excepción COM debe quedar documentada en `INTERFACES.md` y en el modelo de amenazas.

## 3. Tareas

| ID | Tarea | Archivos | Detalle |
|----|-------|----------|---------|
| M10-T01 | Metadatos y capacidades | `backends/outlook.py` | Declarar `driver = "outlook"`, `plugin_api = 1`, capacidades `network: false`, `readonly: "structural"`, `body_local: true`, `attachments: "local"`, `native_order: "text"`; `parse_native_id` valida `EntryID` hexadecimal en mayúsculas. |
| M10-T02 | Metadatos de adjuntos y disponibilidad | `backends/outlook.py` | Lista ordenada con `index` 1..N (mismo orden que `show`), `name` original (`FileName`/`DisplayName`, excluyendo `PR_ATTACHMENT_HIDDEN`), tamaño esperado si la propiedad local lo da. La disponibilidad local se determina **solo con propiedades locales del item**; no se puede forzar descarga: si no se puede saber sin descargar ⇒ `not_downloaded`; S/MIME ⇒ `smime`; corrupto/ilegible ⇒ `corrupt`/`unreadable`; tipo no soportado ⇒ `unsupported`. Sin adjuntos ⇒ `[]` sin motivo. |
| M10-T03 | Materialización COM | `backends/outlook_com.py`, `backends/outlook.py` | Añadir a la lista blanca del proxy de solo lectura **solo** las operaciones de materialización de un adjunto ya descargado (`Attachment.SaveAsFile` y `GetTemporaryFilePath`, según PRD §0.2) y usarlas únicamente en el flujo de extracción. El archivo temporal se crea dentro del directorio `0700` de staging del núcleo (`~/.mailquery/tmp/staging/`), con nombre opaco y `0600`/ACL del perfil; el núcleo comprueba que es un archivo regular dentro de staging (no symlink), lee los bytes, valida el primer bloque antes de promover a la caché y lo borra siempre. `object_model_guard` **no** se extiende a esta operación en 3.0.0 (riesgo aceptado). |
| M10-T04 | Timeouts | `backends/outlook_com.py`, `backends/outlook.py` | Toda llamada COM, incluida la materialización, sigue el límite de 30 s por llamada de RF-33 (watchdog existente) y el tope total de 120 s de extracción del núcleo (M08) no amplía ese límite. Al vencer ⇒ `E_CLIENT_TIMEOUT` (exit 3), staging limpio, sin archivos nuevos. Un aviso bloqueante del OMG se traduce en `E_CLIENT_TIMEOUT` o `E_PERMISSION`. |
| M10-T05 | Doble de Outlook | `tests/fakes/outlook.py` | Ampliar `AttachmentSpec` con contenido, tamaño, nombres, oculto, S/MIME, corrupto, no descargado, permiso y cuelgue; `SaveAsFile` escribe en el archivo temporal indicado y registra la materialización en el `CallLog`; el contador de mutaciones del buzón debe quedar en cero. Escenario nuevo para adjuntos. |
| M10-T06 | Goldens de Outlook | `tests/fixtures/expected/outlook/attachment_*.json` (nuevos), `tests/test_integration.py` | Añadir `outlook/attachment_saved.json`, `outlook/attachment_cached.json`, `outlook/attachment_unavailable.json` y `outlook/attachment_blocked.json`; `attachment_cached` documenta la primera corrida que siembra la caché. Rutas normalizadas con el normalizador real (`self.fx.root` ⇒ `<ROOT>`, no `<HOME>`). Los `outlook/show*.json` **ya se actualizaron en M08** (forma y valor) y no se reescriben aquí; el caso header-only de `show` se prueba contra ellos. |
| M10-T07 | Gate de solo lectura | `tests/test_readonly.py` (solo OL-30) | Ampliar el barrido con `attachment` en Outlook: miembros invocados ⊆ lista blanca (incluida la excepción de materialización), 0 asignaciones, 0 mutaciones del buzón, ninguna escritura en el store, temporales solo bajo `~/.mailquery/tmp/staging` y borrados. OL-30 es el gate de Windows; TC-03 (macOS) es de M09 y no se toca. |
| M10-T08 | SMOKE-ATT-OL (Windows) | `tests/test_smoke.py` (clase `SmokeAttOutlook`, skip fuera de Windows) | En el host del dueño con Outlook clásico abierto: localizar un mensaje con adjunto local, ejecutar `show` y `attachment --index 1`; exit 0, archivo bajo `~/.mailquery/attachments`, tamaño/hash coherentes, store y no leídos sin cambios; skip si no hay Outlook o adjunto local. Sin umbrales de tiempo duros. |
| M10-T09 | Documentación | `docs/INTERFACES.md`, `docs/security/threat-model.md` | Documentar la excepción COM de materialización (operación, staging, borrado, timeouts, OMG no extendido), las capacidades de Outlook y los motivos de adjunto; actualizar el modelo de amenazas para que no contradiga la excepción. |

## 4. Casos de prueba

### UT-OL-ATT-01 — Metadatos, índice y disponibilidad (AC-07/AC-15)

- .01 P `show` y `attachment` comparten `index` 1..N y `name` original; adjuntos ocultos no se listan.
- .02 P Un adjunto local devuelve tamaño esperado estable y se extrae.
- .03 N Un adjunto no descargado (solo propiedades locales) ⇒ `E_ATTACHMENT_UNAVAILABLE` (`not_downloaded`), sin llamada de descarga y sin red.
- .04 N S/MIME ⇒ `E_ATTACHMENT_UNREADABLE` (`smime`) y `show` devuelve `[]`.
- .05 N Corrupto/ilegible ⇒ `E_ATTACHMENT_UNREADABLE` (`corrupt`/`unreadable`); tipo no soportado ⇒ `E_ATTACHMENT_UNAVAILABLE` (`unsupported`).
- .06 N El `CallLog` no registra miembros de descarga ni de red durante los metadatos.
- .07 N `show` de un item header-only con `has_attachments` ⇒ `attachments: []` y `W_ATTACHMENTS_UNAVAILABLE` (cuerpo ilegible), sin nombres del índice y sin `E_USAGE`; usa `outlook/show_header_only.json`.

### UT-OL-ATT-02 — Materialización COM (AC-10/AC-12, §15)

- .01 P Un adjunto local se materializa con `SaveAsFile`/`GetTemporaryFilePath` en el staging `0700`; el archivo es regular, no symlink, `0600`/ACL del perfil; el núcleo lo lee y lo publica con la validación del motor.
- .02 N La materialización se rechaza si el archivo temporal no está dentro de `tmp/staging` o es un symlink ⇒ `E_ATTACHMENT_UNAVAILABLE` (`unsupported`) antes de publicar (D12), sin código interno.
- .03 N Un adjunto con contenido ejecutable en el archivo materializado ⇒ mensaje bloqueado (M06), archivo temporal borrado, nada publicado.
- .04 P El archivo temporal se borra también cuando la extracción falla o el timeout vence.
- .05 N La lista blanca del proxy solo añade las dos operaciones de materialización; cualquier otra operación sigue dando `E_INTERNAL` (OL-01).
- .06 N `object_model_guard` no bloquea la operación de materialización (decisión interna, sin señal observable); el caso solo afirma timeout/permiso y lista blanca, y el riesgo queda documentado.

### UT-OL-ATT-03 — Errores, timeout y motivos (AC-15/AC-17)

- .01 N `E_ACCESSDENIED` en la materialización ⇒ `E_PERMISSION` (3).
- .02 N Rechazo transitorio persistente ⇒ `E_CLIENT_BUSY` (5), sin afirmar un número concreto de reintentos salvo que el PRD.md §17 lo mantenga; el doble registra la secuencia.
- .03 N Una llamada COM de materialización que supera 30 s ⇒ `E_CLIENT_TIMEOUT` (3), staging limpio.
- .04 N El tope total de 120 s del núcleo vence aunque cada llamada COM esté por debajo de 30 s ⇒ `E_CLIENT_TIMEOUT`.
- .05 N Un fallo de materialización en `--all` no produce resultados parciales.
- .06 P Un adjunto de 0 bytes se materializa y publica con `size_bytes: 0`.

### UT-OL-ATT-04 — Solo lectura y log (AC-19, RNF-13)

- .01 P 0 mutaciones del buzón y 0 asignaciones durante todas las extracciones; el `CallLog` muestra solo miembros de la lista blanca.
- .02 P Ninguna escritura fuera de `~/.mailquery`: store, mensajes y flags intactos.
- .03 N El log no registra uids, `EntryID`, `StoreID`, nombres, rutas ni cuentas.
- .04 P `event=end` de `attachment` conserva `count`, `cached`, `bytes`, `duration_ms`.

### TC-09 — Goldens de adjuntos Outlook (nuevos)

- .01 P `attachment_saved.json` (`cached:false`, ruta/tamaño/hash).
- .02 P `attachment_cached.json` (`cached:true`; primera corrida documentada que siembra la caché).
- .03 N `attachment_unavailable.json` (`not_downloaded`, exit 3).
- .04 N `attachment_blocked.json` (contenido ejecutable, exit 4).
- .05 P `outlook/show*.json` ya actualizados en M08: el test solo comprueba que la forma `{index,name,cached_path}` coincide con M08 (no se reescribe el golden).

### SMOKE-ATT-OL (Windows)

- .01 P `show <uid>` de un mensaje con adjunto local ⇒ `attachments[]` con `index`/`name`.
- .02 P `attachment <uid> --index 1` ⇒ exit 0, archivo bajo `~/.mailquery/attachments`, tamaño/hash coherentes, store y no leídos sin cambios.
- .03 B Sin Outlook o sin adjunto local ⇒ skip documentado; la clase declara el skip por plataforma.

## 5. Documentación del milestone

- `docs/INTERFACES.md`: contrato de adjuntos de Outlook, lista blanca COM ampliada, staging, timers, motivos y límites.
- `docs/security/threat-model.md`: excepción de materialización y frontera de confianza, sin contradicciones con I-1 (el buzón no se modifica; solo se escribe en `tmp/`).

## 6. Criterios de cierre

1. Suite verde sin fallos nuevos; UT-OL-ATT y TC-09 verdes solos; SMOKE-ATT-OL ejecutada o saltada con motivo.
2. Gate de solo lectura de Outlook (OL-30) en verde con `attachment` (0 mutaciones, lista blanca).
3. Staging siempre limpio, incluso en errores y timeouts.
4. Sin cambios en `cli.py`, el motor ni el contrato JSON.

## 7. Handoff y HITL

- Reportar: operaciones COM añadidas, comportamiento de disponibilidad, resultados del doble y de la SMOKE, cambios en el modelo de amenazas.
- HITL: solo si la determinación de “ya descargado” exige una llamada que puede disparar descarga en algún escenario; el host Windows sin verificación de materialización ya está aceptado como riesgo (§15) y no bloquea el cierre.

## 8. Riesgos del milestone

| Riesgo | Mitigación |
|---|---|
| `Attachment.SaveAsFile` fuera de la lista blanca y aviso del OMG | Excepción documentada, la operación solo se usa para adjuntos locales en staging; aviso bloqueante ⇒ timeout/permiso; riesgo aceptado §15 |
| Materialización que dispara descarga | Solo propiedades locales para disponibilidad; si no se puede determinar ⇒ `not_downloaded` |
| El doble no reproduce el COM real | SMOKE en Windows del dueño; el doble cubre contrato y fallos; riesgo aceptado |

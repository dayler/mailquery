# M09 — `attachment`: drivers `"remote"`, tope configurable y contenido activo (F2 + A7)

**Lote:** I3 · rama del lote `integration/i3-attachments-rows` · **Oleada:** W4 (sola)
**Rama:** `feature/m09-attachments-remote-timeout-active`, creada desde la punta de `integration/i3-attachments-rows` (abierta desde `develop` con el lote I2 mergeado) · **Worktree:** `../mailquery-wt/m09`
**Estado:** 🟡 (fases F1–F6 cerradas; pendiente de integración) (leyenda y protocolo en [`00-master-plan.md`](00-master-plan.md))

## 1. Objetivo

Corregir BUG-01 (RF-67: `attachment` extrae de drivers `attachments: "remote"`), sustituir el tope fijo de 120 s por `[attachments].timeout_seconds` con corte duro en los plugins externos (RF-68, RNF-22) y añadir `W_ATTACHMENT_ACTIVE_CONTENT` a la respuesta de `attachment` con el detector de M04 (RF-62).

## 2. Alcance

**Dentro:**

1. **Capacidad (`src/mailquery/cli.py`, `_require_attachment_capabilities`):** solo `attachments: "none"` se rechaza en la fila 5 de la precedencia, con `E_ATTACHMENT_UNAVAILABLE` (`unsupported`, exit 3) y el hint `install or declare a driver with attachments = "local" or "remote" in the [scope] blocks of ~/.mailquery/config.toml`. `"remote"` sigue el mismo flujo que `"local"`: filas 6–15, bloqueo por nombre y contenido, límites, SHA-256, staging, caché, manifiesto, `--force` (vuelve a pedir los bytes) y A7. Un acierto de caché no pide bytes al plugin. Un adjunto que el plugin no puede obtener ⇒ `E_ATTACHMENT_UNAVAILABLE` con el `reason` del plugin y su plantilla (mapeo actual de `plugins/api.py`); la capacidad `"remote"` nunca da `unsupported`. El núcleo no abre red. `show` no cambia.
2. **Configuración (`src/mailquery/config.py`):** `[attachments].timeout_seconds`, entero de 10 a 600 (un `bool` no es entero), por defecto `60`; fuera de rango o de otro tipo ⇒ `E_CONFIG_INVALID` (exit 2) en cualquier comando, antes de abrir el store. `AttachmentsConfig.timeout_seconds`; `ATTACHMENTS_KEYS` lo incluye.
3. **Tope por adjunto (RF-68, RNF-22):**
   - `cli.py` obtiene el valor con `_attachment_timeout(config) -> float` (seam de test, D-07) y pasa al motor la factoría `lambda: time.monotonic() + timeout`; ya no usa `EXTRACTION_TIMEOUT_SECONDS`. La constante se conserva en `src/mailquery/plugins/api.py` (la exporta `plugins/__init__.py` y la documenta `INTERFACES.md`) con el valor `60.0`, como valor por defecto documentado; la única fuente efectiva del tope es `config.py` (D-11). `plugins/__init__.py` no cambia.
   - El tope empieza al pedir los bytes del adjunto e incluye la comprobación de *magic bytes* y la escritura en staging; no incluye A7 ni un acierto de caché (el motor ya llama a la factoría solo para lo que extrae; se verifica).
   - **Corte duro en plugins externos:** la espera de la creación del flujo y de cada bloque de bytes se hace en un hilo aparte con el tiempo que le queda al adjunto; al vencer, el motor deja de esperar aunque el plugin siga bloqueado. Hoy `attachment_stream` está en `METADATA_OPERATIONS` y `_run_attachment` envuelve el driver con `wrap_driver`, así que la creación del flujo queda cortada por `METADATA_TIMEOUT_SECONDS` (30 s) con el mensaje de metadatos: en un driver externo, ni la creación de `attachment_stream` ni cada bloque usan `METADATA_TIMEOUT_SECONDS`; los dos usan el tiempo restante del tope del adjunto y, al vencer, producen el `E_CLIENT_TIMEOUT` de RF-68 con su mensaje y su hint. Como `attachments/**` no importa `mailquery.plugins`, el corte se implementa en `src/mailquery/plugins/api.py` (p. ej. el proxy de `attachment_stream` de un driver no nativo devuelve un iterador que obtiene cada bloque con `_run_with_deadline`) y el motor le comunica el instante límite por una vía que no rompa su independencia (p. ej. un parámetro opcional del motor `stream_guard` que `cli.py` rellena para drivers externos). El diseño concreto lo elige el subagente dentro de esas reglas y lo documenta en el bloque de `INTERFACES.md`. Casos que el diseño debe cubrir: una excepción ajena al tope dentro del hilo (p. ej. `reason: network` en el segundo bloque) se propaga con su error; un plazo ya vencido antes de pedir el siguiente bloque da `E_CLIENT_TIMEOUT` sin llamar al plugin; un flujo vacío termina sin error; si `close()` del iterador del plugin lanza al vencer el plazo, el error sigue siendo `E_CLIENT_TIMEOUT`; con `stream_guard=None` (drivers nativos) el motor se comporta como hoy.
   - **Nativos (Apple Mail, Outlook):** el tope se comprueba entre bloques y al terminar cada llamada (como hoy); en Outlook, toda llamada COM sigue con los 30 s de RF-33, que la clave no amplía ni acorta.
   - Al vencer ⇒ `E_CLIENT_TIMEOUT` (exit 3), sin reintento, staging limpio, sin archivos nuevos, con el mensaje actual (`attachment <i> ('<nombre>') of message <uid> did not respond within the timeout`) y el hint `raise [attachments].timeout_seconds in ~/.mailquery/config.toml if the driver is slow; run "mailquery doctor" and do not retry in a loop`. Si vencen antes los 30 s de una llamada COM, el error conserva el mensaje y el hint de RF-33. Con `--all` y varios fallos, se informa el primero en orden de índice (PRD-v2.2 sección 10, punto 10).
4. **A7 (RF-62):** después de extraer o de servir desde la caché, para cada adjunto devuelto en `attachments[]`, `attachments.active_content.active_content_types(path)` y un warning `W_ATTACHMENT_ACTIVE_CONTENT: attachment <index> contains <tipo> in <uid>` por adjunto y tipo, en el orden de `attachments[]` (y de `ACTIVE_CONTENT_TYPES` dentro de un adjunto). Fuera del tope. El archivo se entrega igual y el exit no cambia. Un adjunto bloqueado por el catálogo sigue dando `E_ATTACHMENT_BLOCKED` (no se llega a A7). Los warnings pasan por el A2 central de M07.
5. **Documentación:** ver sección 9.

6. **Textos obsoletos de F2 en documentos consumidores:** el comentario final de `docs/config.example.toml` ("`[attachments]` accepts only `enabled`, `max_file_size_mb`, `max_total_size_mb` and `max_count`…") añade `timeout_seconds`; las filas `E_CLIENT_TIMEOUT` y `E_ATTACHMENT_UNAVAILABLE` de "Troubleshooting" de los dos README describen el tope configurable de `attachment` y los drivers `"remote"`; en `docs/recipes/01-new-mail-digest.md` ("`mailquery attachment` solo copia adjuntos que ya están en el store local") y en las filas `E_CLIENT_TIMEOUT` de las recetas 01 y 02 se añaden la recuperación desde drivers `"remote"` y el tope configurable de `attachment`.

**Fuera:** los 30 s de metadatos y de COM (no cambian); un tope total por comando; detener el hilo de un plugin colgado (riesgo aceptado).

## 3. Dependencias y ACs

- **Entrada:** M04 (detector), M07 (`content_notice`, `original_name` y `warnings[]` saneados en `attachment`); lote I2 mergeado.
- **Salida:** M10 (orden de archivos: `cli.py`, `config.py`, README, skill).
- **ACs:** AC-H12 (conexión con `attachment`, caché, orden), AC-D01–AC-D06, AC-H18 (regla de A7 en la skill).

## 4. Archivos

| Acción | Archivo |
|---|---|
| Modifica | `src/mailquery/cli.py`, `src/mailquery/config.py`, `src/mailquery/attachments/engine.py`, `src/mailquery/plugins/api.py`; `src/mailquery/attachments/__init__.py` si se exporta el detector |
| Modifica | `README.md`, `README.es.md`, `skills/mailquery/SKILL.md`, `docs/config.example.toml`, `docs/KNOWN-DEFECTS.md`, `docs/recipes/01-new-mail-digest.md`, `docs/recipes/02-search-invoices.md` |
| Crea | `tests/test_remote_attachments.py` |
| Modifica | `tests/test_active_content.py` (creado por M04; añade UT-ACT-05), `tests/test_config.py` (UT-CFG-04), `tests/test_cli.py` (UT-ATC-07, UT-ATC-10.03), `tests/test_outlook.py` (UT-OL-ATT-03.04: texto y docstring con el tope configurado), `tests/test_integration.py` (DOC-06.05, DOC-01.03 si se amplía), `tests/fakes/plugin.py` y `tests/fakes/attachment_backend.py` (bloqueo antes del primer bloque y entre bloques, contador de peticiones de bytes) |
| Modifica si los cambios los rompen | `tests/test_attachments.py`, `tests/test_plugins.py`, `tests/test_multidriver.py`, `tests/fakes/attachment_driver.py` |
| Modifica si hace falta (D-18, justificado en la evidencia (c)) | `tests/fixtures/expected/**` (goldens) |
| Bloques para el orquestador | `docs/TEST-CATALOG.md` (secciones 2, 7, 8, 9), `docs/INTERFACES.md` (`attachments/engine.py`, `plugins/api.py`, `cli.py`, `config.py`, sección 4 `attachment`) |

## 5. Refactorizaciones previas

Ninguna.

## 6. Fases

| Fase | Tareas | Estado |
|---|---|---|
| F1 — Configuración | `timeout_seconds`; UT-CFG-04 | 🟢 |
| F2 — `"remote"` | Capacidad; UT-RMT-01, UT-RMT-02, UT-RMT-03; retirar UT-ATC-10.03 | 🟢 |
| F3 — Tope | Seam `_attachment_timeout`, corte duro para externos, nativos entre bloques; UT-RMT-04, UT-RMT-05; UT-ATC-07 | 🟢 |
| F4 — A7 | Warnings tras extraer o servir desde caché; UT-ACT-05 | 🟢 |
| F5 — Documentación | Sección 9; DOC-06.05 | 🟢 |
| F6 — Cierre | Suite completa, evidencia cruda, bloques | 🟢 |

## 7. Tests

**UT-RMT-01 — Extracción desde un plugin `"remote"`** (nuevo) · `tests/test_remote_attachments.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Plugin falso `attachments: "remote"`, `network: true`: `attachment <driver>:<id> --index N` devuelve el JSON de `PRD.md` sección 12.11 (con `content_notice`) y escribe el archivo en la caché. |
| .02 | P | `--all` devuelve todos los adjuntos con `count` correcto; bloqueo por nombre y por contenido y límites (`max_file_size_mb`, `max_total_size_mb`, `max_count`) se comportan igual que con un plugin `"local"` equivalente. |
| .03 | P | Segunda corrida: `cached: true` y el plugin no recibe peticiones de bytes (contador del doble); `--force`: las vuelve a pedir. |
| .04 | B | El núcleo no abre conexiones (`socket.socket` parcheado para fallar durante toda la corrida). |
| .05 | P | El manifiesto escrito es igual al de un plugin `"local"` equivalente con los mismos bytes (salvo marcas de tiempo y el nombre del driver). |

**UT-RMT-02 — Fallo de origen del plugin `"remote"`**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | `reason: network` ⇒ `E_ATTACHMENT_UNAVAILABLE`, exit 3, con la plantilla de ese motivo; nunca `unsupported`. |
| .02 | N | `reason: not_local` ⇒ ídem con su plantilla. |
| .03 | B | Staging limpio y ningún archivo nuevo en la caché. |
| .04 | B | `--all` con fallos de red en los adjuntos 2 y 3 ⇒ se informa el 2 (PRD-v2.2 sección 10, punto 10). |
| .05 | N | `reason: network` lanzado en el segundo bloque (dentro del hilo del corte duro) ⇒ `E_ATTACHMENT_UNAVAILABLE` con su plantilla, no `E_CLIENT_TIMEOUT`. |

**UT-RMT-03 — Driver `attachments: "none"`**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | ⇒ `E_ATTACHMENT_UNAVAILABLE` (`unsupported`, exit 3) antes de abrir el store, con el hint nuevo de RF-67 literal. |

**UT-RMT-04 — Corte duro en plugins externos**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | El plugin se bloquea antes del primer bloque (espera un `threading.Event` que el test no activa hasta el final): con el tope inyectado a 1 s, `E_CLIENT_TIMEOUT` (exit 3) con el mensaje y el hint de RF-68; la espera del núcleo, medida con `time.monotonic()`, cumple `elapsed < tope + 1`. La evidencia registra el máximo observado en 20 corridas locales (A-03). |
| .02 | N | El plugin se bloquea entre dos bloques: ídem. |
| .03 | B | `--all` con los adjuntos 2 y 3 bloqueados: se informa el 2. |
| .04 | B | Staging limpio y sin archivos nuevos; el hilo del plugin se libera al terminar el test (evento) para no dejar el proceso colgado. |
| .05 | N | Con `timeout_seconds` inyectado mayor que `METADATA_TIMEOUT_SECONDS` (parcheado a 0,05 s), un plugin que tarda más de 0,05 s en crear el flujo no se corta antes del tope del adjunto y la extracción termina con éxito. |
| .06 | B | Plazo ya vencido antes de pedir el siguiente bloque ⇒ `E_CLIENT_TIMEOUT` sin nueva petición al plugin; flujo vacío ⇒ sin error; `close()` del iterador que lanza al vencer el plazo ⇒ sigue `E_CLIENT_TIMEOUT`. |

**UT-RMT-05 — Topes que no cambian y lo que no consume el tope**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con `timeout_seconds = 10` y `= 600`, el tope de metadatos de un plugin sigue siendo `METADATA_TIMEOUT_SECONDS` y el de cada llamada COM sigue siendo `outlook_com.CALL_TIMEOUT_SECONDS`. |
| .02 | P | Apple Mail y Outlook (doble): el tope se comprueba entre bloques y al terminar la llamada (un flujo lento entre bloques con tope inyectado da `E_CLIENT_TIMEOUT`); no se usa un hilo aparte con sus objetos. |
| .03 | B | Un acierto de caché no invoca la factoría del tope; A7 se ejecuta después y no la consume (con un detector lento simulado y el tope ya vencido, la respuesta es de éxito). |
| .04 | P | `cli` pasa al motor el valor de `[attachments].timeout_seconds` (espía sobre la factoría con `timeout_seconds = 180`). |
| .05 | N | Doble de Outlook con el watchdog COM (`outlook_com.CALL_TIMEOUT_SECONDS` parcheado) vencido antes del tope del adjunto ⇒ `E_CLIENT_TIMEOUT` con el mensaje y el hint de RF-33, no los de RF-68. |
| .06 | B | Drivers nativos (`stream_guard=None`): el motor se comporta como antes del cambio (mismos bloques leídos y mismo resultado que hoy con el doble). |

**UT-CFG-04 — `[attachments].timeout_seconds`** · `tests/test_config.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Sin clave → 60; 10 y 600 válidos. |
| .02 | N | 9, 601, `"60"`, `60.0` y `true` ⇒ `E_CONFIG_INVALID`, exit 2, también en `search` y `show`, antes del store. |
| .03 | B | Con un valor válido, `show` y `search` dan la misma salida que sin la clave. |

**UT-ACT-05 — `W_ATTACHMENT_ACTIVE_CONTENT` en `attachment`** · `tests/test_active_content.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Ejemplo A7 de PRD-v2.2 sección 8 (`factura.pdf` con `/JavaScript` índice 1, `docs.zip` con `factura.pdf.exe` índice 2): dos warnings con los textos literales, en el orden de `attachments[]`; los dos archivos se entregan; exit 0. |
| .02 | P | Servido desde la caché (segunda corrida): los mismos warnings. |
| .03 | N | El detalle no contiene nombres de archivo; un adjunto sin marcadores no da warning. |
| .04 | N | Un adjunto que bloquea el catálogo sigue dando `E_ATTACHMENT_BLOCKED` (exit 4). |
| .05 | P | Plugin `"remote"`: el mismo warning que con un driver local. |

**UT-ATC-07 — Timeout de extracción** (existente, se reescribe) · `tests/test_cli.py`: .01 y .02 pasan de "120 s" al tope configurado (inyectado con `_attachment_timeout`), mismas expectativas de staging y caché, y asiertan el hint de RF-68 en los drivers nativos.

**UT-OL-ATT-03.04** (existente, se reescribe el texto) · `tests/test_outlook.py`: el docstring y el texto del catálogo dicen "el tope configurado de extracción vence aunque cada llamada COM sea rápida" en lugar de "120 s"; la aserción no cambia.

**UT-ATC-10.03** (existente) se retira y lo sustituye UT-RMT-01 (sección 9 de `TEST-CATALOG.md`).

**DOC-06.05 — `config.example.toml` documenta `timeout_seconds`** · `tests/test_integration.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .05 | P | Dentro del bloque comentado `# [attachments]` existe la línea `# timeout_seconds = 60 …`; una copia en un temporal con el bloque descomentado (como `explicit` en DOC-06.01) da `timeout_seconds == 60` con el cargador real. El ejemplo sigue con todas las secciones comentadas (DOC-06.02). |

**DOC-09 — Documentación de F2 y A7** (nuevo) · `tests/test_remote_attachments.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Los dos README documentan `timeout_seconds` (10–600, 60 por defecto), los drivers `"remote"` en `attachment` y `W_ATTACHMENT_ACTIVE_CONTENT`. |
| .02 | P | La skill nombra `W_ATTACHMENT_ACTIVE_CONTENT` en "Security rules" y ya no dice que los adjuntos de drivers remotos no se pueden recuperar. |

Comandos:

```bash
python -B -m unittest discover -s tests -t . -k test_ut_rmt_
python -B -m unittest discover -s tests -t . -k test_ut_act_05_
python -B -m unittest discover -s tests -t . -k test_ut_cfg_04_
python -B -m unittest discover -s tests -t . -k test_ut_atc_07_
python -B -m unittest discover -s tests -t . -k test_ut_ol_att_03_
python -B -m unittest discover -s tests -t . -k test_doc_06_
python -B -m unittest discover -s tests -t . -k test_doc_09_
python -B -m coverage erase
python -B -m coverage run -m unittest discover -s tests -t .
python -B -m coverage report --include="src/mailquery/cli.py,src/mailquery/config.py,src/mailquery/attachments/engine.py,src/mailquery/plugins/api.py" --fail-under=85
```

`attachments/engine.py` tiene 87,1 % combinado y 78,5 % de ramas en `cf164ff`: no puede bajar del 85 % combinado (D-21); UT-RMT-02.05, UT-RMT-04.05–.06 y UT-RMT-05.05–.06 cubren las ramas nuevas del corte duro.

## 8. Tests existentes afectados (previsibles)

- UT-ATC-07 (120 s), UT-ATC-10.03 (rechazo de `"remote"`), tests que parchean `cli_mod.EXTRACTION_TIMEOUT_SECONDS` (dos usos en `tests/test_cli.py`).
- UT-ERR-04 si fija el tope de 120 s; UT-OL-ATT-03.04 (texto y docstring "120 s", sección 7).
- Si un caso nuevo verificaría exactamente el mismo comportamiento que un caso heredado, se actualiza el heredado y no se crea el nuevo.
- Tests del motor (`tests/test_attachments.py`) que construyan `AttachmentsEngine` si cambia su firma.
- Goldens de `attachment`: no deberían cambiar (las muestras no tienen marcadores de A7); cualquier cambio se justifica.

## 9. Documentación

- `README.md`, `README.es.md`: `timeout_seconds` en "Attachment recovery (`[attachments]`)"; drivers `"remote"` en `attachment` y en "Plugin drivers and capabilities"; el hint nuevo de `E_CLIENT_TIMEOUT`; `W_ATTACHMENT_ACTIVE_CONTENT` en la descripción de `attachment` y en "Body and warnings" (ya no "no hay warnings de adjuntos en `attachment`").
- `skills/mailquery/SKILL.md`: en "`show` and `attachment`", los adjuntos de drivers `"remote"` se recuperan igual; en "Security rules", qué hacer ante `W_ATTACHMENT_ACTIVE_CONTENT` (no abrir; decidir con el usuario).
- `docs/config.example.toml`: dentro del bloque comentado `# [attachments]`, la línea exacta `# timeout_seconds = 60          # 10..600, seconds per attachment in "attachment"`; el comentario final de `[attachments]` añade `timeout_seconds` (sección 2, punto 6).
- `docs/recipes/01-new-mail-digest.md` y `docs/recipes/02-search-invoices.md`: sección 2, punto 6.
- "Troubleshooting" de los README: filas `E_CLIENT_TIMEOUT` y `E_ATTACHMENT_UNAVAILABLE` (sección 2, punto 6).
- `docs/KNOWN-DEFECTS.md`: BUG-01 pasa a "Cerrado" con la fecha de cierre y "corregido en `3.0.0` (en desarrollo)"; el estado del documento se ajusta si no queda ningún defecto abierto.
- Bloques para `INTERFACES.md`: capacidad `"remote"` (se elimina "el núcleo no puede materializar adjuntos remotos"), `EXTRACTION_TIMEOUT_SECONDS = 60.0` como valor por defecto documentado (D-11), diseño del corte duro, `_attachment_timeout`, `AttachmentsConfig.timeout_seconds`, A7 en el flujo de `attachment`, `W_ATTACHMENT_ACTIVE_CONTENT` en la sección 4.
- Bloques para `TEST-CATALOG.md`: sección 2, prefijo `UT-RMT` → `tests/test_remote_attachments.py` y fila `DOC`: añadir `tests/test_remote_attachments.py` (DOC-09); sección 8, UT-RMT-01–05, UT-ACT-05, UT-CFG-04, UT-ATC-07 reescrito, UT-OL-ATT-03.04 reescrito, DOC-06.05, DOC-09; sección 9, UT-ATC-10.03 retirado (lo sustituye UT-RMT-01); sección 7, AC-17 de `PRD.md` (pasa al tope configurable) y filas de AC-H12, AC-H18, AC-D01–AC-D06.

## 10. Actualizaciones de `PRD-v2.2.md` (las escribe el orquestador)

- Registro de conciliación: "Recuperación de adjuntos de drivers `"remote"` (F2)", "Tiempo de extracción de adjuntos (F2)", "Respuesta de `attachment` (F1)" e "Inspección de adjuntos (F1)" → `Implementado y documentado`; "Catálogo de warnings (F1)" → `Implementado y documentado` (completo); "Configuración (F1, F2)" → `Implementado y documentado`; "Skill y README (F1)" → nota: regla de A7 añadida.
- Checklist: CL-06 → BUG-01 cerrado en `KNOWN-DEFECTS.md` (commit); CL-05 avanza (retirados "no hay warnings de adjuntos en `attachment`" y el rechazo de `"remote"` en README, skill e `INTERFACES.md`).
- Tabla de supersesión: sin cambios.

## 11. Datos crudos de evidencia a entregar

(a) suite completa con commit y conteo; (b) grupos `test_ut_rmt_`, `test_ut_act_05_`, `test_ut_cfg_04_`, `test_ut_atc_07_`, `test_ut_ol_att_03_`, `test_doc_06_`, `test_doc_09_` solos; (c) goldens tocados (esperado: ninguno); (d) tests nuevos, modificados y retirados con IDs y AC; (e) `git diff --check` y `git diff --stat integration/i3-attachments-rows...HEAD`; (f) diseño del corte duro, máximo de `elapsed` en 20 corridas de UT-RMT-04.01, riesgos (hilos de plugin que siguen vivos), decisiones y pendientes; (g) cobertura: salida de `coverage report` completa y de la orden con `--include` de la sección 7, con los valores de la línea base del lote de esos módulos. Más los bloques de la sección 9.

## 12. Definition of Done

- [ ] `"remote"` extrae con el mismo motor; solo `"none"` se rechaza, con el hint nuevo.
- [ ] `timeout_seconds` validado; corte duro en plugins externos; nativos entre bloques; COM y metadatos sin cambios; A7 y aciertos de caché fuera del tope.
- [ ] `W_ATTACHMENT_ACTIVE_CONTENT` por adjunto y tipo, también desde la caché.
- [ ] README (también "Troubleshooting"), skill, `config.example.toml`, recetas 01 y 02 y `KNOWN-DEFECTS.md` actualizados.
- [ ] Grupos de la sección 7 verdes solos; UT-ATC-10.03 retirado.
- [ ] Suite completa sin fallos nuevos frente a la línea base del lote.
- [ ] Cobertura (D-21): total ≥ 85 %; `python -B -m coverage report --include=<archivos de src/ de la sección 4> --fail-under=85` verde o, para un módulo por debajo del 85 % en la línea base del lote, sin bajar de ese valor y con las líneas nuevas cubiertas; salida en la evidencia (g).
- [ ] Informe final con los datos de la sección 11 y los bloques.

## 13. Registro de progreso

| Fecha | Fase | Nota |
|---|---|---|
| 2026-11-14 | F1 | `[attachments].timeout_seconds` en el esquema cerrado: entero de 10 a 600, default 60, `bool`/string/float fuera; `AttachmentsConfig.timeout_seconds` y `ATTACHMENTS_KEYS`. UT-CFG-04 (3 casos, incluido el fallo antes del store en `search` y `show`) verde solo. |
| 2026-11-14 | F2 | `_require_attachment_capabilities` rechaza solo `attachments: "none"`, con el hint nuevo; `"remote"` recorre el mismo motor (bloqueo, límites, caché, manifiesto, `--force`). UT-RMT-01 (5), UT-RMT-02 (5) y UT-RMT-03 (1) verdes solos; UT-ATC-10.03 retirado y sustituido por UT-RMT-01–03. |
| 2026-11-14 | F3 | Seam `cli._attachment_timeout`; `AttachmentStreamGuard` corta en un hilo daemon la creación del flujo y cada bloque de un plugin externo con el tiempo restante; los nativos siguen en línea con la comprobación entre bloques y cada llamada; `EXTRACTION_TIMEOUT_SECONDS` queda en `60.0` como default documentado. UT-RMT-04 (6), UT-RMT-05 (5) y UT-ATC-07 (2) verdes solos; UT-OL-ATT-03.04 solo cambia de texto. |
| 2026-11-14 | F4 | `W_ATTACHMENT_ACTIVE_CONTENT` por adjunto y tipo, en el orden de `attachments[]`, después de extraer o servir desde caché; fuera del tope; A7 no cambia el exit ni el archivo. UT-ACT-05 (5 casos) verde solo. |
| 2026-11-14 | F5 | README y README.es con `timeout_seconds` (10–600, 60), los drivers `"remote"` y A7, más "Troubleshooting"; skill con la regla de A7 y los adjuntos remotos; `config.example.toml` con la línea comentada; recetas 01 y 02; BUG-01 cerrado en `KNOWN-DEFECTS.md`. DOC-06.05 y DOC-09 (2 casos) verdes solos. |
| 2026-11-14 | F6 | Suite completa `Ran 1291`, `FAILED (failures=2, skipped=7)` (los 2 fallos ambientales de la línea base: SMOKE-NEW.07 de `mailboxes` y `show`); cobertura total 90,6 % y módulos tocados `cli.py` 91,5 %, `config.py` 96,8 %, `attachments/engine.py` 87,8 % y `plugins/api.py` 90,7 %; `git diff --check` limpio; sin goldens actualizados; bloques para `TEST-CATALOG.md`/`INTERFACES.md` y propuesta de registro en `.worktrees/reports/M09.md`. |

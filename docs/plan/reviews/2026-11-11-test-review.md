# Revisión adversarial de la suite de pruebas — PRD-v2.1 / plan 3.0.0

> **Estado (2026-11-11):** los hallazgos de este informe se corrigieron en la rev. 2 del plan maestro y de los 11 milestones; las decisiones de interpretación quedaron en `PLAN-MASTER.md` §13 y el registro en §11. Este documento se conserva como evidencia histórica de la revisión.

| Campo | Valor |
|---|---|
| Fecha | 2026-11-11 |
| Revisor | Revisor independiente de pruebas (no participó en la redacción del plan) |
| Objeto | Suite propuesta en `docs/plan/PLAN-MASTER.md` §3–§4, §7 y `docs/plan/milestones/M01..M11` |
| Norma | `docs/PRD-v2.1.md` (AC-01..AC-21, RF/RNF, §10.3/§10.4, §11.2/§11.3/§11.7/§11.9, §12) |
| Base real | `tests/` (14 128 líneas, 742 métodos `test_*`), 18 goldens (11 Apple + 7 Outlook), `docs/INTERFACES.md:813-877`, `.github/workflows/tests.yml` |
| Línea base verificada | `python -m unittest discover -s tests -t .`: **Ran 747 tests**, `FAILED (failures=2, skipped=6)`; los 2 fallos son `SMOKE-NEW.07` (`mailboxes` 0,225 s > 0,15 s y `show` 0,178 s > 0,15 s en este host). Coincide con el plan. |
| Alcance | Solo revisión. No se modificó el plan, el código ni los tests. Único write: este informe. |

## 0. Método

1. Lectura completa del PRD-v2.1 y de los 11 milestones; contraste de cada AC con los grupos/casos propuestos.
2. Inventario real de IDs, nombres, helpers, dobles, fixtures y goldens de `tests/`; se ejecutó la suite para verificar la línea base.
3. Para cada caso propuesto se comprobó: (a) que el AC/requisito lo exige; (b) que el caso prueba lo que dice; (c) que el archivo/milestone declarado puede contenerlo sin romper otro; (d) que es automatizable en la matriz de CI.
4. Se buscaron explícitamente colisiones de ID, goldens con más de un dueño, tests existentes que rompen el cambio y que el plan no enumera, y casos que solo reproducen una decisión de implementación.

## 1. Resumen ejecutivo

- **10 bloqueantes**: cuatro milestones rompen tests que están fuera de su write scope (`tests/test_outlook.py`, `tests/test_readonly.py`), M03 subenumera el radio de impacto del uid string, M08 rompe la forma de `show.attachments` en Outlook sin poder tocar su test, M09∥M10 y `SMOKE-ATT` no son paralelizables como están escritos, y el bump a 3.0.0 invalida los goldens de `doctor`.
- **La suite nueva es, en general, pertinente**, pero hay ACs con cobertura solo parcial: AC-01 (falta el positivo de plugin externo), AC-06 (migración por tipo/plataforma y mensajes heredados), AC-07 (symlink/directorio y contenido bloqueable), AC-08 (§11.3 sin pruebas de precedencia), AC-12 (E_PERMISSION/E_IO en CLI), AC-17 (plazo COM inyectado) y AC-21 (conteo de ayudas y TC-07).
- **Los goldens no tienen un único dueño** en 7 de los 18 existentes: `show_2714`, `show_83170`, `show_83180`, `show_smime_encrypted` (M03, M08 y M09) y `outlook/show*` (M03 y M10); además `doctor`/`outlook/doctor` cambian implícitamente en M11 por `pkg <versión>`.
- **La base real confirma 18 goldens** y la convención `UT-*`/`TC-*`/`OL-*`/`SMOKE-*`; no hay colisión literal de los grupos nuevos con los existentes, salvo la reutilización de `SMOKE-ATT.01..04` en M09 y M10 y la ambigüedad `INS-01` frente a `UT-INS-01`.
- **No se encontró** ningún caso que contradiga frontalmente el PRD salvo dos bordes de migración (`0`/negativos y strings solo de dígitos) y el umbral de 240 bytes aplicado a todas las plataformas.

## 2. Hallazgos

Leyenda: **B** = BLOQUEANTE, **M** = MAYOR, **m** = MENOR. Las líneas del plan son las del archivo indicado en la primera celda.

| ID | Sev. | AC / Requisito | Archivo:línea del plan | Hueco o defecto | Corrección propuesta |
|---|---|---|---|---|---|
| R-01 | **B** | AC-01, AC-05, C1 | `docs/plan/milestones/M01-plugin-contract-and-registry.md:10,30` | M01-T02 renombra `name` → `driver` en `MailBackend`, pero `tests/test_outlook.py:877` afirma `backend.name == "outlook"` y `tests/test_outlook.py` no está en el write scope de M01. M01 no puede quedar verde. | Incluir `tests/test_outlook.py` en el write scope de M01 (o mantener `name` como alias hasta M10) y enumerar `OL-02.06` en M01-T07. |
| R-02 | **B** | AC-02, AC-18 | `docs/plan/milestones/M02-config-scope-and-doctor.md:10,30,31` | M02 inserta `driver` tras `home`, pero `tests/test_outlook.py:546-550` (`_OUTLOOK_DOCTOR_CHECKS`) es la lista que afirma **todo** `OutlookDoctorTests`; el archivo no está en M02. Además M02-T05 solo menciona el `10/10`, no las listas ordenadas `tests/test_cli.py:1083,1236` ni `tests/test_integration.py:343-357`, que no son conteos. | Añadir `tests/test_outlook.py` y las listas de `test_cli`/`test_integration` al write scope de M02; actualizar la tupla y las listas; añadir un caso que afirme la posición de `driver`. |
| R-03 | **B** | AC-05, AC-06 | `docs/plan/milestones/M03-uid-and-state-schema-2.md:10,27,31` | M03 retira `check_state_uid` y cambia el `uid` emitido, pero `tests/test_outlook.py:3542,3626` construyen `StateStore(..., OutlookBackend.check_state_uid)` y `:2218,2288,2548,2633` comparan `message["uid"]` con el `EntryID` (47 usos de `["uid"]`); `test_outlook.py` no está en M03. | Añadir `tests/test_outlook.py` a M03; actualizar `message_of`, `show` y `uids` a uid prefijado; conservar un shim de `check_state_uid` o actualizar todas las llamadas en M03. |
| R-04 | **B** | AC-05, TC-03 | `docs/plan/milestones/M03-uid-and-state-schema-2.md:10,62-67` | `tests/test_readonly.py:200-205` (TC-03, gate bloqueante de CI) afirma `uid` entero 2714/83170 y `{83160,83170}`; el archivo no está en M03. El gate queda rojo. | Incluir `tests/test_readonly.py` en M03 y actualizar las expectativas a uid prefijado; volver a correr TC-03 como parte del cierre. |
| R-05 | **B** | AC-05, AC-06 | `docs/plan/milestones/M03-uid-and-state-schema-2.md:31,62-67` | M03 subenumera el radio real: `tests/test_integration.py:297` (`assertIsInstance(uid, int)`), `:453,530,548,624-646,667-677,700,717,735,746,760,769,774,790,898`; `tests/test_search.py:354` (helper `uids()`) y 21 comparaciones literales `:414-1071`; `tests/test_state.py:61-71` (roundtrip schema/uid int), `:175` (schema 2 ahora válido), `:226-246` (mensajes W0 exactos); `tests/test_cli.py:1587`. El plan solo nombra UT-CLI-07, UT-SR-07/08/11 y los seeds. | Enumerar en M03, por archivo y línea, todas las aserciones de uid entero y mensajes exactos; centralizar un helper `prefixed_uid`; añadir un checklist de cierre “ningún `assertIsInstance(uid, int)` ni literal entero”. |
| R-06 | **B** | AC-07 | `docs/plan/milestones/M08-attachment-command-and-show.md:10,31,35` | M08 cambia la forma de `show.attachments` en el núcleo (afecta a los dos backends), pero `tests/test_outlook.py:2291,2351,2369,2406,2420` afirman `[{"name": ...}]` y el archivo no está en M08; `tests/test_integration.py:735,774,898` y `tests/test_search.py:1291,1725,1732` tampoco se enumeran. | Incluir `tests/test_outlook.py` en M08 (o posponer la forma nueva a M10 con compatibilidad temporal) y enumerar todas las aserciones inline; añadir un helper `assert_attachment_shape`. |
| R-07 | **B** | AC-12, AC-19, AC-21 | `docs/plan/milestones/M09-apple-mail-attachments.md:10`, `docs/plan/milestones/M10-outlook-attachments.md:10`, `docs/plan/PLAN-MASTER.md:145,315` | M09 y M10 corren en la misma ola y ambos escriben `tests/test_integration.py`, `tests/test_readonly.py`, `tests/test_smoke.py` y `docs/INTERFACES.md`; TC-03, TC-08, TC-09 y SMOKE-ATT se pisan. La afirmación “sin solape” es falsa para tests. | Serializar M09/M10 o separar en archivos por plataforma (`test_integration_am.py`/`_ol.py`, clases de gate distintas); asignar TC-03 a M09 y OL-30 a M10 exclusivamente. |
| R-08 | **B** | AC-20, AC-17 | `docs/plan/milestones/M09-apple-mail-attachments.md:81-86`, `docs/plan/milestones/M10-outlook-attachments.md:81-85` | `SMOKE-ATT.01..04` se define dos veces (macOS y Windows) con contenido distinto y el mismo ID; `-k smoke_att_01` ejecuta ambos y no hay clase condicional por plataforma especificada. | Renombrar `SMOKE-ATT-AM.01..04` y `SMOKE-ATT-OL.01..03` (o `.01-.04` / `.05-.07`) y declarar el skip por plataforma en la clase. |
| R-09 | **B** | AC-18 | `docs/plan/PLAN-MASTER.md:236`, `docs/plan/milestones/M02-config-scope-and-doctor.md:30`, `docs/plan/milestones/M11-docs-release-and-reconciliation.md:27` | El detalle del chequeo `driver` incluye `pkg <versión>`; el golden se genera en M02 con 2.0.1 y M11 sube a 3.0.0. `doctor.json`/`outlook/doctor.json` quedan obsoletos y ningún milestone de M11 los actualiza (la tabla los asigna solo a M02). | Añadir ambos goldens a M11 o normalizar `pkg <PKG_VERSION>` en `_normalize`; añadir un caso que use `mailquery.__version__`, no un literal. |
| R-10 | **B** | AC-06 | `docs/plan/milestones/M03-uid-and-state-schema-2.md:40,62-67` | `tests/test_state.py:405` (UT-ST-03.04) afirma que un entero es `E_STATE_CORRUPT` en Windows, pero la migración “por tipo, sin depender del SO” dice entero → `apple_mail:<n>`. `:226-246` fija mensajes W0 (“integer >= 1”, “integers >= 1”) que el delta sustituye. M03 no los retira. | Sustituir UT-ST-03.04 por un caso de migración correcta (o por `E_STATE_CORRUPT` solo si `apple_mail` no está instalado, con justificación explícita); actualizar los mensajes exactos; decidir en el PRD la regla de `0`/negativos. |
| R-11 | **M** | AC-06 | `docs/plan/milestones/M03-uid-and-state-schema-2.md:38-43` | UT-ST-06 .01/.02 afirman que enteros → `apple_mail` y hex → `outlook` “independiente del SO”, pero después se valida que el driver exista: en macOS `outlook` puede no estar disponible y en Windows `apple_mail` puede no estarlo (DP-02), con lo que el positivo se convierte en `E_STATE_CORRUPT`. El test no es verde en los 3 SO. | Probar la función pura de migración, o inyectar un registro con ambos drivers “instalados”; declarar la matriz de plataformas y el skip. |
| R-12 | **M** | AC-01 | `docs/plan/milestones/M01-plugin-contract-and-registry.md:43-50,87-89` | No hay positivo de “un plugin externo que cumpla el contrato se registra por la misma vía”: UT-PL-01 .01 solo cubre los internos; .04/.07 son negativos; `tests/fakes/plugin.py` solo se usa para objetos de API. | Añadir UT-PL-01 .09: plugin de prueba con `driver` válido, API 1 y capacidades, registrado y listado; PKG-01 .02 debe probar metadata instalada o inyectada. |
| R-13 | **M** | AC-08, AC-15, AC-17 | `docs/plan/milestones/M08-attachment-command-and-show.md:10,50-58,82-93` | UT-ATC-02/03/06/07 necesitan un backend inyectable en CLI con `attachments: none`, señal S/MIME, motivos y timeout de 120 s; el `_FakeBackend` de `tests/test_cli.py:51-70` no tiene capacidades ni operaciones de adjuntos, y M08 no declara ningún doble nuevo. | Añadir `tests/fakes/attachment_backend.py` (o extender el plugin fake) al write scope de M08 y decir en cada caso qué doble usa. |
| R-14 | **M** | AC-08, §11.3 | `docs/plan/milestones/M08-attachment-command-and-show.md:29,52-66` | Los casos aíslan filas, pero no prueban la **precedencia** entre filas adyacentes: 2 vs 3, 4 vs 5, 8 vs 9, 9 vs 10, 10 vs 11, 11 vs 12. Faltan, p. ej., `--index 9` sobre mensaje con nombre bloqueado (debe ser `E_USAGE`, no `E_ATTACHMENT_BLOCKED`), `enabled=false` + `attachments:none` (debe ser `E_ATTACHMENTS_DISABLED`), S/MIME + `--index 9` (debe ser `E_ATTACHMENT_UNREADABLE`). | Añadir un caso table-driven por cada frontera de §11.3, con código, exit y “no abre store”; es el AC-08 central. |
| R-15 | **M** | AC-07, RF-43 | `docs/plan/milestones/M08-attachment-command-and-show.md:41-48`, `docs/plan/milestones/M07-attachment-cache-and-staging.md:62` | Falta `cached_path: null` para symlink/directorio (RF-43: “solo apunta a archivos regulares”) y falta el positivo de que un mensaje bloqueable **por contenido** sigue mostrando `cached_path` (`show` no inspecciona contenido). UT-ATC-01 .03 solo cubre nombre inseguro. | Añadir UT-ATC-01 .09 (symlink/directorio ⇒ null) y .10 (adjunto con `MZ` cuya caché existe ⇒ `cached_path` no nulo y `attachment` bloquea). |
| R-16 | **M** | AC-15, §11.3 | `docs/plan/milestones/M07-attachment-cache-and-staging.md:80-83`, `docs/plan/milestones/M08-attachment-command-and-show.md:29` | §11.3 exige que, si varios adjuntos fallan, se informe el **primer fallo en orden de índice**. UT-ATT-11 .04 solo afirma “sin parciales”; no hay caso con fallos en índices 2 y 3 que compruebe cuál se reporta. | Añadir un caso `--all` con dos fallos y afirmar el índice/reason del primer fallo; otro con un fallo de nombre y otro de contenido. |
| R-17 | **M** | AC-12, §11.3 fila 15 | `docs/plan/milestones/M07-attachment-cache-and-staging.md:33,41-46`, `docs/plan/milestones/M01-plugin-contract-and-registry.md:34` | No hay caso de `PermissionError` al crear directorio/archivo de caché o staging (debe ser `E_PERMISSION`) ni de `ENOSPC` en staging distinto de `os.replace`. `E_IO` se prueba en el motor, pero no su exit 3 en CLI. | Añadir UT-ATT-07 .06/.07 (EACCES en mkdir/open, ENOSPC en write y en replace) y un caso CLI que afirme `E_IO` + exit 3; extender UT-CLI-09. |
| R-18 | **M** | AC-05, §11.2 | `docs/plan/milestones/M08-attachment-command-and-show.md:52-58` | No hay caso positivo de `mailquery attachment <uid legado>` sin prefijo (entero Apple y `EntryID` Outlook); UT-UID-02 .03 solo cubre `show`. El PRD §11.2 lo exige explícitamente. | Añadir UT-ATC-02 .08/.09: `attachment 83143 --index 1` y `attachment <EntryID> --index 1`, con salida `uid` prefijado. |
| R-19 | **M** | AC-12, AC-13 | `docs/plan/milestones/M09-apple-mail-attachments.md:31-33,79` | TC-08 .05 dice “golden de `show` correspondiente”, pero no existe ni se nombra un golden de `show` con caché previa. `attachment_cached.json` necesita una caché pre-sembrada con tamaño/hash deterministas y no se describe; `attachment_too_large` necesita un adjunto de ~1,5 MiB que no está en la lista de M09-T05. | Nombrar el golden (`show_2714_with_cache.json` o similar) y documentar la siembra de caché; añadir el adjunto de 1,5 MiB a M09-T05; especificar el orden extraer→segunda corrida. |
| R-20 | **M** | AC-15 | `docs/plan/milestones/M09-apple-mail-attachments.md:58-61` | UT-AM-03 .03 está redactado como pregunta y se contradice (“sin bloquear el resto...? — ... `--all` falla”); .02 mezcla “`.emlx` ausente” con “adjunto no materializado”. | Separar: (a) `--index` del seguro con otro `unsupported` ⇒ éxito; (b) `--all` ⇒ fallo sin parciales; (c) `.emlx` ausente ⇒ `not_local`; (d) `.partial.emlx` externalizado ⇒ `unsupported`. |
| R-21 | **M** | AC-01, AC-06, AC-08, RC-11 | `docs/plan/milestones/M01-plugin-contract-and-registry.md:34` | M01 añade 9 códigos nuevos al catálogo, pero `tests/test_cli.py:758-784` (UT-CLI-09.01) enumera 23 y afirma `len(cases) == 23`; ningún milestone lo actualiza, aunque PRD §0.7.2 RC-11 dice “UT-CLI-09 actualizado”. Los nuevos códigos no se prueban a nivel de exit. | Actualizar UT-CLI-09 a los 32 códigos y añadir un caso que compare `errors._EXIT_ERRORS` con la tabla §11.7 completa. |
| R-22 | **M** | AC-01, PKG-01 | `docs/plan/milestones/M01-plugin-contract-and-registry.md:88`, `docs/plan/PLAN-MASTER.md:254` | PKG-01 .02 exige “con el paquete instalado, `importlib.metadata` expone ambos entry points”; CI no instala el paquete (`tests.yml` solo instala pywin32) y el plan no declara skip. | Probar la metadata con entry points inyectados y dejar el caso instalado a `SMOKE-INSTALL`/`pipx`, con skip documentado si no está instalado. |
| R-23 | **M** | AC-20, §12.2 | `docs/plan/milestones/M09-apple-mail-attachments.md:85`, `docs/plan/PLAN-MASTER.md:262` | SMOKE-ATT .03 impone `< 50 ms` en un host real; es flaky y contradice que los presupuestos se midan en M11. | Quitar el umbral duro de M09; mover la medición a M11 (reporte) o usar reloj/plazo inyectado y un umbral holgado para el comportamiento. |
| R-24 | **M** | RNF-12, §12.2 | `docs/plan/milestones/M06-attachment-blocking-and-sanitization.md:10`, `docs/plan/milestones/M07-attachment-cache-and-staging.md:10`, `docs/plan/PLAN-MASTER.md:254` | No hay test de “solo stdlib” para `attachments/**`/`plugins/**`/`registry` (el escaneo actual de `test_backends.py` solo mira `search.py`, `config.py` y `outlook_com.py`), ni presupuesto de extracción Apple < 200 ms / Outlook < 600 ms (§12.2). | Extender el escaneo de imports a los paquetes nuevos; añadir en M11 casos de presupuesto de extracción o registrar la deuda explícitamente. |
| R-25 | **M** | AC-16, §11.7 | `docs/plan/milestones/M05-plugin-errors-and-timeouts.md:47-51` | UT-ERR-01 verifica el mapeo `reason`→código, pero UT-ERR-02 .03 solo prueba “la plantilla del motivo” en singular. No se afirman las 8 plantillas de §11.7 (`not available in the local store`, `could not be retrieved from its origin`, `is S/MIME protected...`, etc.) ni el sufijo `detail`. | Caso table-driven de las 8 plantillas + `: detail`; incluir `network`, `not_downloaded`, `unsupported`, `smime`, `corrupt`, `unreadable`, `permission`, `busy`, `timeout`. |
| R-26 | **M** | AC-21, TC-04 | `docs/plan/milestones/M11-docs-release-and-reconciliation.md:33,89-93` | TC-04 sustituye un único `<uid>` por `messages[0].uid` de `new --peek`/`search --since 1mo`. Si la receta 02 añade `attachment`, ese mensaje puede no tener adjuntos y el comando sale 2; el test falla por una razón ajena a la receta. | Elegir el uid de una búsqueda con `--has-attachments` o de un fixture con adjunto conocido; hacer que la receta declare el uid de un mensaje con adjunto. |
| R-27 | **M** | AC-06, AC-18 | `docs/plan/milestones/M02-config-scope-and-doctor.md:30-31`, `docs/plan/milestones/M03-uid-and-state-schema-2.md:30` | M02 solo menciona el `10/10`; no enumera las listas ordenadas `tests/test_cli.py:1083,1236` ni `tests/test_integration.py:343-357`. M03 no menciona `tests/test_cli.py:1344-1360` (UT-CLI-11.02: `last_uid=42`), que pasa a estar prefijado. | Enumerar y actualizar esas listas/detalles; añadir una aserción de posición de `driver` y de `last_uid` prefijado en `doctor`. |
| R-28 | **M** | AC-21 | `docs/plan/milestones/M11-docs-release-and-reconciliation.md:9`, `tests/test_integration.py:1356-1365` | TC-07.04 sigue recorriendo la ayuda raíz y **5** comandos; no incluye `attachment` y no está en los grupos de M11. | Extender TC-07.04 a 6 comandos + raíz, incluir `attachment --help` y afirmar la ausencia de “cinco comandos”; asignarlo a M11. |
| R-29 | **M** | AC-07, RF-43 | `docs/plan/milestones/M08-attachment-command-and-show.md:35,46`, `docs/plan/milestones/M09-apple-mail-attachments.md:31` | `show_smime_encrypted.json` hoy tiene `attachments: [{"name": "smime.p7m"}]`; en 3.0.0 debe ser `[]` (cambio de **valor**, no solo de forma). Lo mismo en `tests/test_search.py:1732`. M08 lo cambia; M09-T04 dice “solo forma/`cached_path`” y vuelve a asignarse el golden. | M08 es el dueño del valor y la forma; actualizar también la aserción inline de `test_search.py:1732`; quitar `show_smime_encrypted` de M09-T04 o especificar el diff exacto (`[]`). |
| R-30 | **M** | PKG-02, INS-01 | `docs/plan/milestones/M11-docs-release-and-reconciliation.md:80` | `GOOD_VERSION = __version__` (literal `3.0.0`) hace que el `-v` falso de `tests/test_install_scripts.py` sea solo “3.0.0”, sin `backend outlook`; el chequeo final de `install.ps1` y UT-INS-01.03 fallan. `GOOD_VERSION` es una **línea completa** `mailquery <v> (backend outlook; Python ...; Windows ...)`. | Construir `f"mailquery {mailquery.__version__} (backend outlook; Python 3.14.0; Windows 10.0.26200 AMD64)"`; hacer dinámico solo el fragmento de versión. |
| R-31 | m | AC-06, DP-03 | `docs/plan/milestones/M03-uid-and-state-schema-2.md:27`, `docs/plan/milestones/M07-attachment-cache-and-staging.md:34` | No hay caso de ciclo de vida de plugin (PRD §10.2.10/DP-03): actualizar dentro de API 1 no cambia config/state/caché; desinstalar deja `[scope]` en `E_DRIVER_UNKNOWN`, cursor en `E_STATE_CORRUPT`, poda el anillo y **conserva la caché**. Los tres primeros se cubren por separado; “caché conservada” no. | Añadir un caso con plugin fake: desinstalar ⇒ códigos esperados + archivo de caché intacto; actualizar ⇒ `config.toml`/`state.json`/caché byte a byte iguales. |
| R-32 | m | AC-18, §11.9 | `docs/plan/milestones/M01-plugin-contract-and-registry.md:63-67` | UT-PL-03 .01/.02 solo tienen un driver por plataforma; no se prueba el orden alfabético `drivers: ...` con varios (p. ej. `graph` + `apple_mail`). | Añadir un caso con plugin fake y nativo en plataforma parcheada; afirmar orden alfabético y DP-02. |
| R-33 | m | AC-15, AC-14, AC-12 | `docs/plan/milestones/M01-plugin-contract-and-registry.md:34`, `docs/plan/milestones/M08-attachment-command-and-show.md:52-58`, `docs/plan/milestones/M07-attachment-cache-and-staging.md:41-46` | No se afirman los `hint` de `E_DRIVER_UNKNOWN` (lista de instalados + `pipx inject`), `E_ATTACHMENTS_DISABLED`, `E_IO`, `E_PLUGIN_FAILED`; §11.7 los fija. | Añadir aserciones de substrings de hint por código en UT-ERR/UT-ATC. |
| R-34 | m | AC-12 | `docs/plan/milestones/M09-apple-mail-attachments.md:33`, `docs/plan/milestones/M10-outlook-attachments.md:33` | El plan dice “rutas normalizadas a `<HOME>`”; el normalizador real sustituye `self.fx.root` por `<ROOT>` y solo el detalle `home` por `<HOME>`. Las rutas de `attachment` quedarán `<ROOT>/home/.mailquery/...`. | Corregir el texto a `<ROOT>` (o extender `_normalize` si se quiere `<HOME>`); evita escribir un golden con el token equivocado. |
| R-35 | m | AC-11, §10.3.3 | `docs/plan/milestones/M06-attachment-blocking-and-sanitization.md:72` | Fija el fallback de 32 hex a **240 bytes** de ruta en todas las plataformas; el PRD habla del “límite de la plataforma” y 240 es la cifra de riesgo de Windows (§15). En macOS se impone una regla más estricta que la normativa. | Parametrizar por plataforma o probar en el máximo de la plataforma; documentar 240 como presupuesto de implementación, no como límite universal. |
| R-36 | m | AC-02 | `docs/plan/milestones/M09-apple-mail-attachments.md:71` | UT-AM-04 .04 cita “las capacidades de §4”; las capacidades están en RF-38/§6.1. Además `.03` (permisos POSIX) debe declarar la condición de plataforma explícita. | Corregir la cita a §6.1/RF-38 y marcar `.03` como POSIX-only con skip documentado. |
| R-37 | m | AC-16, AC-19 | `docs/plan/milestones/M05-plugin-errors-and-timeouts.md:51` | UT-ERR-02 .05 se llama “un `hint`/`detail`/`log_message` con uid... no se registra”, pero el núcleo solo sanea controles/longitud; el PRD asigna al plugin no incluir PII. El propio caso admite que solo verifica `hint`/`detail`. | Afirmar que `hint`/`detail` nunca se registran y que `log_message` se sanea (controles ≤ 200 bytes); probar la obligación de PII del plugin en el doble, no en el núcleo. |
| R-38 | m | Convención §7.1 | `docs/plan/milestones/M01-plugin-contract-and-registry.md:63-67`, `docs/plan/milestones/M08-attachment-command-and-show.md:78-80,103-107`, `docs/plan/milestones/M11-docs-release-and-reconciliation.md:77-81` | Grupos nuevos que duplican tests existentes sin renombrarlos: UT-PL-03 vs UT-CLI-01..03; UT-ATC-09 vs UT-CLI-06; PKG-01/02 vs TC-06; UT-ATC-05 vs UT-ATC-02/UT-DRV-04. §7.1 dice “se renombra; no se duplica”. | Declarar el test existente que se reemplaza o renombrar el grupo; evitar dos IDs para el mismo comportamiento. |
| R-39 | m | Mapeo §7.2 | `docs/plan/PLAN-MASTER.md:213-226` | `UT-OL-ATT` se mapea a `tests/fakes/outlook.py` (un doble, no un test); UT-DRV-05 (doctor) a `test_config.py`; todo UT-AM a `test_backends.py` aunque UT-AM-03/04 son e2e; el grupo `RO` no existe en la base. | Corregir a `tests/test_outlook.py`, `tests/test_cli.py`/`test_integration.py`, `tests/test_integration.py`; eliminar `RO` o definirlo. |
| R-40 | m | AC-21 | `docs/plan/milestones/M08-attachment-command-and-show.md:105`, `docs/plan/milestones/M11-docs-release-and-reconciliation.md:68` | “Cada ejemplo de las **seis ayudas**” cuenta mal: son la raíz + 6 subcomandos = **7** invocaciones (la base UT-CLI-06.06 recorre raíz + 5 = 6). | Decir “la ayuda raíz y las seis de subcomando” y actualizar el bucle a 7. |
| R-41 | m | AC-10, AC-12 | `docs/plan/milestones/M06-attachment-blocking-and-sanitization.md:63,70,80`, `docs/plan/milestones/M07-attachment-cache-and-staging.md:54` | Casos débiles o vacíos: UT-ATT-05 .04 no afirma nada (el mensaje vacío “no llega a esta capa”); UT-ATT-04 .04 prueba independencia del `cwd` (irrelevante); UT-ATT-03 .06 y UT-ATT-07 .05 simulan un crash difíciles de observar y sin señal clara. | Sustituir por aserciones observables: no escritura verificada en el gate, determinismo entre dos llamadas, y archivos completos tras inyección de fallo en `os.replace`. |
| R-42 | m | AC-17 | `docs/plan/milestones/M08-attachment-command-and-show.md:93` | UT-ATC-07 .03 (“En Outlook se conserva el límite de 30 s... se verifica en M10”) es un placeholder no ejecutable en M08. | Quitarlo de M08; la cobertura está en UT-OL-ATT-03 .03/.04. |
| R-43 | m | AC-17, M05 | `docs/plan/milestones/M05-plugin-errors-and-timeouts.md:65` | UT-ERR-04 .04 prueba el watchdog COM de Outlook, que M05 no toca; es una regresión de M10 y no del timeout de plugin. | Moverlo a M10/OL-30 o eliminarlo de M05. |
| R-44 | m | Convención §7.1 | `docs/plan/milestones/M11-docs-release-and-reconciliation.md:83` | `INS-01` convive con `UT-INS-01` de la base; `-k ins_01` selecciona ambos grupos y rompe el criterio “ejecutado solo”. | Renombrar a `INS-SMOKE-01` o mantener el prefijo `UT-INS`. |
| R-45 | m | AC-05 | `docs/plan/milestones/M01-plugin-contract-and-registry.md:79` | UT-UID-01 .03 mezcla dos expectativas (“`E_USAGE` si el formato es inválido o `E_DRIVER_UNKNOWN` si el driver es válido pero no está instalado”) sin separar los inputs; no se puede saber qué assertar para mayúsculas/guion. | Dividir en: formato inválido ⇒ `E_USAGE`; driver válido no instalado ⇒ `E_DRIVER_UNKNOWN`; tabla de inputs por caso. |
| R-46 | m | AC-06 | `docs/plan/milestones/M03-uid-and-state-schema-2.md:50` | UT-ST-07 .04 está marcado **P** pero es negativo (1025 caracteres ⇒ `E_STATE_CORRUPT`). | Marcarlo **N**. |
| R-47 | m | AC-15, AC-17 | `docs/plan/milestones/M10-outlook-attachments.md:56,61` | UT-OL-ATT-02 .06 afirma que `object_model_guard` “no evalúa” la materialización (decisión interna sin señal); UT-OL-ATT-03 .02 exige “un solo reintento como en 2.0.1”, no fijado en el delta. | Afirmar solo timeout/permiso y lista blanca; quitar el conteo de reintentos salvo que el PRD.md §17 lo mantenga. |

## 3. Matriz AC → casos propuestos → cobertura

| AC | Casos propuestos en el plan | Cobertura |
|---|---|---|
| AC-01 | UT-PL-01 .01-.08, PKG-01 .01-.03 | **Parcial**: falta positivo de plugin externo registrado; UT-PL-01 .01 solo internos. |
| AC-02 | UT-PL-02 .01-.06, UT-DRV-05 .02 | **Completa**. |
| AC-03 | UT-DRV-01 .01-.06, UT-DRV-02 .01-.04, UT-DRV-03 .01-.03 | **Completa**. |
| AC-04 | UT-MD-01..04, UT-MD-05, UT-MD-06 | **Completa**. |
| AC-05 | UT-UID-01 .01-.07, UT-UID-02 .01-.06, UT-SR-11, goldens | **Parcial**: falta `attachment` con uid legado; el radio de tests existentes está subestimado (R-05). |
| AC-06 | UT-ST-06 .01-.06, UT-ST-07 .01-.05 | **Parcial**: UT-ST-03.04 y mensajes W0 contradicen la migración (R-10); plataforma/registro sin fijar (R-11); falta mezcla de tipos en el anillo. |
| AC-07 | UT-ATC-01 .01-.08, goldens `show_*` | **Parcial**: sin symlink/directorio y sin contenido bloqueable con `cached_path` (R-15). |
| AC-08 | UT-ATC-02 .01-.07, UT-ATC-03 .01-.05 | **Parcial**: sin precedencia entre filas de §11.3 (R-14); falta uid legado (R-18). |
| AC-09 | UT-ATT-03 .01-.06, UT-AM-01 .01-.05, golden `attachment_blocked` | **Completa**. |
| AC-10 | UT-ATT-01 .01-.08, UT-ATT-02 .01-.05, UT-AM-01 .02-.03, UT-OL-ATT-02 .03 | **Completa**. |
| AC-11 | UT-ATT-04 .01-.07, UT-AM-02 .01-.04 | **Completa** (con el matiz del umbral de 240 bytes, R-35). |
| AC-12 | UT-ATT-07 .01-.05, UT-ATT-08 .01-.06, UT-ATC-04 .01-.05, TC-08 | **Parcial**: E_PERMISSION/E_IO en CLI no probados (R-17); `attachment_cached` sin siembra descrita (R-19). |
| AC-13 | UT-ATT-06 .01-.06, golden `attachment_too_large` | **Completa**. |
| AC-14 | UT-DRV-04 .01-.05, UT-ATC-05 .01-.03 | **Completa** (duplicación, R-38). |
| AC-15 | UT-ATT-05 .01-.05, UT-ATT-11 .01-.04, UT-ATC-06 .01-.04, UT-OL-ATT-03 | **Completa** (salvo plantillas, R-25). |
| AC-16 | UT-ERR-01 .01-.05, UT-ERR-02 .01-.05, UT-ERR-03 .01-.04 | **Completa** (R-37/R-25 son de precisión). |
| AC-17 | UT-ERR-04 .01-.04, UT-ATC-07 .01-.03, UT-OL-ATT-03 .03-.04 | **Parcial**: plazo COM de 30 s sin inyección declarada; UT-ATC-07 .03 es placeholder (R-42). |
| AC-18 | UT-PL-03 .01-.05, UT-DRV-05 .01-.06, `doctor.json` | **Completa** salvo el desfase de versión en M11 (R-09) y el orden multi-driver (R-32). |
| AC-19 | UT-MD-06 .01-.03, UT-ERR-02 .04-.05, UT-ATC-08 .01-.03, UT-OL-ATT-04 | **Completa**. |
| AC-20 | UT-ATT-10 .01-.04, SMOKE-ATT | **Completa** (R-23 por el umbral temporal). |
| AC-21 | UT-ATC-09 .01-.05, DOC-01..06, TC-07 | **Parcial**: “seis ayudas” por 7 (R-40); TC-07 no se extiende (R-28). |

## 4. Goldens y TCs

### 4.1 Los 18 goldens existentes (verificados)

| Golden | Dueño según el plan | Veredicto |
|---|---|---|
| `doctor.json` | M02 (`PLAN-MASTER.md:236`) | **Correcto en M02**, pero cambia otra vez en M11 por `pkg <versión>` (R-09). |
| `mailboxes.json` | Sin cambio | **Correcto**. |
| `new_first_run.json` | M03 (`:237`) | **Correcto**. |
| `new_seeded.json` | M03 | **Correcto**. |
| `search_default.json` | M03 | **Correcto**. |
| `search_all_mail.json` | M03 | **Correcto**. |
| `show_2714.json` | M03 y M08 (`:237,239`) | **Tres dueños**: M03 (uid), M08 (forma), M09 (`M09:31`). R-29/R-07. |
| `show_83170.json` | M03 y M08 | Igual: tres dueños. |
| `show_83180.json` | M03 y M08 | Igual: tres dueños. |
| `show_smime_encrypted.json` | M03 y M08 | Además cambia de **valor** a `attachments: []`; M09 se lo reasigna (R-29). |
| `show_not_in_scope_error.json` | M03 | **Correcto**; el `message` contiene el uid y debe pasar a prefijado. |
| `outlook/doctor.json` | M02 (`:236`) | **Correcto en M02**, obsoleto en M11 (R-09). |
| `outlook/mailboxes.json` | Sin cambio | **Correcto**. |
| `outlook/new_first_run.json` | M03 (`:238`) | **Correcto**. |
| `outlook/search.json` | M03 | **Correcto**. |
| `outlook/show.json` | M03 y M10 (`:238,240`) | **Dos dueños**; además las aserciones inline de `test_outlook.py` rompen en M03/M08 (R-03/R-06). |
| `outlook/show_header_only.json` | M03 y M10 | Igual. |
| `outlook/show_smime.json` | M03 y M10 | Igual. |

### 4.2 Goldens nuevos (9)

| Golden | Dueño | Veredicto |
|---|---|---|
| `search_multidriver.json` | M04 (`:241`) | **Correcto**; el fixture de plugin debe ser determinista. |
| `new_multidriver.json` | M04 | **Correcto**. |
| `attachment_saved.json` | M09 (`:242`) | **Parcial**: no se identifica el mensaje/fixture exacto; el flujo depende de `attachments=True`. |
| `attachment_cached.json` | M09 | **Defectuoso**: no se describe la caché pre-sembrada ni la secuencia de dos corridas (R-19). |
| `attachment_blocked.json` | M09 | **Parcial**: no se dice si es bloqueo por nombre (ejemplo C) o por contenido (ejemplo D); falta el otro. |
| `attachment_too_large.json` | M09 | **Parcial**: el adjunto de ~1,5 MiB no aparece en M09-T05 (R-19). |
| `outlook/attachment_saved.json` | M10 (`:243`) | **Correcto** con el doble. |
| `outlook/attachment_cached.json` | M10 | **Defectuoso**: misma falta de siembra que M09 (R-19). |
| `outlook/attachment_unavailable.json` | M10 | **Correcto** (`not_downloaded`). |

### 4.3 TCs, gates, SMOKE y documentación

| TC / gate | Veredicto |
|---|---|
| TC-01 (goldens Apple) | **Parcial**: M02 solo actualiza “el conteo” y no las listas (R-02/R-27); M03 no enumera `assert_message_shape` ni `DEFAULT_UID_ORDER` (R-05); M08 no enumera las aserciones inline de `attachments` (R-06). |
| TC-02 (goldens Outlook) | **Correcto** en M03/M10, pero las aserciones inline de `test_outlook.py` se rompen antes (R-03/R-06). |
| TC-03 (solo lectura Apple) | **Bloqueado**: M03 lo rompe y no puede tocarlo (R-04); M09 lo extiende y M10 también lo escribe en paralelo (R-07). |
| TC-04 (recetas) | **Mayor**: el `<uid>` de `messages[0]` puede no tener adjuntos (R-26). |
| TC-05 (paridad JSON) | **Correcto**; `.03` duplica TC-05.05 de la base (R-38). |
| TC-06 (packaging) | **No se menciona**; PKG-01/02 lo duplican (R-38). |
| TC-07 (docs) | **No se extiende**: sigue con 5 comandos y sin `attachment` (R-28). |
| TC-08 (goldens adjuntos Apple) | **Parcial**: `.05` sin golden; `.02` sin siembra (R-19). |
| TC-09 (goldens adjuntos Outlook) | **Correcto**, salvo la siembra de `attachment_cached` (R-19). |
| OL-30 (gate Outlook) | **Correcto** en M10; hay que actualizar el set de comandos a 6 y la lista blanca COM. |
| SMOKE-INSTALL.02 | **Correcto** en M11 (regex literal `2\.0\.1` en `tests/test_smoke.py:227`). |
| SMOKE-ATT | **Bloqueante**: IDs duplicados y archivo compartido entre M09/M10 (R-08). |
| DOC-01..06 | **Parcial**: “seis ayudas” y TC-07 (R-40/R-28); el resto es coherente. |
| PKG-01/02, INS-01 | **Duplican** TC-06/UT-INS-01; `GOOD_VERSION` mal definido en PKG-02 (R-30/R-38/R-44). |

## 5. Tests existentes que el plan no enumera o ubica mal

| Test existente | Archivo:línea | Lo rompe | Milestone que debería actualizarlo | Estado en el plan |
|---|---|---|---|---|
| `OL-02.06` (`backend.name`) | `tests/test_outlook.py:877` | M01 (`name`→`driver`) | M01 | **No enumerado; fuera de write scope** (R-01). |
| `_OUTLOOK_DOCTOR_CHECKS` y todos los `OutlookDoctorTests` | `tests/test_outlook.py:546-550` | M02 (`driver` tras `home`) | M02 | **No enumerado; fuera de write scope** (R-02). |
| `OL-25.01`, `new_core_with_string_uids...` (`check_state_uid`) | `tests/test_outlook.py:3542,3626` | M03 (retira `check_state_uid`) | M03 | **No enumerado; fuera de write scope** (R-03). |
| `self.message_of`, `show`, `uids` de Outlook | `tests/test_outlook.py:2218,2288,2548,2633` | M03 (uid prefijado) | M03 | **No enumerado** (R-03). |
| `TC-03.01` uids enteros | `tests/test_readonly.py:200-205` | M03 (uid prefijado) | M03 | **No enumerado; fuera de write scope** (R-04). |
| `assert_message_shape` (`uid` int) | `tests/test_integration.py:297` | M03 | M03 | **No enumerado** (R-05). |
| `DEFAULT_UID_ORDER` y comparaciones | `tests/test_integration.py:58-66,453,530,548,624-646,667-677,700,717,735,746,760,769,774,790,898` | M03 | M03 | **No enumerado** (R-05). |
| `uids()` y comparaciones literales | `tests/test_search.py:354,414-1071` (21 líneas) | M03 | M03 | **No enumerado** (R-05). |
| `test_roundtrip_preserves_every_field` (schema 1/uid int) | `tests/test_state.py:61-71` | M03 | M03 | **No enumerado**; solo “tests que usan enteros” genérico (R-05). |
| `test_unsupported_schema_raises_state_corrupt` (`schema=2`) | `tests/test_state.py:175` | M03 (schema 2 válido) | M03 | **No enumerado** (R-05). |
| Mensajes W0 exactos (`integer >= 1`) | `tests/test_state.py:226-246` | M03 (migración) | M03 | **No enumerado**; contradice AC-06 (R-10). |
| `UT-ST-03.04` (integer corrupt) | `tests/test_state.py:405` | M03 (migración por tipo) | M03 | **No enumerado**; contradice AC-06 (R-10). |
| `attachments == [{"name": ...}]` en `show` | `tests/test_outlook.py:2291,2351,2369,2406,2420`; `tests/test_integration.py:735,774,898`; `tests/test_search.py:1291,1725,1732` | M08 (forma nueva) | M08 | **No enumerado**; `test_outlook.py` fuera de scope (R-06). |
| `test_doctor_reports_all_required_checks` | `tests/test_cli.py:1234-1250` | M02 | M02 | **No enumerado**; solo se menciona `10/10` (R-02/R-27). |
| `test_doctor_is_common_checks_plus_the_backend_checks` | `tests/test_cli.py:1083-1091` | M02 | M02 | **No enumerado** (R-02/R-27). |
| `TC-01.01` lista de chequeos | `tests/test_integration.py:343-357` | M02 | M02 | **No enumerado**; el write scope solo permite “el conteo” (R-02/R-27). |
| `UT-CLI-11.02` (`last_uid=42`) | `tests/test_cli.py:1344-1360` | M03 (uid prefijado) | M03 | **No enumerado** (R-27). |
| `StateStore(..., backend.check_state_uid)` en `_FakeBackend` | `tests/test_cli.py:60,971` | M03 (retira `check_state_uid`) | M03 | **No enumerado** (R-03). |
| `show` con uid entero (CLI real) | `tests/test_cli.py:1587` | M03 | M03 | **No enumerado** (R-05). |
| `UT-CLI-09.01` (23 códigos) | `tests/test_cli.py:758-784` | M01 (deja el catálogo incompleto: 9 códigos nuevos) | M01 | **No enumerado**; RC-11 dice actualizado (R-21). |
| `TC-07.04` (5 comandos) | `tests/test_integration.py:1356-1365` | M08/M11 (lo deja obsoleto: 6 comandos) | M11 | **No enumerado** (R-28). |
| `SMOKE-INSTALL.02` (regex `2\.0\.1`) | `tests/test_smoke.py:227` | M11 (3.0.0) | M11 | **Sí enumerado** en M11-T01 (`M11:27`). |
| `GOOD_VERSION` `2.0.0` | `tests/test_install_scripts.py:252` | M11 (3.0.0) | M11 | **Sí enumerado** en M11-T01; pero PKG-02 .02 lo define mal (R-30). |

## 6. Automatizabilidad (matriz de CI y hosts)

1. **CI no instala el paquete** (`.github/workflows/tests.yml` solo instala `pywin32`): PKG-01 .02 y cualquier caso “con el paquete instalado” debe usar metadata inyectada o skip documentado (R-22).
2. **SMOKE-ATT** se salta correctamente en CI si no hay cliente, pero el plan debe declarar la clase skip y no reutilizar IDs (R-08). El umbral de 50 ms de M09 es flaky (R-23).
3. **Timeouts**: UT-ERR-04 y UT-ATC-07 declaran plazo inyectado; UT-OL-ATT-03 .03/.04 no lo declara. Hay que fijar un `deadline`/fake clock también para COM, o el test espera 30/120 s reales.
4. **POSIX/Windows**: UT-ATT-09 .01/.02 y UT-AM-04 .03 deben llevar aserción condicional explícita; `UT-AM-04 .03` solo dice “en POSIX” (R-36). `UT-OL-ATT-02 .01` mezcla `0600` y ACL del perfil: separar por SO.
5. **`-k`**: `SMOKE-ATT` duplicado y `INS-01`/`UT-INS-01` rompen el criterio “verde ejecutado solo” (R-08/R-44).
6. **Plataforma**: UT-ST-06 .01/.02 y UT-DRV-05 .01 requieren patch de plataforma/registro; no se dice cómo (R-11).
7. **Presupuestos §12.2**: solo se prueba el cache-hit (< 50 ms); no hay caso Apple < 200 ms / Outlook < 600 ms ni de `attachment --all` lineal (R-24).

## 7. Veredicto

La suite propuesta **no está lista para ejecutarse tal cual**. Antes de lanzar M01 hay que corregir el write scope de M01–M03/M08 para incluir los tests que el cambio rompe, y antes de M09 hay que separar el trabajo de M09/M10. Los ACs con cobertura insuficiente (AC-01, AC-06, AC-07, AC-08, AC-12, AC-17, AC-21) necesitan casos nuevos, no solo renombrados. Los 18 goldens están bien contados, pero 7 no tienen un único dueño y 2 más cambian implícitamente en M11. Con las correcciones R-01..R-30 la suite sería coherente con el PRD y automatizable en la matriz de CI.

# Walkthrough — Fase W3: Outlook, lectura

| Campo | Valor |
|-------|-------|
| Fecha | 2026-11-04 |
| Rama | `feature/w3-outlook-read` (git flow), creada desde `feature/w2-backend-interface` @ `c52825b` |
| Commits | Uno solo para la fase |
| Plan | `docs/plans/2026-11-03-v2.0.0-windows-outlook.md` rev. 18 |
| Contrato | PRD y anexos del commit `f1ad969` (fijado en la cabecera del plan) |
| Orquestación | Sesión Opus 5.5; un subagente **Opus 5.5** por tarea (tabla de modelos del plan) |
| Host | Windows 11 x64, Python 3.14.7, `pywin32`, Outlook clásico 16.0.0.20430 abierto |
| Cierre | Revisión del planificador y OK del dueño asumidos; suite verificada solo en Windows. Tras W3 la ejecución se detiene hasta la orden del dueño. |

---

## 1. Tareas hechas

| Tarea | Qué se hizo | Casos de test |
|-------|-------------|---------------|
| W3-T01 | `tests/fakes/outlook.py` (OOM falso en memoria con `CallLog`, contadores de mutación, todos los escenarios de §7.5, zona horaria, registro y SecurityCenter inyectables, fallos COM con la forma de `pywintypes.com_error`) y `tests/fakes/run_cli.py` (lanzador en subprocess). Diseño del acceso al OOM verificado en el Outlook del host con código de solo lectura fuera del repo. | Base de OL-*; 31 tests de sanidad |
| W3-T02 | `backends/outlook_com.py`: detección en el orden de §12.6 (`pywin32` → `CurVer` ≥ 16 → `GetActiveObject`), caché `gen_py` en `<home>/tmp/gen_py`, proxy `ReadOnlyCom` con lista blanca `READONLY_MEMBERS`, vigilante de 30 s (D-03, con el gancho de `doctor` para W4), reintento ante rechazo transitorio y mapeo de HRESULT. Esqueleto de `OutlookBackend`. | OL-01.01…04, OL-02.01…07, OL-03.01…04, OL-04.01/.05/.06, OL-05.01/.02 |
| W3-T03 | Stores y cuentas: candidatos (Exchange en caché, IMAP, POP3, EAS, PST local) y excluidos con los 6 motivos, etiqueta y ruta de §B.3; `account.uuid` = `PR_RECORD_KEY`; `resolve_scope(..., excluded=)` resuelve claves contra excluidos para reportarlos. | UT-BE-01.01, OL-08.01 + 14 tests de clasificación |
| W3-T04 | Carpetas: recorrido en profundidad, solo carpetas de correo, carpetas de sincronización ocultas por función, bandeja como `INBOX` en cualquier idioma, `path`/`name`/`url` codificados, contadores de items buscables, `resolve_mailbox` según §15.3. | OL-10.01…03, OL-11.01…04, OL-12.01…03, OL-13.01 |
| W3-T05 | Items: `query` por `Folder.GetTable` con el `EntryID` permanente (`PR_LONGTERM_ENTRYID_FROM_TABLE`), fechas UTC y corte al segundo en Python, dedupe por Message-ID, destinatarios SMTP, adjuntos visibles, `find_message` con identificación de store excluido por `PR_RECORD_KEY`. | OL-14.01/.02, OL-15.01/.02, OL-16.01…03, OL-19.01…04, UT-BE-04.01…05 contra el falso |
| W3-T06 | `load_body` (solo cabeceras, S/MIME sin abrir, item que no se abre, texto plano, HTML, HTML sin texto, convocatorias) y `show` de punta a punta. | OL-17.01/.02, OL-20.01…07, OL-21.01/.02, OL-22.01/.02, OL-23.01…07 |
| W3-T07 | `mailboxes`, `search` (metadatos) y `show` de punta a punta con `W_STORE_EXCLUDED`; goldens de Outlook; gate de solo lectura (barrido de W3); contadores solo en `mailboxes`; traceback de todo `E_INTERNAL` en el log; `docs/INTERFACES.md` actualizado. | OL-06.01…06, OL-07.01…11, OL-09.01…04, TC-02.01…05, OL-28.01/.02, OL-29.01…03, OL-30.01…04 |

Cobertura: los 107 casos de W2 y W3 del catálogo tienen su método con el ID en el nombre.

**Criterio de cierre (plan §5 W3):** CU-03 (`search --from`), CU-04 (`search --unread --since`), CU-05 (`show`) y CU-06 (`mailboxes`) funcionan en Windows con el Outlook falso; OL-30 (gate de solo lectura de Outlook) en verde. Los goldens de Apple Mail y `test_readonly.py` no cambian respecto a W2.

---

## 2. Salida de la suite

Comando: `python -B -m unittest discover -s tests -t . -v` (PowerShell, host Windows).

| Momento | Corridos | Fallidos | Errores | Saltados |
|---------|----------|----------|---------|----------|
| Inicio de W3 (= fin de W2) | 505 | 0 | 0 | 10 |
| Tras W3-T01 | 536 | 0 | 0 | 10 |
| Tras W3-T02 | 556 | 0 | 0 | 10 |
| Tras W3-T03 | 573 | 0 | 0 | 10 |
| Tras W3-T04 | 587 | 0 | 0 | 10 |
| Tras W3-T05 | 609 | 0 | 0 | 10 |
| Tras W3-T06 | 628 | 0 | 0 | 10 |
| **Final W3** | **666** | **0** | **0** | **10** |

Los 10 saltados son `InstallShTest` sin `sh` en el `PATH` de PowerShell (§7.7). `python -m compileall -q src` sin errores.

---

## 3. Goldens nuevos (`tests/fixtures/expected/outlook/`)

Todos sobre `FakeOutlook.default()` (una cuenta Exchange en caché y un buzón compartido excluido) con zona fija UTC−04:00; la config declara la cuenta y el buzón compartido para fijar el texto de `W_STORE_EXCLUDED`.

| Golden | Contenido |
|--------|-----------|
| `mailboxes.json` | Una cuenta `Exchange (ana.perez@example.com)`, INBOX (3/2, incluida), `Deleted Items` y `Sent Items` (0/0); URLs `outlook://<uuid>/…`; `excluded_stores` con el compartido (`path: null`, `shared_mailbox`); `W_STORE_EXCLUDED` |
| `search.json` | 3 mensajes: normal con adjunto; solo cabeceras (`body` false/false/false, `W_BODY_NOT_LOCAL`); S/MIME (`body` true/false/false, `W_BODY_UNREADABLE` de S/MIME) |
| `show.json` | Mensaje normal en el orden de §12.4, cabeceras de transporte, adjunto `factura-2026-10.pdf`, `source.emlx_path: null`, `partial: false` |
| `show_header_only.json` | `readable: false`, `body_text: ""`, cabeceras sintetizadas, `W_BODY_NOT_LOCAL` |
| `show_smime.json` | `readable: false`, `attachments: []`, `W_BODY_UNREADABLE: S/MIME encrypted content is not supported`, sin `W_ATTACHMENTS_UNAVAILABLE` |

---

## 4. Verificación contra el Outlook del host (D-02, solo lectura)

Dos sondas fuera del repo (scratchpad de la sesión), ejecutadas con `python -I`, solo `GetActiveObject`, caché de `pywin32` redirigida, sin asignaciones ni miembros de escritura, sin libreta de direcciones e imprimiendo solo tipos, longitudes, conteos y prefijos.

- `CurVer` = `Outlook.Application.16`; versión 16.0.0.20430; 4 stores: dos buzones de entrega en caché (`ExchangeStoreType` 0 y **4**), buzón compartido (1) y carpetas públicas (2) ⇒ los candidatos se identifican por `Account.DeliveryStore`, como dice §B.3.
- `PR_RECORD_KEY` de 16 bytes, distinto en los 4 stores; los bytes 4..20 del `EntryID` permanente coinciden con él (5/5 y 5/5).
- La columna `EntryID` de las tablas es el id corto (48 hex); `PR_LONGTERM_ENTRYID_FROM_TABLE` (`0x66700102`) da el permanente de 140 hex (P-9).
- Las fechas de tabla llegan en UTC y los filtros DASL comparan en UTC; `ReceivedTime` difiere de `PR_MESSAGE_DELIVERY_TIME` en el offset local (P-5).
- `GetDefaultFolder(19…22)` identifica las carpetas de sincronización; una convocatoria no tiene `HTMLBody`.
- **No leídos de las bandejas leídas: iguales antes y después en todas las corridas** (1/1 y 0/0). `%TEMP%\gen_py` sin cambios.
- Desviación: la primera sonda tenía un error en los proptags y se repitió: abrió 5 items en cada una de dos bandejas en lugar de una (solo lectura de tipos y longitudes).

Ninguna contradicción con el anexo B.

---

## 5. Decisiones tomadas

| # | Tarea | Decisión |
|---|-------|----------|
| 1 | Proceso | La rama parte de `feature/w2-backend-interface`. Durante W3 otra sesión editó mucho `docs/PRD.md` y los anexos (secciones renumeradas, sin commitear): los subagentes leyeron la versión del commit `f1ad969`, que es el contrato que fija el plan. Esos cambios ajenos **no** están en el commit de W3. |
| 2 | Proceso | El dueño detuvo la ejecución durante W3-T02 (primer intento descartado sin escribir archivos) y la reanudó; W3-T02 se relanzó desde cero. |
| 3 | W3-T01 | `outlook_app` es un conector con `GetActiveObject` (en producción, `win32com.client`); lista blanca tipada por clase de objeto (`Columns.Add` permitido en `Table`, `Folders.Add` prohibido); se usa `Session`, no `GetNamespace`. |
| 4 | W3-T01/T05 | `Columns.Add` sobre un `Table` autorizado en las sondas del host: solo cambia la vista en memoria de la tabla, no el store. |
| 5 | W3-T01/T04 | Son items buscables `IPM.Note*` (incluido S/MIME) y todos los `IPM.Schedule.Meeting*` (convocatorias, cancelaciones y respuestas); quedan fuera `IPM.Report.*`, tareas, notas y los borrados IMAP (`MSGSTATUS_DELMARKED`). |
| 6 | W3-T02 | Gancho de `doctor` en el vigilante (`command` + `doctor_handler`) para W4-T03; el JSON de timeout se escribe con las funciones de `cli` para salir idéntico al resto de errores. Un error COM se reconoce por una clase `com_error` en su MRO (real y falsa). `MK_E_UNAVAILABLE` ⇒ `E_OUTLOOK_NOT_RUNNING`; `CO_E_CLASSSTRING` ⇒ `E_CLIENT_UNSUPPORTED`. |
| 7 | W3-T02 | Textos: `E_CLIENT_UNSUPPORTED` hint "install classic Outlook (version 16.0 or later); the new Outlook is not supported"; `E_OUTLOOK_NOT_RUNNING` hint "open classic Outlook with the same user, without elevation, and retry"; `E_CLIENT_TIMEOUT` "Outlook did not respond within <N> s (possible security prompt)" con hint a `doctor`. |
| 8 | W3-T03 | Los stores excluidos se devuelven en `accounts()` con la clave `excluded`; un store ilegible no tiene uuid y se resuelve solo por etiqueta; HTTP ⇒ `HTTP (<smtp>)`, otros tipos ⇒ `Other (<smtp>)`; cualquier error COM al leer un store ⇒ `unavailable` (ocupado, permiso y timeout se siguen propagando). |
| 9 | W3-T04 | `id` de carpeta = su `EntryID`; las referencias se comparan con la forma codificada; el nombre localizado de la bandeja no resuelve (solo `INBOX`). |
| 10 | W3-T05 | Prefiltro DASL en UTC con margen de −1/+2 min y corte exacto al segundo en Python; el Message-ID se traduce a un entero por instancia para reutilizar el dedupe del núcleo; Bcc nunca se reporta; un uid de longitud impar o menor de 20 bytes es "not found". |
| 11 | W3-T06 | Ganchos de `show` (`not_found_hint`, `unreadable_attachments`) y `mailboxes_without_counters` por `getattr`, fuera de `MailBackend`, para que su superficie siga siendo exactamente la de §9.3. Textos: `W_BODY_NOT_LOCAL: only the headers of uid … are stored locally; the body is never downloaded`; `W_BODY_UNREADABLE: the Outlook item for uid … cannot be opened`; el hint de "not found" remite a `excluded_stores`. |
| 12 | W3-T06 | Regla de adjuntos de Windows para todo cuerpo ilegible que no sea S/MIME: `attachments: []` y `W_ATTACHMENTS_UNAVAILABLE` solo si `has_attachments`. |
| 13 | W3-T07 | Orden de warnings: `W_NO_ACCOUNTS`, `W_STORE_EXCLUDED` (en el orden de los bloques), `W_ACCOUNT_LABELS_UNAVAILABLE`, los del comando y `W_FIRST_RUN` al final (§12.3 paso 6). |
| 14 | W3-T07 | Rendimiento: `search`, `show` y `new` no leen tablas para contadores; solo `mailboxes` cuenta, una vez por carpeta y backend. |
| 15 | W3-T07 | Todo `E_INTERNAL` (también el que viene de COM) registra su traceback con solo los frames y el tipo, sin el mensaje (§14). |

---

## 6. Puntos abiertos

1. **CLI real en Windows:** `mailboxes`, `search` y `show` funcionan contra Outlook a través del backend, pero `new`, `--text`, `--to`/`--cc` y el `doctor` de Outlook son de W4. No se ejecutó la CLI contra el Outlook real (las corridas reales son las SMOKE de W5).
2. **`scan.messages_read`** cuenta un S/MIME como leído aunque el item no se abre; OL-24.05 (W4-T02) lo define como "items abiertos": si W4 lo corrige, cambia `outlook/search.json`.
3. **Rendimiento pendiente para W4:** `load_body` lee `PR_TRANSPORT_MESSAGE_HEADERS` en cada mensaje (también en los snippets y en `--text`); un cuerpo legible sin adjuntos abre el item dos veces. OL-38 no existe en rev. 18; el presupuesto de §19 se comprobará en las SMOKE de W5.
4. **CI fuera de Windows** sin verificar (instrucciones para macOS en `docs/Walkthrough-w0-parity.md` §6, con `git checkout feature/w3-outlook-read`).
5. **Cambios ajenos** en `docs/PRD.md` y `docs/backends/*.md` siguen sin commitear para su dueño.
6. Revisión del planificador y OK del dueño asumidos. **La ejecución queda detenida tras W3 hasta la orden del dueño.**

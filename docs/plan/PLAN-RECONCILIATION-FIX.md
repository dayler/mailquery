# Plan — Corrección de la conciliación `PRD.md` ↔ `PRD-v2.1.md` (commit `ee24fe5`)

**Fecha:** 2026-11-12.
**Base:** `develop` en `ee24fe5`.
**Documentos que se corrigen:** `docs/PRD.md` y `docs/PRD-v2.1.md` §0.7. `docs/plan/PLAN-MASTER.md` solo en su registro (§11) y en la línea de cierre de §9.3 (D-3). Registro nuevo: `docs/KNOWN-DEFECTS.md` (BUG-01, D-2), ya creado por el planificador.
**Ejecutor:** implementador (`PRD.md`, `PRD-v2.1.md`); planificador (`PLAN-MASTER.md`).
**Estado:** ejecutado el 2026-11-12 en la rama `docs/prd-reconciliation-fix` (sin commit). Decisiones D-1…D-4 resueltas por el dueño el 2026-11-12 (§2.2). Resultado y verificaciones: §8.

---

## 0. Objetivo y criterio de terminado

Rehacer la conciliación para que `PRD.md` v2.1:

1. Cambie **solo** las reglas listadas en la tabla de supersesión (`PRD-v2.1.md` §0.2) y las que fijan CR-01 y CR-02 (§0.7.5); todo lo demás queda **idéntico** al `PRD.md` v1.3 (`ee24fe5^`), salvo la renumeración de referencias.
2. Incorpore **todo** el contenido normativo del delta (§1–§15), transcrito, no resumido ni reescrito.
3. No contenga contenido de plan (IDs de seguimiento, IDs de pruebas, milestones).
4. Describa lo que hace el código (`src/mailquery`), con las divergencias código↔delta resueltas por el dueño (D-1, D-2).

Y que `PRD-v2.1.md` §0.7 refleje el estado real: sin ítems redefinidos para ponerlos en verde y coherente con `PLAN-MASTER.md` (§0.7.4 punto 1).

Terminado = las verificaciones V1–V8 (§5) pasan.

---

## 1. Diagnóstico de `ee24fe5`

### 1.1 Cambios fuera de §0.2 (contenido v1.3 vigente borrado o recortado)

| Sección v1.3 | Pérdida |
|---|---|
| §11.3 | 12 filas de la tabla de correspondencia (pertenencia a carpeta, buzón agregado, carpetas listadas, mensajes buscables, `total`/`unread`, fechas, `from`/`to`/`cc`, `is_flagged`, cabeceras de `show`, cuerpo, `partial`, `source.emlx_path`); codificación `%25`/`%2F`, URL percent-encoded, reglas de etiqueta; "`--since` incluye y `--until` excluye al segundo". |
| §12.4 | Filas de uid de store excluido (Windows), textos `invalid uid …: expected an integer` / `expected an uppercase hexadecimal EntryID`, hint a `excluded_stores`, "(o no hay cuentas declaradas)". |
| §12.6 | "Los existentes no cambian de exit en macOS"; orden de detección de Outlook (`E_DEPENDENCY_MISSING` → `E_CLIENT_UNSUPPORTED` → `E_OUTLOOK_NOT_RUNNING`) y sus hints; "cada error debe incluir un `hint` accionable". |
| §12.8 | Dependencias y textos `not evaluated`, `available accounts: unknown (…)`, detalle de `state` sin cursor, timeout de 30 s dentro de `doctor`, "misma semántica en ambos backends", partes del criterio de `object_model_guard`. |
| §12.9 | Reglas de `--version`: solo opción global (con subcomando ⇒ `E_USAGE`), combinable con `--log-level`, precedencia `-v -h`/`-h -v`, "no necesita `pywin32`", "funciona con Outlook cerrado o sin FDA", "`<backend>` no se abre ni se consulta". |
| §12.10 | "Sustituye a `W_EMLX_UNREADABLE`"; definición por plataforma de "tiene adjuntos" en `W_ATTACHMENTS_UNAVAILABLE`. |
| §15.2 | "(siempre válido, aunque las etiquetas no estén disponibles)"; origen de etiquetas/UUID y reglas de comillas TOML; ejemplos de errores de sintaxis. |
| §17 | Fila "Disco lleno al escribir estado ⇒ exit 1, cursor intacto" (el código sigue así: `state.py:228`, `state.py:317-330`). |
| §20 | Criterios 1 y 2 reescritos (debían seguir vigentes); el 2 perdió "los contadores de no leídos del alcance no cambian". |
| §22.2 | Tabla histórica de 2.0.0 recortada (filas eliminadas y celdas acortadas). |
| §8 ADR-16 | Frase eliminada sin fila en §0.2. |
| §21.2, §21.3 | Añadidos sin origen en el delta (receta `02-attachment-recovery.md`, línea de idempotencia de `attachment`). |

### 1.2 Delta incompleto o reescrito

- **AC-01…AC-21 reescritos con otro significado** (AC-09, AC-10, AC-12, AC-13, AC-15, AC-18, AC-20 no coinciden con el delta ni con la matriz de `PLAN-MASTER.md` §4) y con una columna de IDs de pruebas.
- **§12.5 (`attachment`)** reescrito: falta la fila S/MIME/ilegible ⇒ `E_ATTACHMENT_UNREADABLE` antes de "0 adjuntos", la resolución de cuenta, las "Reglas adicionales" y los textos de referencia del delta §11.3.
- **No incorporados:** ayuda de `attachment` (delta §11.4); ejemplos C–H (§11.5); límites de `hint`/`detail`/`log_message` y plantillas de `message` (§11.7); filas de extracción del presupuesto (§12.2); `event=error` y sustitución por `log_message` (§12.1); detalle del chequeo `driver` (`no declared drivers`, `not evaluated: driver failed`, chequeos solo del nativo; §11.6); puntos 8–9 del modelo (§10.2: cursor de driver instalado no declarado, composición JSON multi-driver); limitación de etiquetas con `:` y reglas de validación (§13.1); `[attachments]` en el archivo completo de configuración (§13.2 → `PRD.md` §15.5); unos 10 de los 15 riesgos aceptados (§15); nota y ejemplo de §10.3.3.
- **Reglas recortadas:** RF-36, RF-38, RF-43, RF-45, RF-46, RF-49, RF-50, RNF-13, RNF-14, RNF-15, RNF-16, RNF-17, ADR-20.
- **§16.2 sin conciliar:** sigue diciendo "Cero red" aunque la fila "Red del núcleo y de plugins" de §0.2 lo incluye.
- **CR-01 incompleto:** §10.3.1 conserva "El acierto de caché no re-valida el contenido" sin adaptarla; faltan "`--force` fallido conserva la entrada verificada", el borrado de la entrada no verificada cuyo reintento falla, y el manifiesto con versión.
- **ADR-26** copiado tal cual ("el `PRD.md` no se edita hasta el release"): contradice al propio documento.
- **IDs de seguimiento en texto normativo:** RC-07, CL-07, CL-13 y referencias a CR-/DP- en RF/RNF/§.

### 1.3 Afirmaciones que el código contradice

| `PRD.md` (`ee24fe5`) | Código |
|---|---|
| `max_file_size_mb` 1–1024; `max_total_size_mb` 1–2048 | 1–500 y 1–1024 (`config.py:52-54`); el delta §13.1 es correcto. |
| Módulos `attachments/sanitizer.py`, `blocklist.py`, `manifest.py` | Reales: `blocking.py`, `catalog.py`, `sanitize.py`, `paths.py`, `screening.py`, `cache.py` (incluye el manifiesto), `engine.py`. Faltan `uid.py` y `plugins/` (`plugins/api.py`) en §9.2 y §10.1. |
| Manifiesto escrito "en el mismo commit que los archivos" | Cada archivo se publica con su `os.replace`; el manifiesto (`{"version": 1, "entries": …}`) se escribe después, best-effort (`engine.py:579-606`, `cache.py:61`). |
| Symlink en caché ⇒ `E_IO` "inmediatamente" | Se detecta al publicar (`cache.py:468-485`); antes, la caché vale miss y se extrae a staging, que se limpia. Coincide con CR-01 ("la publicación falla"). |
| Orden de 15 pasos de §12.5 | El código sigue el delta §11.3 (filas 1–15, `INTERFACES.md`); el texto de `ee24fe5` no. |
| Re-extracción fallida ⇒ `E_ATTACHMENT_UNAVAILABLE` (§10.4) | Se propaga el código real del fallo (`engine.py:564-577`). Es también divergencia con el delta → D-1. |
| `attachments: "remote"` admitido (RF-38, RF-43, RF-46, §4) | `cli.py:1059` lo rechaza como `"none"` (`E_ATTACHMENT_UNAVAILABLE`, `unsupported`), decisión de M08 (`M08-…md:122`, `INTERFACES.md:1020`). Divergencia con el delta → D-2. |

### 1.4 §0.7 de `PRD-v2.1.md`

- CL-09 redefinido ("`PRD.md` sin cambios…" → "conciliado normativamente") y marcado 🟢 en el mismo commit.
- RC-25, CL-05 y CL-08 en 🟢 sin release; el paquete es `3.0.0a0`. Contradice `PLAN-MASTER.md:351` (siguen ⚪ hasta el release), que no se actualizó.
- Párrafo de §0.7.3 dice que CL-12 queda "validado o archivado"; CL-12 sigue ⚪.
- §0.7.1 sigue diciendo que CL-09 "permanece ⚪ por diseño"; el texto de CR-02 se cambió a "quedan conciliados (🟢)".
- Columna "Conciliación" de CR-01/CR-02 en 🟢 con la conciliación incompleta.
- CL-01 🟢 está respaldado (`PLAN-MASTER.md` §3: ACs 🟢 21/21); se mantiene.

---

## 2. Decisiones

### 2.1 Resueltas por el planificador

| ID | Decisión | Motivo |
|---|---|---|
| R-1 | **Se reconstruye `PRD.md` desde v1.3 (`ee24fe5^`)**, no se parchea `ee24fe5`. Se puede reutilizar texto de `ee24fe5` solo si coincide con el delta. | Recupera de una vez todo lo borrado en §1.1 y hace la verificación V1 mecánica. |
| R-2 | **Operaciones permitidas:** (a) *sustituir* el texto de una regla listada en §0.2, con el texto del delta; (b) *añadir* el contenido nuevo del delta (IDs que continúan la numeración: O8–O14, CU-08/09, RF-35–51, RNF-12–17, ADR-17–27, AC-01–21, y las secciones §1–§15 del delta), transcrito; (c) *aplicar* CR-01/CR-02 sobre las reglas que listan. Cualquier otra frase cambiada o añadida es un defecto. | Es la definición de conciliación de §0.3. |
| R-3 | **Transcribir, no resumir.** Solo se adaptan: referencias (`PRD.md §N` → `§N`; `§N` del delta → su sección nueva), "este delta" → "este documento", y el texto que CR-01/CR-02 sustituyen. | §1.2: el resumen perdió reglas. |
| R-4 | **AC-01…AC-21 conservan su ID y su texto del delta** (salvo CR-01 en AC-12 y AC-20). No se renumeran: v1.3 no usa AC-xx (delta §0.1 punto 4), y renumerar rompe la matriz de `PLAN-MASTER.md` §4. Los criterios 1 y 2 de v1.3 quedan **literales**; los 3 y 4 se sustituyen por AC-01…AC-21 (fila "Criterios de aceptación" de §0.2). Sin columna de verificación. | Trazabilidad con CL-01 y con la evidencia de M01–M11. |
| R-5 | **Sin IDs de seguimiento en el texto normativo:** ni RC-, CL-, CR-, DP-, UT-, PKG-, TC-, SMOKE-, DOC-, INS-, M01–M11. Las decisiones DP-01…DP-03 y los cambios CR-01/CR-02 se escriben como reglas en su sección dueña y se registran en el Anexo D (fecha de aprobación) y en la fila 2.1 de la tabla de versiones. | El PRD no contiene plan; §0.7 deja de existir al retirar el delta. |
| R-6 | **ADR-26** se conserva con su ID y se marca cumplido, como ADR-12: "(cumplido en v2.1: el delta se concilió en este documento)". **ADR-12** sigue la fila "Tipo y formato de `uid`": queda marcado como superado por ADR-19. | Sin huecos de numeración y sin contradicción. |
| R-7 | **Arquitectura (§9.1, §9.2, §10.1) con los módulos reales**: `uid.py`, `plugins/` (`api.py`), `backends/registry.py`, `attachments/` con `blocking.py`, `catalog.py`, `sanitize.py`, `paths.py`, `screening.py`, `cache.py`, `engine.py`. La vista de componentes y el flujo se toman del delta §9.1/§9.2; la tabla de responsabilidades de v1.3 se amplía con una fila por módulo nuevo (responsabilidad según delta §9.3). | La arquitectura se queda en el PRD con cambios mínimos y debe describir el código. |
| R-8 | **§22.2 (2.0.0) queda literal.** Los cambios de 3.0.0 (delta §0.4 y §0.4.1) van en una subsección nueva. | Fila "Cambios de comportamiento en macOS" de §0.2: "sustituye/amplía". |
| R-9 | **Recetas (§21.2) y §21.3 sin añadidos**: el delta no los cambia (solo §21.1). | R-2. |
| R-10 | **Numeración de v1.3 conservada; las secciones nuevas se añaden al final de cada capítulo:** §6.5–§6.7, §9.4 (flujo de `show`/`attachment`), §10.3 (§10.3.1–§10.3.4), §10.4, §12.11 (`attachment`), §22.4 (cambios visibles en 3.0.0) y §23.1. Por tanto, en §3 de este plan: el flujo es §9.4 (no §9.3) y la garantía de solo lectura sigue en §9.3; `attachment` es §12.11; el contrato JSON sigue en §12.5, errores §12.6, ayuda §12.7, `doctor` §12.8, `--version` §12.9, warnings §12.10; la versión sigue en §22.3 y los cambios de 3.0.0 van en §22.4. Sin §16.4: el modelo de confianza de Δ§4 tiene como dueña a `PRD.md` §4. | Corrección del 2026-11-12 sobre la versión anterior de esta fila (que adoptaba la numeración de `ee24fe5`): con la numeración estable siguen siendo válidas todas las referencias a `PRD.md` ya escritas en código y documentación. |
| R-11 | **Ajustes de coherencia cerrados.** Una regla de v1.3 que no está en §0.2 pero quedaría contradicha por una fila de §0.2 se ajusta **solo en la frase afectada**. Lista cerrada: RF-01 (uid de `last_uid`, fila `uid`), RF-04 (forma de `attachments`, fila `show`), RF-05 (S/MIME, Δ§0.4), RF-07 (dedupe por driver, RF-37), RF-31 (`drivers`, fila `--version`), RNF-05 (permisos de `attachments/` y manifiesto, fila "Layout del home"), RNF-07 (`drivers=`, fila "Logs"), RNF-09 (adjuntos extraídos, Δ§4 punto 3), O7 y referencias renumeradas. Fuera de esta lista no hay ajustes. | Evita contradicciones internas sin abrir la puerta a reescrituras. |

### 2.2 Decisiones del dueño (resueltas el 2026-11-12)

**Resolución:**

- **D-1 = (a).** El PRD adopta el código. §10.4 y la fila "Cron externo borra archivos" de §23.1: "si la re-extracción falla, el comando falla con el código de ese fallo (§12.7)". Sin cambio de código.
- **D-2 = (a), registrado como defecto.** El PRD describe el comportamiento actual: en 3.0.0 `attachment` solo extrae de drivers con `attachments: "local"`; `"remote"` se puede declarar (exige `network: true`) y `attachment` responde `E_ATTACHMENT_UNAVAILABLE` (`unsupported`) antes de abrir el store. Según el dueño, **es un defecto: la extracción desde plugins `"remote"` debe estar soportada**. Queda registrado en [`docs/KNOWN-DEFECTS.md`](../KNOWN-DEFECTS.md) (BUG-01). El PRD añade una nota "Pendiente conocido (abierto)" en RF-46, con el mismo formato que §19 usa con `PERFORMANCE-BACKLOG.md`: "en 3.0.0 un driver `attachments: "remote"` no puede extraer adjuntos; debe admitirse según ADR-22; seguimiento en `KNOWN-DEFECTS.md`". La nota no lleva el ID BUG-01 (V5).
- **D-3 = (a).** Se aplica §6.
- **D-4 = (a).** Se aplica §6 (fila Cabecera).

**Preguntas planteadas:**

| ID | Pregunta | Opciones | Recomendación | Bloquea |
|---|---|---|---|---|
| D-1 | Re-extracción fallida de un archivo borrado o alterado durante la ejecución: delta §10.4 y §15 dicen `E_ATTACHMENT_UNAVAILABLE`; el código propaga el código real (`E_ATTACHMENT_UNREADABLE`, el mapeado del driver…). | (a) el PRD adopta el código; (b) se corrige el código. | **(a):** el código usa el mismo mapeo que cualquier extracción (§11.7) y AC-20 no fija código. Texto: "si la re-extracción falla, el comando falla con el código de ese fallo (§12.7)". | T5 (§10.4, §23.1) |
| D-2 | `attachments: "remote"`: el delta lo admite (el plugin obtiene los bytes de su origen; §0.2 fila "No objetivos", §4.2, RF-43, RF-46, ADR-22); el código, M08 e `INTERFACES.md` lo rechazan con `E_ATTACHMENT_UNAVAILABLE` (`unsupported`). | (a) el PRD adopta el código: en 3.0.0 `attachment` solo admite `"local"`; `"remote"` se declara pero no se extrae; (b) se corrige el código para extraer desde un plugin `"remote"`. | **(a):** no hay plugins remotos y el usuario pidió fidelidad al código; se cambian RF-43, RF-46, §4 (Plugins/Adjuntos), §3.3, la fila de `attachment` en §12.5 fila 5 y la regla de capacidades de RF-38 mantiene `"remote"` ⇒ `network: true`. | T3, T4, T6 |
| D-3 | CL-09 y el estado de release en §0.7. | (a) RC-25, CL-05 y CL-08 vuelven a ⚪ (release pendiente); CL-09 se redefine como cambio de plan registrado ("`PRD.md` conciliado con §0.2 y CR-01/CR-02; el resto idéntico a v1.3") y pasa a 🟢 solo al pasar V1–V8; (b) restaurar CL-09 literal ("`PRD.md` sin cambios") y revertir la conciliación hasta el release. | **(a):** §0.3 exige conciliar antes del release, no en él; la conciliación ya se hizo y conviene dejarla correcta. El cambio de ítem se registra en `PLAN-MASTER.md` §11 y en su §9.3 (§0.7.4 puntos 1 y 2). | T9, T10 |
| D-4 | Estado del delta tras conciliar: §0.3 dice "se elimina o queda como anexo histórico". | (a) se mantiene el archivo con una nota de cabecera: §1–§15 históricos sin valor normativo, `PRD.md` v2.1 es la fuente de verdad; §0.7 sigue operativo como gate del release; se archiva al publicar `3.0.0`; (b) se elimina ya. | **(a):** §0.7 sigue siendo el gate de CL-05/CL-12/RC-25 hasta el release. | T9 |

---

## 3. Mapa de conciliación (destino → origen → operación)

Operaciones: **C** = conservar literal v1.3 (solo referencias renumeradas); **S** = sustituir con el delta; **A** = añadir del delta; **CR** = aplicar CR-01/CR-02. Referencias "Δ§" = secciones de `PRD-v2.1.md`.

| Sección destino | Operación | Origen | Notas |
|---|---|---|---|
| Cabecera | S | — | Versión 2.1; paquete `3.0.0` (en `develop` `3.0.0a0`, sin publicar); fecha; estado "implementado en `develop`, sin publicar". |
| Tabla de versiones | A | — | Fila 2.1 que resume Δ y nombra CR-01/CR-02. Única fila nueva. |
| §1 | S + A | Δ§0.2 fila "Red"; Δ§1 | Tabla de clientes con plugins; "sin red" → núcleo e internos; resumen Δ§1 transcrito. Sin `$O(1)$`. |
| §2 | A | Δ§2 | Puntos 1–4 de Δ§2 transcritos. |
| §3.2 | A | Δ§3.1 | O8–O14. |
| §3.3 | S + A | Δ§0.2 fila "No objetivos"; Δ§3.2 | Viñeta de adjuntos remotos sustituida; resto de Δ§3.2 añadido. Ajuste D-2. |
| §4 | S + A | Δ§0.2 filas "I-1" y "Bytes de adjuntos en Outlook"; Δ§4 | Cita I-1 de Δ§4; viñeta Windows con la excepción COM de §0.2; puntos 1–4 de Δ§4. Ajuste D-2. |
| §5 | A | Δ§5 | CU-08, CU-09. |
| §6.1–§6.3 | C + S | Δ§0.2 | Solo RF-01 (uid string), RF-04/RF-05 (adjuntos, S/MIME), RF-07 (dedupe por driver). Resto literal. |
| §6.4 | S | Δ§0.2 | RF-26 ← RF-36 (selección); RF-27 ← RF-40 (uid); RF-31 añade `drivers`. Resto literal. |
| §6.5–§6.7 | A + CR | Δ§6.1–§6.3 | RF-35…RF-51 literales; CR-01 sobre RF-45 y RF-51; D-2 sobre RF-43/RF-46. |
| §7 | S + A | Δ§0.2; Δ§7 | RNF-02 (red), RNF-04 (orden total); RNF-05, RNF-07, RNF-09 según R-11; RNF-12…RNF-17 literales. |
| §8 | A + R-6 | Δ§8 | ADR-17…ADR-27 literales; ADR-12 y ADR-26 marcados. ADR-16 literal v1.3. |
| §9.1 | S | Δ§9.1 | Diagrama de Δ con nombres de módulo reales (R-7). |
| §9.2 | C + A | Δ§9.3; código | Tabla v1.3 + filas `uid.py`, `plugins/api.py`, `backends/registry.py`, módulos de `attachments/` (R-7). |
| §9.3 (nuevo) | A | Δ§9.2 | Flujo de `show`/`attachment` literal. |
| §9.4 (antes §9.3) | S | Δ§0.2 fila "Bytes de adjuntos en Outlook" | Literal v1.3 + excepción COM. |
| §10.1 | S | código | Árbol con módulos reales. |
| §10.2 | S | Δ§10.1 | Árbol de Δ + `.manifest.json` (CR-01). |
| §10.3 | A + CR | Δ§10.3 | §10.3.1–§10.3.3 literales con ejemplo y nota de §10.3.3; frase de acierto de §10.3.1 adaptada a CR-01: "El acierto no re-inspecciona contenido: solo se sirve si su SHA-256 coincide con el registrado en el manifiesto, calculado sobre bytes que ya pasaron la pantalla". §10.3.4 = contrato CR-01 completo de Δ§0.7.5 (las 7 viñetas, incluidas versión del manifiesto, `--force` fallido y borrado de la entrada no verificada). |
| §10.4 | S + CR | Δ§10.4 | Literal + "validada por manifiesto"; D-1. |
| §11.1 | S | Δ§0.2; Δ§10.2 puntos 1–3 | Tabla v1.3: fila Cuenta (plugins), Mensaje (`uid` string), Cuerpo (`attachments` nuevo). |
| §11.2 | S | Δ§10.2 puntos 4–6 | Ejemplo `schema: 2`; corrupción/validación de v1.3 adaptadas al uid prefijado; migración y validación de Δ literales. |
| §11.3 | C + S + A | Δ§0.2 filas uid y adjuntos; Δ§10.2 puntos 2, 7–10 | **Tabla v1.3 completa**; solo cambian filas `uid`, `account.label/uuid` y `Adjuntos`; se añade la columna "Plugins externos (API 1)" con los valores de Δ§10.2 punto 2 y "según el conector" en las filas que Δ no define; la frase final sustituye solo el orden "a igual fecha el uid se compara como texto" por el orden total; puntos 7–10 de Δ§10.2 literales. |
| §12 tabla | S | Δ§11.1 | Seis comandos. |
| §12.2, §12.3 | S | Δ§10.2 punto 7 | Solo la frase de orden. |
| §12.4 | S | Δ§0.2 fila `show`; Δ§11.3 | Ejemplos con uid prefijado y legado; `attachments` RF-43; S/MIME; **filas de store excluido y textos de v1.3 conservados** (aplicados al uid legado/`outlook:`); filas nuevas de driver. |
| §12.5 (nuevo) | A | Δ§11.2, Δ§11.3 | Sintaxis, campos de respuesta, **tabla de precedencia de 15 filas literal**, reglas adicionales y textos de referencia. D-2 en fila 5. |
| §12.6 | S + A | Δ§0.2 fila "Contrato JSON"; Δ§11.5 | Ejemplos con uid string; ejemplos A–H literales. |
| §12.7 | S + A | Δ§0.2 fila "Códigos"; Δ§11.7 | Tabla de exits ampliada; **texto v1.3 conservado** (detección de Outlook, hints, "no cambian de exit en macOS"); regla de propiedad, diccionario, mapeo y plantillas de Δ§11.7 literales. |
| §12.8 | S + A | Δ§0.2 fila "Tabla de comandos y ayuda"; Δ§11.4 | Ayuda raíz: comando `attachment` y línea de exits **tal como la imprime el código** (`cli.py:89-91`); ayuda de `attachment` de Δ§11.4. |
| §12.9 | S + A | Δ§11.6 | Tabla de chequeos con `driver`; **reglas comunes de v1.3 conservadas**; Δ§11.6 literal. |
| §12.10 | S + A | Δ§11.9 | Ejemplos y formato aditivo; **reglas de v1.3 conservadas**; viñetas de Δ§11.9. |
| §12.11 | S | Δ§11.8; Δ§0.4 fila S/MIME | Literal v1.3 + frase de "sin warnings nuevos"; fila `W_ATTACHMENTS_UNAVAILABLE`: se conserva la definición por plataforma y se cambia solo el caso S/MIME. |
| §13.1–§13.3 | S | Δ§0.2 fila "Instalación" | Entry points, `pipx inject`, versión; desinstalar un plugin (DP-03 como regla). |
| §14 | S + A | Δ§12.1 | `drivers=`, evento `end` y `event=error` de `attachment`, `log_message`, log del plugin; prohibiciones de v1.3 ampliadas. |
| §15 (completo) | S + A | Δ§13 | §15.1 propiedades con rangos de Δ§13.1 (1–500, 1–1024); §15.2 regla del primer `:` + **texto v1.3 conservado** (formas, comillas, errores de sintaxis con `[scope."…"]`); §15.3 + reglas de validación de Δ§13.1 (incluida la limitación de `:`); §15.4/§15.5 con `[attachments]` de Δ§13.2; §15.6 + Δ§13.3. |
| §16.2 | S | Δ§0.2 fila "Red" | "Cero red" → núcleo e internos; plugins con `network: true`. |
| §17 | S + A | Δ§0.2 fila "Errores y timeouts de Windows" | Tabla v1.3 completa (**incluida "Disco lleno al escribir estado"**) + filas de Δ. |
| §19 | S + A | Δ§12.2 | Tabla de Δ§12.2 completa (acierto, 1 adjunto, `--all`) y su párrafo; pendiente conocido de v1.3 literal. |
| §20 | S | Δ§0.2 fila "Criterios"; Δ§14 | Criterios 1 y 2 literales v1.3; AC-01…AC-21 literales (R-4) con CR-01 en AC-12 y AC-20. |
| §21.1 | S | Δ§0.2 fila "Operación con el harness" | Puntos 5 y 6. |
| §22.2 | C | — | Literal v1.3 (R-8). |
| §22.3 (nuevo) | A | Δ§0.4, Δ§0.4.1 | Tablas macOS y Windows. |
| §22.4 (antes §22.3) | S + CR | Δ§0.5; CR-02 | `3.0.0`, regla de incompatibilidad; `develop` anuncia `3.0.0a0`, sin publicar. |
| §23.1 (nuevo) | A + CR | Δ§15 | **Todas** las filas; fila "Caché manipulada" adaptada a CR-01; D-1 en la fila del cron. |
| Anexo D | A | Δ§0.6; Δ§0.7.5; ADR-17–27 | Entradas de decisiones con fecha de aprobación: 2026-11-11 para ADR-17…ADR-27 y DP-01…DP-03; 2026-11-12 para CR-01 (`d88e6df`); 2026-11-11 para CR-02 (`4cf88a6`); D-1 y D-2 con la fecha de la respuesta del dueño. |
| Anexo E, F | S + A | Δ | uid prefijado, ejemplos de `attachment`, glosario. |

Toda sección que no aparece en la tabla es **C**.

---

## 4. Pasos de ejecución

Rama: `docs/prd-reconciliation-fix` desde `develop`. **No** incluir el cambio local de `docs/ROADMAP.md`. Commit en la rama; **merge a `develop` solo con orden del dueño**.

| Paso | Acción | Depende de |
|---|---|---|
| T1 | Crear la rama y restaurar v1.3: `git show ee24fe5^:docs/PRD.md > docs/PRD.md`. Guardar `ee24fe5:docs/PRD.md` en un archivo temporal fuera del repo como fuente de fragmentos reutilizables. | — |
| T2 | Insertar las secciones nuevas vacías según la estructura destino (§3: §6.5–§6.7, §9.3, §10.3, §10.4, §12.5, §22.3, §23.1) y renumerar §9.3→§9.4, §12.5→§12.6 … §12.10→§12.11, §22.3→§22.4, con todas sus referencias internas (incluidas las del Anexo D). | T1 |
| T3 | Aplicar las filas **S** y **A** de §1–§9 del mapa (cabecera, §1–§8, §9.1–§9.4). | T2; D-2 para §3.3, §4, RF-43, RF-46 |
| T4 | Aplicar §10–§12 del mapa, incluida la tabla de precedencia literal y los ejemplos A–H. | T2; D-2 para §12.5 fila 5 |
| T5 | Aplicar CR-01 (§10.3.1, §10.3.4, §10.4, RF-45, RF-51, AC-12, AC-20, §23.1) y CR-02 (§12.10, §13.2, §22.4). | T3, T4; D-1 |
| T6 | Aplicar §13–§24 del mapa (instalación, logs, configuración, seguridad, errores, rendimiento, AC, harness, versiones, riesgos, anexos). | T2; D-2 |
| T7 | Pasar V1–V6 y V8 (§5); corregir y repetir hasta que pasen. | T3–T6 |
| T8 | Commit `docs(prd): redo PRD.md v2.1 reconciliation strictly against PRD-v2.1 §0.2 and CR-01/CR-02`. | T7 |
| T9 | `PRD-v2.1.md`: aplicar §6 de este plan según D-3 y D-4. | D-3, D-4; T7 |
| T10 | Planificador: registrar en `PLAN-MASTER.md` §11 la corrección y, si D-3 = (a), el cambio de definición de CL-09 y la línea de §9.3. | D-3 |
| T11 | Pasar V7; commit `docs(prd-v2.1): restore §0.7 release states and record the reconciliation`. | T9, T10 |

---

## 5. Verificación

Ejecutar desde la raíz del repo. Todas deben pasar antes de T8/T11.

- **V1 — Nada cambia fuera del mapa.** Para cada sección marcada **C** (o no listada), su texto es igual al de `ee24fe5^` salvo números de sección en referencias. Procedimiento: extraer cada sección por su título con un script temporal (fuera del repo) en ambas versiones, normalizar `§\d+(\.\d+)*` a `§N` y comparar; cero diferencias. Para las secciones **S**, revisar `git diff --word-diff=plain ee24fe5^ -- docs/PRD.md` y confirmar que cada hunk corresponde a una fila de §0.2, a un texto del delta, a CR-01/CR-02, a D-1/D-2 o a un ajuste de la lista cerrada R-11 (§3).
- **V2 — Todo el delta está.** Cada ID aparece al menos una vez en `docs/PRD.md`:
  ```bash
  for id in O8 O9 O10 O11 O12 O13 O14 CU-08 CU-09 $(seq -f 'RF-%g' 35 51) $(seq -f 'RNF-%g' 12 17) $(seq -f 'ADR-%g' 17 27) $(seq -f 'AC-%02g' 1 21) E_DRIVER_UNKNOWN E_ATTACHMENTS_DISABLED E_PLUGIN_INCOMPATIBLE E_PLUGIN_FAILED E_ATTACHMENT_UNAVAILABLE E_ATTACHMENT_UNREADABLE E_ATTACHMENT_BLOCKED E_ATTACHMENT_TOO_LARGE E_IO "no declared drivers" "declared drivers: unknown (config failed)" "has no attachments" "event=error" "attachment requires exactly one of --index or --all"; do grep -qF -- "$id" docs/PRD.md || echo "FALTA: $id"; done
  ```
  Salida vacía. Además, los ejemplos A–H de Δ§11.5, la ayuda de Δ§11.4 y las 15 filas de Δ§11.3 están presentes, y §23.1 tiene todas las filas de Δ§15.
- **V3 — AC literales.** Extraer las líneas `**AC-NN.**` de Δ§14 y de `PRD.md` §20 y compararlas: idénticas salvo AC-12 y AC-20 (CR-01) y referencias. Sin columna de verificación ni IDs de pruebas.
- **V4 — Reglas literales.** Mismo método que V3 para RF-35…RF-51, RNF-12…RNF-17 y ADR-17…ADR-27: idénticas salvo CR-01 (RF-45, RF-51, ADR-24), CR-02 (ADR-27), D-1, D-2, ADR-26 (R-6) y referencias.
- **V5 — Sin contenido de plan.**
  ```bash
  grep -nE '\b(RC|CL)-[0-9]{2}\b|\bCR-0[12]\b|\bDP-0[1-3]\b|\b(UT|PKG|TC|SMOKE|DOC|INS)-[A-Z0-9]|\bM(0[1-9]|1[01])\b' docs/PRD.md
  ```
  Solo puede salir la fila 2.1 de la tabla de versiones y el Anexo D.
- **V6 — Referencias.** Todo `§N` o `§N.N` citado en `PRD.md` existe como encabezado; ninguna referencia apunta a `PRD-v2.1.md` como norma (solo la fila 2.1 de versiones y una mención histórica, D-4). RF-46 enlaza `KNOWN-DEFECTS.md` en su nota "Pendiente conocido" (D-2) y §19 sigue enlazando `PERFORMANCE-BACKLOG.md`.
- **V7 — §0.7 coherente.** Estados y textos según §6; `PLAN-MASTER.md` §9.3 y §11 coinciden con §0.7.
- **V8 — Fidelidad al código.** Cada afirmación coincide con el código:

| Afirmación en `PRD.md` | Evidencia esperada |
|---|---|
| `[attachments]` defaults 100/200/50/`true`; rangos 1–500, 1–1024 (`>= max_file_size_mb`), 1–500 | `config.py:47-56`, `config.py:464-470` |
| Módulos de §9.2/§10.1 | `ls src/mailquery src/mailquery/attachments src/mailquery/backends src/mailquery/plugins` |
| Manifiesto `{"version": 1, "entries": …}`, atómico, best-effort tras publicar; SHA-256 completo en cada acierto | `cache.py:61`, `cache.py:420-424`, `cache.py:519-540`, `engine.py:579-606` |
| `--force` fallido conserva entrada verificada; entrada no verificada que falla se borra y se quita del manifiesto | `engine.py:384-422`, `cache.py:542-571` |
| Enlace en `attachments/`, `<driver>/`, `<native_id>/` ⇒ `E_IO` al publicar, sin escribir en la caché | `cache.py:443-485`, `cache.py:618-624` |
| Precedencia de `attachment` = Δ§11.3 | `cli.py:556-572`, `cli.py:812-871`, `cli.py:1126-1169`, `engine.py:333-606` |
| `attachments: "remote"` según D-2 | `cli.py:1054-1067` |
| Re-extracción fallida según D-1 | `engine.py:564-577` |
| Disco lleno al escribir estado ⇒ `E_INTERNAL`, exit 1 | `state.py:317-330` |
| `--version`: formato, solo global, `-v -h`/`-h -v`, metadata sin importar plugins, filtro de internos por plataforma | `cli.py:274-311`, `registry.py:89-127` |
| Orden de detección de Outlook y hints | `outlook_com.py:116-120`, `outlook_com.py:784-818` |
| Línea de exits de la ayuda raíz | `cli.py:89-91` |
| Timeouts 30 s / 120 s por adjunto, `E_CLIENT_TIMEOUT` exit 3 | `plugins/api.py:70-100`, `plugins/api.py:459-466` |
| Prefijo de driver inválido o no instalado en `[scope]` ⇒ `E_DRIVER_UNKNOWN` | `config.py:503-515` |
| Migración schema 1→2, poda del anillo, `cursor.last_uid` de driver no instalado ⇒ `E_STATE_CORRUPT` | `state.py:46`, `state.py:528-596` |

---

## 6. Corrección de `PRD-v2.1.md` §0.7 (T9)

Partir de `ee24fe5^:docs/PRD-v2.1.md` para las filas tocadas por `ee24fe5` y aplicar:

| Elemento | Con D-3 = (a) (recomendado) |
|---|---|
| RC-25 | Restaurar fila original: "Release futuro del `3.0.0`…", ⚪. |
| Párrafo de §0.7.3 | Restaurar original, cambiando solo "CL-09" por la nueva definición: "CL-05, CL-08 (en lo que dependa de RC-25) y CL-12 quedan ⚪ pendientes del release futuro; CL-09 se cierra con la conciliación de `PRD.md` v2.1". |
| CL-01 | 🟢 (se mantiene). |
| CL-05 | Restaurar fila original, ⚪. |
| CL-08 | Restaurar fila original, ⚪. |
| CL-09 | Ítem: "`PRD.md` conciliado: cambian solo las reglas de §0.2 y las de CR-01/CR-02; el resto es idéntico a v1.3". Evidencia: "verificaciones V1–V8 de `plan/PLAN-RECONCILIATION-FIX.md`". Estado 🟢 solo tras pasar V1–V8. |
| §0.7.1 última frase | "La conciliación con `PRD.md` (CL-09) se cierra con la verificación de `plan/PLAN-RECONCILIATION-FIX.md`." |
| §0.7.4 punto 3 | Añadir: "El registro y el checklist siguen operativos como gate del release hasta publicar `3.0.0`; después se archivan." |
| CR-01, CR-02 (columna Conciliación) | 🟢 tras pasar V1–V8. |
| Párrafo CR-02 | Restaurar "RC-25 y CL-05 siguen ⚪". |
| Cabecera (D-4 = (a)) | Nota: "§1–§15 son históricos y sin valor normativo desde la conciliación en `PRD.md` v2.1 (2026-11-12); §0.7 sigue operativo como gate del release `3.0.0`." Estado: "conciliado en `PRD.md` v2.1; no publicado". |

Con D-3 = (b): restaurar §0.7 completo de `ee24fe5^` y revertir `PRD.md` a v1.3; este plan se reduce a T1 + T9 + T11.

---

## 7. Fuera de alcance

- Cambios de código. La corrección de BUG-01 (`docs/KNOWN-DEFECTS.md`) es un trabajo aparte del implementador; al cerrarla, el PRD recupera el texto del delta en RF-43, RF-46, §4 y §12.5 fila 5, y se retira la nota "Pendiente conocido".
- `INTERFACES.md`, READMEs, recetas y skills: no se tocan en este plan.
- `docs/ROADMAP.md` (cambio local sin commit, ajeno a este plan).
- Bump a `3.0.0`, tags, release y merge a `main`.

---

## 8. Ejecución (2026-11-12)

- `docs/PRD.md` se generó desde `ee24fe5^:docs/PRD.md` (v1.3) con un script que aplica solo las operaciones de §3 (R-10) y transcribe el delta; las referencias del delta se traducen a la numeración de §3/R-10.
- **V1:** ninguna sección de v1.3 desaparece; las secciones cambiadas son exactamente las marcadas S/A en §3; cada línea eliminada de v1.3 corresponde a una fila de §0.2, a CR-01/CR-02, a D-1/D-2 o a la lista R-11.
- **V2:** presentes O8–O14, CU-08/09, RF-35…RF-51, RNF-12…RNF-17, ADR-17…ADR-27, AC-01…AC-21, los errores nuevos, los ejemplos A–H, la ayuda de `attachment`, la precedencia de 15 filas y todos los riesgos de Δ§15.
- **V3/V4:** AC, RF, RNF y ADR literales salvo CR-01 (AC-12, RF-45, RF-51, ADR-24), CR-02 (ADR-27), D-2 (RF-46), ADR-26 (R-6) y referencias.
- **V5:** IDs DP-/CR- solo en la fila 2.1 de versiones y en el Anexo D; ningún RC-/CL-/UT-/M01–M11.
- **V6:** todas las referencias `§N` de `PRD.md` existen; también las `PRD §N` de `src/`, `tests/`, READMEs y documentos.
- **V7:** `PRD-v2.1.md` §0.7 y `PLAN-MASTER.md` (D20, D21 y cierre §9.3) coinciden.
- **V8:** rangos de `[attachments]` (1–500, 1–1024, 1–500), módulos reales, manifiesto best-effort con versión, orden de precedencia de Δ§11.3, `--version`, detección de Outlook y línea de exits de la ayuda raíz tomada de `mailquery --help`.
- **Comentarios del código (2026-11-12, regla del dueño en `CLAUDE.md`):** los comentarios y docstrings de `src/`, `scripts/`, `pyproject.toml` y del workflow de CI ya no citan documentos, requisitos ni IDs de plan; solo describen el código (sin cambios de código, verificado por AST). Los tests automatizados conservan sus referencias.
- **Referencias externas:** las citas a `PRD-v2.1` en `tests/`, READMEs, `INTERFACES.md`, `config.example.toml`, `threat-model.md`, `PERFORMANCE-BACKLOG.md` y `PRD-v2.2.md` (antes `PRD-content-hardening.md`) apuntan ahora a `PRD.md` v2.1. `KNOWN-DEFECTS.md` mantiene el enlace al delta porque el comportamiento esperado de BUG-01 solo está en él.


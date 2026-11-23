# Trazabilidad

Solo el orquestador escribe este archivo, al cerrar cada milestone y cada lote.

## AC → milestone → tests

**Tabla: Matriz de trazabilidad de los criterios de aceptación**

| AC | Qué exige (resumen) | Milestones | Tests | Estado |
|---|---|---|---|---|
| AC-63 | uid `outlook:` + id corto, estable, resuelto; `EntryID`, mayúsculas, `-1`, `-02` ⇒ `E_USAGE` sin caché; macOS sin cambios y sin `cache.db` | M05, M06 | OL-31.01–.04, OL-32.01–.03, UT-UID-03.01, SMOKE-NEW.11 | 🟢 |
| AC-64 | `seq` 1 y 2 y sus uids, también en la misma consulta; parte estable en la ejecución; cada uid a su mensaje y a su directorio de adjuntos; `seq` 3 tras borrar el 2 | M01, M06 | UT-NID-03.02, .03, .07, .09; OL-34.01–.04 | 🟢 |
| AC-65 | Solo se registra lo impreso (`search`, `--group-by`, `new`, `--peek`); `--count` sin filas; sin mensajes no avisa; fallo del registro ⇒ sin mensajes ni estado | M03, M05 | UT-PL-06.01–.03, .05; OL-33.01–.06 | 🟢 |
| AC-66 | Ausente confirmado ⇒ no encontrado y fila borrada; cada causa de indeterminado conserva la fila; ninguna fila cambia de `native_id` | M06 | OL-35.01–.15 | ⚪ |
| AC-67 | Sin `short_id` ni `seq` en ninguna salida; claves de Windows iguales a las de macOS | M05 | OL-31.05 | 🟢 |
| AC-68 | `--show-native-id` en Windows y macOS; mismas claves y valores; el id nativo no es entrada; otros comandos ⇒ `E_USAGE`; forma nativa inválida ⇒ `E_PLUGIN_FAILED` | M03, M04, M06, M07 | UT-PL-06.08, UT-SNI-01.01–.08, OL-36.01–.03, OL-30 (barrido con la opción), DOC-16.01, SMOKE-NEW.11 | 🟢 |
| AC-69 | Cálculo `pmw3w06f5e`; `E_LOCKED`, `E_PERMISSION`, `E_IO` y sus versiones en un plugin; base vacía; hint de repetir la búsqueda; `show` sin base; permisos; columnas; `mailboxes`, `doctor` y `--version` no crean `cache.db` | M01, M03, M05, M06 | UT-NID-01.01, UT-NID-02.01–.08, UT-NID-04.01; UT-PL-05.05, .06; OL-31.06, OL-32.04–.07; OL-35.01 | 🟢 |
| AC-70 | Base abierta en el contexto del plugin, también en un gancho vigilado, sin ver otro driver; plugin sin ganchos igual; gancho > 30 s ⇒ `E_CLIENT_TIMEOUT` sin mensajes | M01, M03, M04 | UT-NID-04.02–.04; UT-PL-05.01–.03, .06; UT-PL-06.04, .06; UT-SNI-01.03 | 🟢 |

Puntos del checklist con test: CL-10 → OL-35 (M06); CL-09 → suite completa con `doc_14` y `doc_15` (F5 y conciliación); CL-06 y CL-11 → DOC-16.02 y .03 más las búsquedas de M07.

## Filas de conciliación → milestones

Todas las filas incluyen a M07 (documentos consumidores), así que ninguna está completa antes del lote 2. El orquestador las pasa a `implementado` en F4, en la rama de la unidad, después de integrar el lote 2, comprobando para cada fila que sus milestones están 🟢. Esta tabla es la única fuente: las secciones "Actualizaciones de la unidad" de los milestones la copian.

Hallazgo para RC-10 (lo añade el orquestador a su "Qué cambia" al cerrar M03, por la regla "Hallazgos" del protocolo de cambios): `backends/base.py` define la excepción de "no encontrado" con hint del driver, y `cli.py` da el home a los drivers internos y un contexto de plugin por driver, que cierra al terminar.

**Tabla: Filas de la tabla de conciliación por milestone**

| Fila | Contrato | Milestones | Estado en la unidad |
|---|---|---|---|
| RC-01 | Resumen del producto | M05, M06, M07 | pendiente |
| RC-02 | uid legado de Windows | M05, M07 | pendiente |
| RC-03 | Forma del `uid` de Outlook | M05, M07 | pendiente |
| RC-04 | Ejemplos de `show` con uid de Outlook | M05, M07 | pendiente |
| RC-05 | Ejemplo de invocación con uid de Outlook | M05, M07 | pendiente |
| RC-06 | Requisitos nuevos RF-80…RF-83 | M01, M03, M04, M05, M06, M07 | pendiente |
| RC-07 | Ayuda de `show` | M04, M07 | pendiente |
| RC-08 | Privacidad y permisos (RNF-05) | M01, M07 | pendiente |
| RC-09 | ADR-02 y ADR-50 | M01, M03, M05, M07 | pendiente |
| RC-10 | Módulos | M01, M03, M04, M05, M07 | pendiente |
| RC-11 | Árbol de fuentes y home | M01, M07 | pendiente |
| RC-12 | Orden total | M05, M07 | pendiente |
| RC-13 | Caché de ids nativos (estructuras) | M01, M07 | pendiente |
| RC-14 | Opciones de `show` | M04, M07 | pendiente |
| RC-15 | Validación del uid | M05, M06, M07 | pendiente |
| RC-16 | Errores `E_PERMISSION` y `E_IO` | M01, M05, M07 | pendiente |
| RC-17 | Mensaje movido de carpeta | M05, M07 | pendiente |
| RC-18 | Criterios de aceptación AC-63…AC-70 | M01, M03, M04, M05, M06, M07 | pendiente |
| RC-19 | Cambios visibles: opciones | M04, M07 | pendiente |
| RC-20 | Cambios visibles en Windows | M05, M07 | pendiente |
| RC-21 | Riesgos | M05, M06, M07 | pendiente |
| RC-22 | Problema | M05, M07 | pendiente |
| RC-23 | Validación de `attachment` | M06, M07 | pendiente |
| RC-24 | Privacidad (sin contenido de correos) | M01, M07 | pendiente |
| RC-25 | Desinstalación | M07 | pendiente |
| RC-26 | Contrato de plugin (RF-36) | M03, M04, M07 | pendiente |
| RC-27 | `show` no escribe (AC-07) | M05, M06, M07 | pendiente |
| RC-28 | Efectos de cada comando | M03, M05, M07 | pendiente |
| RC-29 | Lock ocupado | M01, M07 | pendiente |
| RC-30 | Ciclo de vida del plugin | M07 | pendiente |
| RC-31 | Versión en `develop` | M07 | pendiente |
| RC-32 | Formato de `--version` | M07 | pendiente |
| RC-33 | Versión mayor (ADR-27) | M07 | pendiente |
| RC-34 | Caché de adjuntos (RF-51) | M06, M07 | pendiente |
| RC-35 | `show` no escribe en disco (RF-41) | M05, M06, M07 | pendiente |
| RC-36 | Home de la app | M01, M07 | pendiente |
| RC-37 | Versión del paquete en la portada | M07 | pendiente |
| RC-38 | Flujo de `show` | M06, M07 | pendiente |

## Documentos consumidores → milestones

**Tabla: Documentos consumidores por milestone**

| Documento | Milestone | Estado en la unidad |
|---|---|---|
| `README.md` | M07 | actualizado |
| `README.es.md` | M07 | actualizado |
| `skills/mailquery/SKILL.md` | M07 | actualizado |
| `docs/INTERFACES.md` | M07 | actualizado |
| `docs/config.example.toml` | — | sin cambio |
| `docs/recipes/` | M07 | actualizado |
| `docs/security/` | M07 | actualizado |
| `docs/tests/` | Orquestador (F0, cierres de milestone, F5) | actualizado |

## Cambios en `docs/tests/` (F0)

Los escribe el orquestador en F0 con la marca `[pendiente]` (casos nuevos) o `[por actualizar]` (casos existentes), copiando las tablas de las secciones "Tests" de cada milestone.

**Tabla: Grupos nuevos del catálogo de pruebas**

| Grupo | Archivo de catálogo | Archivo de test | Milestone |
|---|---|---|---|
| UT-NID-01…UT-NID-04 (prefijo nuevo `UT-NID`) | `native-ids.md` (nuevo) | `tests/test_native_ids.py` | M01 |
| UT-PL-05, UT-PL-06 | `plugins.md` | `tests/test_plugins.py` | M03 |
| UT-SNI-01 (prefijo nuevo `UT-SNI`) | `cli-config.md` | `tests/test_show_native_id.py` | M04 |
| OL-31, OL-32, OL-33 | `outlook-runtime.md` | `tests/test_outlook.py` | M05 |
| UT-UID-03 | `state-backends.md` | `tests/test_uid.py` | M05 |
| OL-34, OL-35, OL-36 | `outlook-runtime.md` | `tests/test_outlook.py` | M06 |
| SMOKE-NEW.11 (caso nuevo; `Requisitos:` del grupo suma AC-63, AC-68 y AC-69) | `smoke.md` | `tests/test_smoke.py` | M06 |
| DOC-16 | `docs-packaging.md` | `tests/test_packaging.py` | M07 |

Casos existentes que pasan a `[por actualizar]`, con el texto nuevo de `Verifica` que da su milestone: OL-14.01, OL-23.01, OL-23.03, OL-25.01, UT-UID-01.05, UT-UID-02.03, UT-ATC-01.04 y TC-02.02–.06 y TC-09 (goldens de Outlook) en M05; OL-30 (barrido de opciones con `show --show-native-id`) en M06; TC-01.01 y TC-02.07 (versión en los goldens de `doctor`) en M07. Las tablas de casos se copian con su línea de título.

Otros cambios de F0: filas de `UT-NID` y `UT-SNI` en la tabla de prefijos de `TEST-CATALOG.md`; filas AC-63…AC-70 en `acceptance-matrix.md` con los casos de la primera tabla de este archivo. Los archivos de área quedan por debajo de 300 líneas (`outlook-runtime.md` pasa de 158 a unas 240).

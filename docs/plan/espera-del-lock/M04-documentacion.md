# M04 — Documentación

- **Unidad:** `docs/changes/espera-del-lock.md` (contribuye y no la completa sola).
- **Oleada / lote:** 2 / 1. **Rama del lote:** `feature/espera-del-lock-lote-1`. **Rama del milestone:** `feature/espera-del-lock-m04`, creada desde el tip de la rama del lote.
- **Commit base:** (te lo da el orquestador al lanzar; lo copias aquí en tu primer commit). **Línea base de la suite:** (te la da el orquestador al lanzar, con los fallos y saltos conocidos; la copias aquí).
- **Depende de:** M01 (`LockConfig` y la lectura de `[lock]`, ya integrados en la rama del lote). **Lo usan:** nadie. Corre en paralelo con M02.
- **ACs:** ninguno directo; cubre los documentos consumidores de la unidad.

## Objetivo

Los README, el archivo de configuración de ejemplo, el documento de interfaces y el modelo de amenazas describen el reintento del lock y la sección `[lock]` con sus valores por defecto.

## Alcance

- `README.md` y `README.es.md`, con el mismo contenido en los dos: sección `[lock]` con sus tres claves, valores por defecto, rangos y `retries = 0`; `[lock]` en la lista de secciones admitidas; `E_LOCKED` descrito como reintentos agotados en las tablas de errores y de reacción del harness; la línea `Lock:` si el README reproduce la ayuda raíz.
- `docs/config.example.toml`: sección `[lock]` con sus tres claves, valores por defecto y comentarios de rango, y `[lock]` en los comentarios que enumeran las secciones.
- `docs/INTERFACES.md`: `LockConfig`, `Config.lock` y la firma nueva de `RunLock` con su comportamiento.
- `docs/security/threat-model.md`: el efecto de varias sesiones pasa a ser el reintento del lock, con `E_LOCKED` solo al agotarse.
- Tests de documentación del grupo DOC-19.

## Fuera de alcance

- La ayuda raíz en `cli.py` (M03). `docs/tests/`, `docs/prd/` y la unidad (orquestador). `skills/mailquery/SKILL.md` y `docs/recipes/`: sin cambio.

## Alcance de escritura

`README.md`, `README.es.md`, `docs/config.example.toml`, `docs/INTERFACES.md`, `docs/security/threat-model.md`, `tests/test_integration.py`, este archivo, `docs/plan/espera-del-lock/work/M04-handoff.md`, `docs/plan/espera-del-lock/work/M04-propuestas.md`, `docs/plan/espera-del-lock/work/M04-evidencia.md`.

## Especificación

Rangos de `docs/changes/espera-del-lock.md` en el commit `e3670c7` (encabezado y líneas):

- "Requerimientos", RF-89 entero: 70-98.
- "Configuración": 100-111.
- "Interfaz de los módulos": 113-117.
- "Cambios visibles": 126-128.
- "Documentos consumidores": 181-195.
- "Checklist de conciliación", textos obsoletos y valores por defecto: 208 y 212.

## Puntos de entrada en el código

Commit `a1e0977`; si la línea se movió, búscala por el texto:

- `README.md`: lista de secciones (304), `### Content presentation ([content])` (354), chequeos de `doctor` (403-429), tabla de códigos de salida (963), caché de ids nativos (1038, no cambia), tabla de reacción del harness (1061). `README.es.md`: los bloques equivalentes.
- `docs/config.example.toml`: `url_display` (56), comentario final de secciones (119).
- `docs/INTERFACES.md`: `### state.py` (1140) con `RunLock(home)` (1174), `### config.py` (1178) con `ContentConfig` (1187, 1207). Archivo de 2717 líneas: se lee por rangos.
- `docs/security/threat-model.md`: "Varias sesiones" (151).
- `tests/test_integration.py`: `test_doc_06_01` (2203) y `test_doc_06_04` (2233), como modelo.

## Refactorizaciones previas

Ninguna.

## Decisiones aplicables

- **D-06.** `[lock]` va después de `[content]` allí donde se enumeran las secciones.

## Fases

**Tabla: Fases de M04**

| Fase | Tareas | Estado |
|---|---|---|
| 1 | Tests del grupo DOC-19, en rojo | ⚪ |
| 2 | `README.md` y `README.es.md` | ⚪ |
| 3 | `docs/config.example.toml`, `docs/INTERFACES.md` y `docs/security/threat-model.md` | ⚪ |
| 4 | Búsqueda de textos obsoletos, gates, datos crudos de evidencia y propuestas | ⚪ |

## Tests

Grupo nuevo `DOC-19 — Documentación del reintento del lock` en `tests/test_integration.py` (Requisitos: RF-89); definición en `docs/tests/docs-packaging.md`, detrás de DOC-18:

- **.01 P.** `README.md` y `README.es.md` documentan `[lock]` con `retries`, `initial_delay_ms` y `backoff_factor`, sus valores por defecto 5, 150 y 2, sus rangos y `retries = 0`.
- **.02 P.** `docs/config.example.toml` se lee con el cargador real, y su sección `[lock]` declara los valores por defecto de `LockConfig`.
- **.03 N.** Ni los README ni `docs/security/threat-model.md` describen `E_LOCKED` como rechazo inmediato del lock de ejecución ni "más `E_LOCKED`" como efecto de varias sesiones; `docs/INTERFACES.md` no describe el lock como no bloqueante.

Tests que cambian: `test_doc_06_02`, que limita las secciones documentadas en el ejemplo de configuración y debe admitir `lock`; y los de DOC-01, DOC-02 y DOC-03 que comparen textos que este milestone toca.

Comando: `python -B -m unittest discover -s tests -t . -k doc_19`.

## Documentación

La del alcance. `README.md` y `README.es.md` cambian en el mismo commit. Toda tabla o figura nueva lleva su título.

## Actualizaciones de la unidad

Propón al orquestador:

- Documentos consumidores `README.md`, `README.es.md`, `docs/INTERFACES.md`, `docs/config.example.toml`, `docs/security/threat-model.md` y `docs/tests/docs-packaging.md`: de `pendiente` a `actualizado`.
- Quitar `[pendiente]` de DOC-19 y `[por actualizar]` de DOC-06.02 en `docs/tests/docs-packaging.md`.
- Los valores por defecto tal como quedaron escritos en `README.md`, `README.es.md` y `docs/config.example.toml`, para la revisión cruzada del checklist.

## Gates

Los de `REGLAS.md`: suite completa, `-k doc_19`, `-k test_doc_`, `-k doc_14`, `-k doc_15`, `git diff --check`.

## Datos crudos de evidencia

Los de la sección "Evidencia cruda" de `REGLAS.md` (cobertura: "no aplica", no toca `src/`), más: el resultado de buscar los tres textos obsoletos en los cinco documentos del alcance.

## Definition of Done

- Los 3 casos de DOC-19 pasan solos y en la suite.
- La suite completa no tiene fallos nuevos frente a la línea base.
- `README.md` y `README.es.md` llevan el mismo contenido.
- Los valores por defecto son idénticos en los tres documentos que los muestran.
- `git diff --stat` solo muestra archivos del alcance de escritura.
- Fases en 🟢; `work/M04-propuestas.md` y `work/M04-evidencia.md` confirmados en la rama.

## Registro de progreso

**Tabla: Registro de progreso de M04**

| Fecha | Fase | Nota |
|---|---|---|

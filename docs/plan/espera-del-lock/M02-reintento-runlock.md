# M02 — Reintento en `RunLock`

- **Unidad:** `docs/changes/espera-del-lock.md` (contribuye y no la completa sola).
- **Oleada / lote:** 2 / 1. **Rama del lote:** `feature/espera-del-lock-lote-1`. **Rama del milestone:** `feature/espera-del-lock-m02`, creada desde el tip de la rama del lote.
- **Commit base:** (te lo da el orquestador al lanzar; lo copias aquí en tu primer commit). **Línea base de la suite:** (te la da el orquestador al lanzar, con los fallos y saltos conocidos; la copias aquí).
- **Depende de:** M01 (`mailquery.config.LockConfig`, ya integrado en la rama del lote). **Lo usan:** M03. Corre en paralelo con M04.
- **ACs:** AC-x1, las partes de pausas simuladas, `retries = 0` y `E_PERMISSION`, a nivel de `RunLock`.

## Objetivo

`RunLock.acquire()` reintenta tomar el lock con pausas crecientes según un `LockConfig` y falla con `E_LOCKED` al agotar los reintentos.

## Alcance

- La firma nueva de `RunLock` y el reintento de `acquire`, como fijan los rangos citados en "Especificación".
- La pausa en milisegundos se trunca a entero (D-09) y `sleep` recibe segundos (D-05).
- Interrupción durante una pausa: además de lo que fija la unidad, el descriptor queda cerrado.
- Docstrings de `RunLock` y `_lock_fd` acordes con el comportamiento nuevo.

## Fuera de alcance

- Lectura de `[lock]` (M01). Construcción del lock en los comandos y en `doctor` (M03). Documentos (M04).

## Alcance de escritura

`src/mailquery/state.py`, `tests/test_state.py`, este archivo, `docs/plan/espera-del-lock/work/M02-handoff.md`, `docs/plan/espera-del-lock/work/M02-propuestas.md`, `docs/plan/espera-del-lock/work/M02-evidencia.md`.

## Especificación

Rangos de `docs/changes/espera-del-lock.md` en el commit `<commit de referencia>` (encabezado y líneas):

- "Requerimientos", condiciones "Tope por pausa" (81) y "Primer intento" a "Orden" (86-93).
- "Interfaz de los módulos": 113-117.
- "Criterios de aceptación", AC-x1: 132.

## Puntos de entrada en el código

En `src/mailquery/state.py`, commit `a1e0977`; si la línea se movió, búscala por el nombre:

- `_lock_fd` (340), `_unlock_fd` (349), `RunLock` (357), `RunLock.acquire` (375), `RunLock.release` (407).
- En `tests/test_state.py`: `RunLockTest` (788).

## Refactorizaciones previas

- **Separar el intento de la apertura en `acquire`.** Hoy `acquire` abre el archivo e intenta el bloqueo en un solo cuerpo. Se extrae el intento de bloqueo a un método privado para que el bucle de reintentos lo envuelva sin duplicar la apertura ni el cierre del descriptor. No cambia el comportamiento: los 7 casos de UT-ST-01 siguen pasando sin tocarlos.

## Decisiones aplicables

- **D-05.** `sleep` recibe segundos, como `time.sleep`; los tests comparan las pausas en milisegundos enteros.
- **D-09.** "Sin decimales" es truncar: 12,5 ms pasa a 12 y 15,625 a 15. El producto se calcula de modo que un error de coma flotante no baje un valor exacto al entero anterior.

## Fases

**Tabla: Fases de M02**

| Fase | Tareas | Estado |
|---|---|---|
| 1 | Refactorización previa, con UT-ST-01 verde | ⚪ |
| 2 | Tests del grupo UT-ST-08, en rojo | ⚪ |
| 3 | Reintentos, pausas, `hint` e interrupción | ⚪ |
| 4 | Gates, datos crudos de evidencia y propuestas | ⚪ |

## Tests

Grupo nuevo `UT-ST-08 — Reintento del lock` en `tests/test_state.py` (Requisitos: RF-x1, AC-x1); definición en `docs/tests/state-backends.md`, detrás del último grupo UT-ST. El lock ocupado se consigue con otro `RunLock` sobre el mismo directorio; las pausas, con un `sleep` sustituido que las registra.

- **.01 P.** Lock libre: se toma en el primer intento y `sleep` no se llama.
- **.02 N.** Lock siempre ocupado y `LockConfig` por defecto: seis intentos, pausas de 150, 300, 600, 1200 y 2400 ms, y `E_LOCKED` con el `message` y el `hint` de reintentos agotados que fija la unidad, comparados literalmente con `5` y la ruta del lock.
- **.03 B.** `retries = 3`, `initial_delay_ms = 1000`, `backoff_factor = 3`: pausas de 1000, 3000 y 5000 ms.
- **.04 B.** `retries = 3`, `initial_delay_ms = 100`, `backoff_factor = 1.5`: pausas de 100, 150 y 225 ms.
- **.05 N.** `retries = 0`, y también sin `retry`: un solo intento, sin pausa, y `E_LOCKED` con el `hint` de "Sin reintentos", comparado literalmente.
- **.06 P.** Lock ocupado que se libera durante la segunda pausa: `acquire` lo toma en el siguiente intento y no hay más pausas.
- **.07 N.** El archivo del lock no se puede abrir: `E_PERMISSION` y `sleep` no se llama.
- **.08 N.** `sleep` lanza `KeyboardInterrupt`: se propaga, el lock no queda tomado y, al liberarlo su dueño, otro `RunLock` lo toma.
- **.09 B.** Pausas truncadas (D-09): `initial_delay_ms = 10` y `backoff_factor = 1.25` dan 10, 12 y 15 ms.

Tests que cambian: ninguno; UT-ST-01 se mantiene igual.

Comando: `python -B -m unittest discover -s tests -t . -k ut_st_08`.

## Documentación

Ninguna.

## Actualizaciones de la unidad

Ninguna fila ni documento consumidor queda completo con este milestone. Propón quitar `[pendiente]` de UT-ST-08 en `docs/tests/state-backends.md`.

## Gates

Los de `REGLAS.md`: suite completa, `-k ut_st_08`, `-k ut_st_01`, cobertura de `src/mailquery/state.py`, `git diff --check`.

## Datos crudos de evidencia

Los de la sección "Evidencia cruda" de `REGLAS.md`, más: el texto exacto de los dos `hint` de `E_LOCKED` y la lista de pausas observada en .02, .03, .04 y .09.

## Definition of Done

- Los 9 casos de UT-ST-08 y los 7 de UT-ST-01 pasan solos y en la suite.
- La suite completa no tiene fallos nuevos frente a la línea base.
- Ningún test de este milestone duerme de verdad.
- `git diff --stat` solo muestra archivos del alcance de escritura.
- Ningún comentario de `src/` cita IDs ni documentos.
- Fases en 🟢; `work/M02-propuestas.md` y `work/M02-evidencia.md` confirmados en la rama.

## Registro de progreso

**Tabla: Registro de progreso de M02**

| Fecha | Fase | Nota |
|---|---|---|

# M04 — Propuestas para documentos compartidos

## `docs/tests/docs-packaging.md`

- En la tabla "Casos de DOC-19", quitar el marcador `[pendiente]` de los casos .01, .02 y .03: los tres existen en `tests/test_integration.py` (`LockRetryDocumentationTest`) y pasan solos y en la suite completa. El texto de cada caso no cambia.
- En la tabla de DOC-06, quitar `[por actualizar]` del caso .02: `test_doc_06_02_scope_examples_with_and_without_driver_prefix` admite `lock` entre las secciones documentadas y pasa. El texto del caso no cambia.

## `docs/changes/espera-del-lock.md`

- "Documentos consumidores": `README.md`, `README.es.md`, `docs/INTERFACES.md`, `docs/config.example.toml` y `docs/security/threat-model.md` pasan de `pendiente` a `actualizado`. `docs/tests/docs-packaging.md` pasa a `actualizado` cuando el orquestador aplique la propuesta anterior.
- Para la revisión cruzada de CL-10, los valores por defecto quedaron escritos así:
  - `README.md` y `README.es.md`, bloque `toml` de la sección `[lock]`: `retries = 5` (`0..10`), `initial_delay_ms = 150` (`10..5000`), `backoff_factor = 2` (`1..10`); en la prosa, pausas de 150, 300, 600, 1.200 y 2.400 ms, 4,65 s en total, tope fijo de 5.000 ms.
  - `docs/config.example.toml`, bloque comentado `# [lock]`: `# retries = 5` (`0..10`), `# initial_delay_ms = 150` (`10..5000`), `# backoff_factor = 2` (`1..10`).
- Para CL-06: la búsqueda de los tres textos obsoletos en los cinco documentos del alcance no encuentra nada (detalle en `work/M04-evidencia.md`).

## Otros documentos compartidos

Ninguna.

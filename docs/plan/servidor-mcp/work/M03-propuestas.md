# M03 — propuestas

## Marcas de `docs/tests/`

- DOC-16.03, TC-01.01 y TC-02.07: implementados; quitar `[por actualizar]` cuando el orquestador aplique las marcas.

## Unidad

- RC-01, RC-16, RC-25 y RC-33: la versión `3.0.0a3` está en la rama; proponer su paso a `implementado` en la conciliación posterior, no en este trabajo.

## Desviaciones

Ninguna.

## Plan

- `tests/test_packaging.py` conserva `assertNotIn("3.0.0a2", text)` en DOC-16.03: es una aserción de ausencia, no una mención vigente.
- `docs/PERFORMANCE-BACKLOG.md` conserva la medición histórica con `3.0.0a2`; queda fuera del alcance de M03 y es un registro histórico.

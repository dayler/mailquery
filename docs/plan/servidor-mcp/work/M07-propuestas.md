# M07 — propuestas

## Marcas de `docs/tests/`

- SMOKE-MCP: los casos .01–.04, .06 y .07 se ejecutaron y pasaron en macOS con Apple Mail real; .05 se saltó con motivo (no se puede retirar el Acceso total al disco ni cerrar Outlook desde la suite). Proponer quitar `[pendiente]` a los ejecutados y dejar .05 con su motivo.

## Unidad

- Documentos consumidores `docs/tests/smoke.md` y `docs/tests/infrastructure.md` a `actualizado` cuando se apliquen las marcas.
- CL-10: el dueño lo verifica en F4; este milestone entrega el procedimiento.

## Desviaciones

Ninguna.

## Plan

- `SmokeMcpTest` reutiliza `SmokeTest.setUpClass` con `SmokeTest.setUpClass.__func__(cls)` y liga `_run`/`_store_counts` al `cls` nuevo; así no duplica la instalación con `pipx` ni cambia los casos existentes.
- SMOKE-MCP.06 usa un plugin que falla al consultar y acepta `E_PLUGIN_FAILED` o `E_CONFIG_ACCOUNT_UNKNOWN`, según cómo resuelva el entorno; se restaura el `config.toml` temporal al terminar.

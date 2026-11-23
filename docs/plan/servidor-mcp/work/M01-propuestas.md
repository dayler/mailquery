# M01 — propuestas

## Marcas de `docs/tests/`

Ninguna: este milestone no crea ni cambia casos con ID. El test de regresión no tiene ID y queda descrito en la evidencia.

## Unidad

Ninguna fila de conciliación ni documento consumidor cambia de estado por este milestone.

## Desviaciones

Ninguna.

## Plan

- La clave de `extra` que lleva el evento al formateador es `mailquery_event`; el valor es `{"fields": ((clave, valor), ...), "text": str | None, "traceback": str | None}`.
- `log_event` acepta `Logger` y `LoggerAdapter`; con el adaptador escribe por el logger subyacente con el `run_id` del adaptador mezclado con los datos del evento, sin depender de `merge_extra`.
- `setup_logging` emite su evento con el adaptador: en la base, a nivel `debug`, el registro no llegaba al archivo porque el `Logger` plano no tenía `run_id`; ahora la línea `logging initialized level=… max_size_mb=…` sí se escribe.

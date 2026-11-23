# M04 — propuestas

## Marcas de `docs/tests/`

- UT-CFG-05, UT-CFG-06, UT-LOG-05, UT-LOG-06 y DOC-18 implementados; quitar `[pendiente]` cuando el orquestador aplique las marcas.

## Unidad

- RC-07, RC-12, RC-13, RC-22, RC-27 y RC-28 a `implementado`; RC-20 queda para M06 (`docs/INTERFACES.md`); la parte de logs de RC-24 en M05.
- Documento consumidor `docs/config.example.toml` a `actualizado`; `docs/tests/cli-config.md` cuando se apliquen las marcas.
- Se propone para la conciliación posterior; no se aplica en este trabajo.

## Desviaciones

Ninguna.

## Plan

- `active_log_filename()` expone el nombre del archivo activo; `setup_logging(..., json=)` elige archivo y formateador.
- El `JsonFormatter` convierte los campos del evento: entero decimal a número, `true`/`false` a booleano (sin distinguir mayúsculas), `-` a `null` y el resto a texto; `message` siempre texto.
- Un `text` del evento con forma `clave=valor` se incorpora a `fields` (el caso de `event=start` sin campos adicionales); el texto libre va a `text`.
- El formateador solo se instala en el logger `mailquery`; los plugins conservan su logger y su archivo.
- `json = "yes"` u otro tipo dan `E_CONFIG_INVALID`; la ejecución deja el error en `mailquery.log` en texto con los valores por defecto.

---
aliases: ["Sección 14", "Logs"]
tags: [prd]
---

## 14. Logs

**Archivo:** `~/.mailquery/logs/mailquery.log` (permisos: RNF-05), en **texto plano**, o, con `[logging].json = true`, `~/.mailquery/logs/mailquery.jsonl` en **JSON Lines** (RF-88). Cuando el archivo activo supera `[logging].max_size_mb` (default 10 MB) se rota: pasa a `mailquery.log.1` (o `mailquery.jsonl.1`), los anteriores se desplazan y se conservan **5** archivos rotados; el más antiguo se borra. El tamaño máximo en disco de cada formato es, por tanto, unas 6 veces `max_size_mb`. Cada ejecución escribe solo en el archivo de su formato: el del otro formato, con sus rotados, no se modifica, no se rota ni se borra.
**Regla:** `stdout` es solo el JSON de datos; nada de logs en `stdout`. Además de las excepciones de texto de RF-16, `mcp serve` escribe en `stdout` el protocolo MCP (RF-84); ninguna escribe logs en `stdout`.

Formato de texto (estilo log4j):

```text
2026-11-02 02:15:00,123 INFO  mailquery.store run=abc123 strategy=live_ro version=V10 schema_ok=true
2026-11-02 02:15:00,214 INFO  mailquery.cli run=abc123 event=start command=search backend=apple_mail drivers=apple_mail
2026-11-02 02:15:00,427 INFO  mailquery.cli run=abc123 event=end command=search exit_code=0 count=1 truncated=False warnings=0 warning_codes=- mode=metadata candidates=1 messages_read=0 duration_ms=304
```

Formato JSON (`[logging].json = true`, RF-88): una línea por evento, cada una un único objeto JSON en UTF-8, con los mismos eventos, el mismo nivel y los mismos datos que el formato de texto.

- `ts`: fecha y hora local en ISO 8601 con milisegundos y desfase; `level`: `ERROR`, `WARNING`, `INFO` o `DEBUG`; `logger` y `run`.
- `fields`: un objeto con cada campo `clave=valor` del evento, con el mismo nombre y su valor completo. Un entero decimal es un número; `true` o `false`, en cualquier combinación de mayúsculas, un booleano; `-`, `null`; el resto, texto. `message` es siempre texto.
- `text`: el texto del evento que no tiene forma `clave=valor`, solo si existe; `traceback`: el de un `E_INTERNAL`, solo si existe.
- Si `config.toml` no se puede cargar, la ejecución escribe su error en `mailquery.log` en texto con los valores por defecto, aunque el archivo pida `json = true`.

La línea `event=start` del ejemplo anterior, en formato JSON:

```json
{"ts": "2026-11-02T02:15:00.214-04:00", "level": "INFO", "logger": "mailquery.cli", "run": "abc123", "fields": {"event": "start", "command": "search", "backend": "apple_mail", "drivers": "apple_mail"}}
```

- Niveles: `error`, `warning`, `info`, `debug` (§15.1).
- Se registran: comando, backend (driver nativo), drivers declarados, estrategia de conexión, versión del store o del cliente, conteos, duración, número de warnings y sus códigos `W_*` (sin el detalle), y errores (`code` + mensaje).
- **Nunca** se registran asuntos, cuerpos, direcciones, nombres de personas, nombres originales o sanitizados de adjuntos, carpetas o cuentas, etiquetas de cuenta, rutas, términos de búsqueda ni identificadores de mensajes o stores (uids, `EntryID`, `StoreID`); si el mensaje de un error los contiene, se omiten al escribirlo en el log.
- Un error inesperado (`E_INTERNAL`) registra además su traceback.

Plugins y `attachment`:

- `event=start`: `command=... backend=<driver nativo> drivers=<lista declarada separada por comas>`. `backend` es siempre el driver nativo; `drivers` es el conjunto declarado, que puede diferir (p. ej. solo un plugin declarado en macOS).
- `event=end` de `attachment` (solo en éxito; en fallo se registra `event=error` y no se emite `end`): `event=end command=attachment exit_code=0 count=<N> cached=<M> bytes=<total> duration_ms=<ms>`.
- El `log_message` de un plugin se sanea (controles, 200 bytes) y se registra en lugar del `message` si está presente; el núcleo no registra nunca `hint` ni `detail` de plugin con datos personales.
- El log de un plugin (`~/.mailquery/logs/<driver>.log`) es opcional y propiedad del plugin: el núcleo no lo escribe, no lo rota ni lo lee. El plugin debe aplicar la misma política de privacidad (sin uids, nombres, rutas, cuentas ni secretos).
- Un `E_INTERNAL` registra traceback; un fallo de plugin se registra en nivel `error` con `code` y `log_message` saneado.

`mcp serve`:

- El servidor registra `event=start command=mcp` al arrancar, una línea `event=call tool=<herramienta> exit_code=<n> duration_ms=<ms>` por llamada, sin parámetros ni valores, y `event=end` al terminar (RF-84). No mantiene abierto el archivo entre dos eventos, y un fallo al escribir el log no llega a `stdout` ni a `stderr`.
- Cada proceso hijo registra su propia ejecución como cualquier comando, en el archivo de su formato.

---


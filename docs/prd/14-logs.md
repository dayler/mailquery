---
aliases: ["Sección 14", "Logs"]
tags: [prd]
---

## 14. Logs

**Archivo:** `~/.mailquery/logs/mailquery.log` (permisos: RNF-05), en **texto plano**. Cuando supera `[logging].max_size_mb` (default 10 MB) se rota: pasa a `mailquery.log.1`, los anteriores se desplazan y se conservan **5** archivos rotados; el más antiguo se borra. El tamaño máximo en disco es, por tanto, unas 6 veces `max_size_mb`.
**Regla:** `stdout` es solo el JSON de datos; nada de logs en `stdout`.

Formato (estilo log4j):

```text
2026-11-02 02:15:00,123 INFO  mailquery.store run=abc123 strategy=live_ro version=V10 schema_ok=true
2026-11-02 02:15:00,214 INFO  mailquery.cli run=abc123 event=start command=search backend=apple_mail drivers=apple_mail
2026-11-02 02:15:00,427 INFO  mailquery.cli run=abc123 event=end command=search exit_code=0 count=1 truncated=False warnings=0 warning_codes=- mode=metadata candidates=1 messages_read=0 duration_ms=304
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

---


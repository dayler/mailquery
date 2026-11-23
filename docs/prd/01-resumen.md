---
aliases: ["Sección 1", "Resumen ejecutivo"]
tags: [prd]
---

## 1. Resumen ejecutivo

`mailquery` es una utilidad de línea de comandos, escrita en Python, que lee el almacén local del cliente de correo de escritorio **sin modificar absolutamente nada**: no marca correos como leídos, no edita, no mueve, no borra y no cambia flags. Soporta dos plataformas mediante **backends** intercambiables:

**Tabla: Plataformas, clientes y forma de lectura**

| Plataforma | Cliente | Cómo lee |
|------------|---------|----------|
| macOS | Apple Mail | `Envelope Index` (SQLite read-only) + `.emlx` |
| Windows | Outlook clásico (16.0) | Outlook Object Model por COM, detrás de un proxy de solo lectura |

Toda su configuración, estado y logs viven en `~/.mailquery`; el repositorio del proyecto solo contiene código y documentación.

Devuelve **siempre un objeto JSON** por ejecución (no existe `--format`), con el **mismo contrato en ambas plataformas** (misma forma; las diferencias de valor están en §11.3 y §12.5), pensado para que un harness de agentes lo consuma bajo demanda: resúmenes de correo nuevo, búsquedas por asunto/contenido/remitentes/fechas, seguimiento de remitentes y reportes. Solo lee las cuentas declaradas en `~/.mailquery/config.toml` (alcance: §15).

Es deliberadamente pequeño: sin demonio, sin programador interno, sin base de datos propia de mensajes y sin red en el núcleo ni en los backends internos (un plugin externo puede usarla si lo declara, §4). La única fuente de verdad es el cliente de correo local, leído en modo estrictamente read-only.

Desde la versión 3.0.0 añade dos capacidades:

1. **Plugins de backend (`<driver>:`).**
   - El núcleo descubre backends por el entry point group `mailquery.backends`; los backends internos (`apple_mail`, `outlook`) se registran por la misma vía y cualquier plugin externo usa el mismo contrato. El registro funciona también en modo desarrollo sin instalación.
   - Cada plugin declara `driver` (`[a-z0-9_]{1,64}`, único), `plugin_api = 1` y un mapa de capacidades (`network`, `readonly`, `body_local`, `attachments`, `native_order`).
   - En `~/.mailquery/config.toml` las cuentas se declaran como `[scope."<driver>:<cuenta>"]`; si se omite `<driver>:`, aplica el driver nativo del SO (`apple_mail` en macOS, `outlook` en Windows).
   - Todo `uid` es un `string` opaco `"<driver>:<native_id>"`; el núcleo separa el prefijo y el plugin solo ve su `<native_id>` limpio. Esto da rutas de caché deterministas y routing `O(1)` en `show` y `attachment`, sin bloques `"backend"`/`"driver"` en el JSON.
   - La configuración y el log de un plugin externo son **opcionales**: si existen, viven en `~/.mailquery/<driver>.toml` y `~/.mailquery/logs/<driver>.log`, los gestiona el plugin y el núcleo no los lee ni los rota.
2. **Recuperación local de adjuntos (`mailquery attachment`).**
   - `mailquery attachment <uid> (--index N | --all) [--force]` recupera los adjuntos ya presentes en el store local hacia `~/.mailquery/attachments/<driver>/<native_id>/<sanitized_name>` (`sanitized_name` ya incluye el prefijo `<index:02d>_`; directorios `0700`, archivos `0600` en POSIX) y devuelve ruta, nombres, tamaño y SHA-256.
   - El bloqueo es **del mensaje completo**: si cualquier adjunto tiene nombre hostil, extensión peligrosa o contenido ejecutable, no se escribe **ningún** archivo del mensaje, ni con `--index` ni con `--all`, y el comando falla con `E_ATTACHMENT_BLOCKED` (exit 4). No hay extracción parcial; el mensaje entero se considera no confiable.
   - Si el adjunto no puede recuperarse, falla con `E_ATTACHMENT_UNAVAILABLE` (exit 3) y un motivo (`not_local`, `unsupported`, `network`, ...); si está corrupto o es S/MIME, con `E_ATTACHMENT_UNREADABLE` (exit 3).
   - El núcleo aplica sanitización determinista del nombre (`sanitized_name`: nombre final con el prefijo `NN_`, ≤ 153 bytes UTF-8; el nombre sin prefijo (raíz + extensión), ≤ 150 bytes), límites de `[attachments]` y escritura atómica vía staging en `~/.mailquery/tmp/`.
   - La caché es **efímera y best-effort**: su limpieza la hace un cron externo; la aplicación no barre la caché ni la valida al arrancar; solo verifica contra el manifiesto del mensaje los archivos que va a servir (§10.3.4).

En 3.0.0 también endurece el contenido no confiable (F1), corrige la recuperación de adjuntos de los drivers remotos (F2) y adapta la salida a lo que pide el harness (F3).

**F1 — Endurecimiento del contenido no confiable.**

**Principio.** `mailquery` no sustituye al cliente de correo (Apple Mail, Outlook) ni muestra correos a nadie: da al harness una forma de leer el correo y procesarlo tan seguro como se pueda. Por eso entrega **lo que recibió el destinatario**, el texto que él vería en su cliente y no un canal paralelo, **sin los caracteres y bloques que solo sirven para esconder contenido**, y **con señales** para que el harness aplique su política. Lo que `mailquery` no puede resolver queda documentado en el [anexo de seguridad](../security/threat-model.md).

El correo es contenido **no confiable** y el harness lo entrega al LLM. F1 **deja de transportar contenido engañoso** y **da al harness señales explícitas** con las opciones A2–A7 del [anexo de seguridad](../security/threat-model.md); A1 (frontera de confianza) es ese anexo con el ADR-28. Lo que F1 no cambia: RF-64.

1. **A2 — Saneado del texto:** elimina ANSI, controles C0/C1, DEL, los caracteres de formato Unicode (`Cf`: RLO, bidi, zero-width, *tag characters*) y otros invisibles que sirven para esconder datos (selectores de variación, rellenos Hangul) de todos los campos de contenido del correo y de los textos de warnings y errores. Los identificadores que el usuario reutiliza no se alteran. La búsqueda ignora esos mismos caracteres, así que lo que se muestra se puede buscar.
2. **A3 — Cuerpo visible:** el cuerpo sale del HTML cuando el mensaje lo tiene, que es lo que ve el destinatario en su cliente, y no del texto plano alternativo. Las hojas `<style>` del mensaje se pasan a estilos en línea con `css-inline` y la conversión HTML → texto omite los elementos ocultos por el atributo `hidden` o por `display:none`/`visibility:hidden`. El warning `W_HIDDEN_CONTENT` dice cuántos caracteres se omitieron, sin el texto. Así el harness procesa lo mismo que ve el destinatario y sabe que había contenido oculto; decidir qué hacer con ese mensaje es suyo.
3. **A4 — Visualización de URLs:** `neutralize` por defecto (la URL se lee pero no queda lista para abrirse, p. ej. `http` → `hxxp`), `keep` (el texto exacto) o `strip` (`[link omitted]`), por configuración o con `--strip-links`, en el asunto, los nombres, `headers` y el cuerpo; `neutralize` además acorta las URLs gigantes. No se resuelven URLs (RF-54).
4. **A5 — Señales de enlaces:** warnings por mensaje, con el `uid` y sin URL ni dominio: `W_EXTERNAL_LINKS` (enlaces del asunto, los nombres y el cuerpo), `W_NON_ASCII_DOMAIN` (dominios no ASCII en URLs y direcciones, contra los homoglifos; `neutralize` los escribe en punycode), `W_SCRIPT_LINK` (`javascript:`, `vbscript:`, `data:`) y `W_LONG_URL` (más de 2.048 caracteres).
5. **A6 — Señales del remitente:** `W_SENDER_AUTH_FAILED` repite el veredicto de SPF, DKIM o DMARC que el proveedor dejó en `Authentication-Results` cuando alguno falla, y `W_REPLY_TO_MISMATCH` avisa cuando las respuestas irían a otro dominio que el del remitente. `mailquery` no verifica nada por su cuenta (no hay red): solo repite lo que el proveedor ya calculó.
6. **A7 — Contenido activo en adjuntos:** al extraer con `attachment`, `W_ATTACHMENT_ACTIVE_CONTENT` avisa de un PDF con JavaScript o `/Launch`, un documento de Office con macros o un ZIP con un ejecutable dentro, sin abrir, ejecutar ni descomprimir el archivo. El archivo se entrega igual: decide el harness.

Además, cada respuesta de éxito de `search`, `new`, `show` y `attachment` lleva un aviso fijo (`content_notice`) que recuerda que el contenido no es confiable, y la skill y los README explican las reglas para el agente y los controles para quien opera el harness (RF-66).

Nada de esto convierte al correo en contenido "seguro": la inyección de prompt, la apertura de URLs y la ejecución de archivos siguen siendo responsabilidad del harness y del OS (anexo de seguridad, ADR-28).

**F2 — Corrección de defectos.**

1. **Adjuntos de drivers remotos (BUG-01 de [`KNOWN-DEFECTS.md`](../KNOWN-DEFECTS.md)):** `attachment` extrae los adjuntos de un plugin con `attachments: "remote"`, que obtiene los bytes desde su origen con su propia red (ADR-22). El núcleo no abre red y trata esos bytes igual que los de un driver local: bloqueo, límites, SHA-256, caché, manifiesto y, con F1, `W_ATTACHMENT_ACTIVE_CONTENT`.
2. **Tope de extracción:** el tope por adjunto es `[attachments].timeout_seconds`, 60 s por defecto, para todos los drivers. En un plugin externo es un corte duro: un plugin que se queda esperando la red no deja `attachment` colgado.

**F3 — Salida a medida de `search`, `new`, `show`, `doctor` y `mailboxes`.**

F3 hace que lo barato sea lo que sale por defecto y añade formas de pedir solo lo necesario:

1. **Fila mínima por defecto:** `search` y `new` devuelven `uid`, `subject`, `from`, `date_received`, `is_read` y `has_attachments`, sin leer el cuerpo.
2. **`--fields`:** en `search` y `new` añade campos a la fila mínima (`--fields snippet`, `--fields all`); en `show` elige los campos que se devuelven (`show <uid> --fields attachments`).
3. **`--group-by`:** `search` agrupa los resultados por remitente, dominio, carpeta, cuenta, día, semana o mes (hasta dos claves) y devuelve los últimos mensajes de cada grupo.
4. **`--count`:** `search` devuelve solo el número de mensajes.
5. **`doctor --failures`:** `doctor` muestra solo los chequeos que fallan.
6. **Sin *preflight*:** la skill no ejecuta `doctor` ni `mailboxes` antes de usar `mailquery` y diagnostica a partir de los errores; un `search` sin resultados dice en `hint` cuántas carpetas y cuentas buscó y cómo ampliar el alcance.
7. **`mailboxes` agrupado:** cada cuenta lista sus carpetas una vez, solo con `path` e `included`; el nombre, la URL y los contadores se piden con `--fields`, y sin contadores no se cuenta ningún mensaje.
8. **Plugins en `doctor`:** `doctor` muestra en una sección propia los chequeos de cada plugin declarado y si sus cuentas y carpetas resuelven, también con `--failures`.

`new` y `search --unread` se mantienen (ADR-45).

**Id corto de mensaje en Outlook.**

1. **`uid` corto:** en Windows el `uid` es `outlook:` más un id corto de 10 caracteres, en lugar de los 140 del `EntryID` (RF-81).
2. **Caché de ids nativos:** `~/.mailquery/db/cache.db` relaciona cada id corto impreso con su id nativo. El núcleo ofrece la librería y cada driver decide si la usa (RF-80, RF-82).
3. **`--show-native-id`:** opción de depuración de `show`, que muestra el id nativo en lugar del id corto (RF-83).

---


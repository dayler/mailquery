---
aliases: ["Glosario", "Anexo F"]
tags: [prd, glosario]
---

# Glosario

Términos del PRD. Dentro de cada grupo, en orden alfabético.

## Términos generales

### Alcance

Cuentas declaradas en config y carpetas que se leen (INBOX siempre dentro de cada cuenta declarada); si no hay cuentas declaradas, el alcance está vacío.

### Backend / driver

Implementación de la interfaz de backend (§9.2) para un origen de correo concreto: `apple_mail`, `outlook` o un plugin externo.

### Caché de ids nativos (`cache.db`)

Base SQLite de `~/.mailquery` que relaciona cada id corto impreso con su `native_id`.

### Cursor

Marca de agua `(fecha de recepción, uid)` que da a `new` su semántica de procesamiento único.

### Herramienta MCP

Cada comando que el servidor MCP expone (`search`, `new`, `show`, `attachment`, `mailboxes`, `doctor`), con un parámetro por opción del comando (RF-85).

### Id corto

Alias de un `native_id` largo: el principio de la codificación en base32 de su `SHA-256`, sin sufijo. En Outlook tiene 10 caracteres. Con el sufijo `-<seq>`, que llevan desde el segundo `native_id` del mismo driver con el mismo id corto, forma la parte del `uid` posterior al prefijo (RF-80, RF-81).

### Manifiesto (`.manifest.json`)

Registro SHA-256 por mensaje que valida los aciertos de la caché de adjuntos (§10.3.4).

### Plugin

Paquete de terceros registrado en `mailquery.backends` que implementa `plugin_api = 1` y declara sus capacidades (RF-33, RF-36).

### Precepto/receta

Regla que el usuario define para una tarea del harness; vive en `docs/recipes/`, no en la app.

### Reintento del lock

Nuevo intento de tomar el lock de ejecución que un comando de datos hace, tras una pausa creciente, cuando lo encuentra ocupado; el número de reintentos y las pausas se configuran en `[lock]` (RF-89).

### `sanitized_name`

Nombre seguro, determinista e idempotente de un adjunto en la caché, con el prefijo `<index:02d>_` (§10.3.3).

### Servidor MCP

Proceso `mailquery mcp serve` que lanza el harness para usar los comandos de `mailquery` como herramientas MCP por stdin y stdout; ejecuta cada llamada como una invocación de la CLI (RF-84, RF-86).

### Snippet

Extracto de 200 caracteres del cuerpo que `search` y `new` incluyen con `--fields snippet` (RF-68).

### uid

Identificador opaco de un mensaje devuelto por `search`/`new` y aceptado por `show`/`attachment`; string `"<driver>:<native_id>"` en todas las plataformas.

## Términos de los backends

### `.emlx` / `.partial.emlx`

Archivo por mensaje de Apple Mail; `partial` indica adjuntos externalizados.

### EntryID / StoreID

Identificadores (en hex) de un item y de un store dentro del perfil de Outlook.

### Envelope Index

Base SQLite de metadatos de Apple Mail.

### Modo caché (Cached Exchange Mode)

Outlook mantiene una copia local del buzón y lee de ella sin ir al servidor.

### Object Model Guard

Protección de Outlook que avisa cuando un programa externo accede a datos sensibles por COM.

### OST / PST

Archivos de datos de Outlook; OST = caché local de una cuenta de servidor, PST = archivo de datos local.

### TCC / Full Disk Access (FDA)

Control de privacidad de macOS que protege `~/Library/Mail`.

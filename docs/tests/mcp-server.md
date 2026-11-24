# Servidor MCP

#### UT-MCP-01 — Transporte y mensajes JSON-RPC

Requisitos: RF-84, AC-71 · Archivo: `tests/test_mcp_server.py`

**Tabla: Casos de UT-MCP-01**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Cada respuesta es un único objeto JSON-RPC 2.0 en una línea UTF-8 terminada en `\n`; nada más llega a stdout. |
| .02 | P | Una línea terminada en `\r\n` se atiende igual que la misma línea terminada en `\n`. |
| .03 | N | Una línea que no es JSON, o que no es UTF-8 válido ⇒ error `-32700` con `id` `null`; la sesión sigue atendiendo la línea siguiente. |
| .04 | N | Una petición sin `method` ⇒ `-32600`; un array vacío ⇒ `-32600` con `id` `null`. |
| .05 | N | Un método desconocido ⇒ `-32601` con el `id` de la petición. |
| .06 | P | Un lote con dos peticiones ⇒ un array con sus dos respuestas en orden; un lote solo de notificaciones ⇒ ninguna respuesta; un elemento que no es objeto ⇒ `-32600` dentro del array. |
| .07 | P | `notifications/initialized`, `notifications/cancelled` y una notificación desconocida ⇒ ninguna respuesta. |
| .08 | P | `tools/list` antes de `initialize` ⇒ la misma respuesta que después. |
| .09 | P | Con los flujos que arma la CLI sobre bytes, cada línea escrita termina en `\n` sin `\r` en todas las plataformas. |

#### UT-MCP-02 — `initialize` y `ping`

Requisitos: RF-84, AC-71 · Archivo: `tests/test_mcp_server.py`

**Tabla: Casos de UT-MCP-02**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `initialize` ⇒ `serverInfo` `{"name": "mailquery", "version": __version__}` y `capabilities.tools` sin `listChanged`. |
| .02 | P | Pedida cada una de `2024-11-05`, `2025-03-26`, `2025-06-18` y `2025-11-25` ⇒ `protocolVersion` igual a la pedida. |
| .03 | B | Pedida una versión no soportada, o ninguna ⇒ `2025-11-25`. |
| .04 | P | `ping` ⇒ resultado `{}`. |
| .05 | P | El contenido de `tools/list` y de `tools/call` es el mismo con cualquier versión negociada. |

#### UT-MCP-03 — Herramientas de `tools/list`

Requisitos: RF-85, AC-71 · Archivo: `tests/test_mcp_server.py`

**Tabla: Casos de UT-MCP-03**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Exactamente `search`, `new`, `show`, `attachment`, `mailboxes` y `doctor`, en ese orden; ninguna para `mcp` ni para `--version`. |
| .02 | P | La `description` de cada herramienta es la de su subcomando y la de cada parámetro, el `help` de su opción. |
| .03 | P | Cada opción larga es un parámetro sin guiones y con `_`: `include_mailbox`, `has_attachments`, `strip_links`, `group_by`, `from`. |
| .04 | P | Tipos: indicador ⇒ `boolean`; `limit` ⇒ `integer`; `index` de `attachment` ⇒ `integer`; opción repetible o con lista ⇒ `array` de `string`; una opción con `choices` ⇒ `string` con `enum`; el resto ⇒ `string`. |
| .05 | P | `log_level` está en todas las herramientas, opcional, `string` con el `enum` de `--log-level`. |
| .06 | N | `doctor` no tiene `json`; `show` no tiene `show_native_id`; ninguna tiene `help`. |
| .07 | P | `uid` es obligatorio en `show` y `attachment`; todas las herramientas tienen `additionalProperties: false`. |
| .08 | P | Una opción nueva añadida a un parser de prueba aparece en su herramienta sin otro cambio. |

#### UT-MCP-04 — Argumentos de la CLI

Requisitos: RF-85, RF-86, AC-72, AC-73 · Archivo: `tests/test_mcp_server.py`

**Tabla: Casos de UT-MCP-04**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | El ejecutor recibe `[<intérprete>, "-P", "-m", "mailquery", …]` con el intérprete del servidor. |
| .02 | P | `log_level` va antes del comando (`--log-level=debug search …`). |
| .03 | P | Cada valor va como `--opción=valor`; un `array` da una opción por elemento; `true` da el indicador y `false` lo omite. |
| .04 | P | `uid` va al final, detrás de `--`. |
| .05 | P | `doctor` lleva siempre `--json`; con `failures: true`, también `--failures`. |
| .06 | P | `search` con `{"since": "1w", "unread": true, "fields": ["snippet"]}` ⇒ `search --since=1w --unread --fields=snippet`. |
| .07 | B | `subject` con un valor que empieza por `-` llega como `--subject=<valor>`. |
| .08 | P | `attachment` con `index: 2` ⇒ `--index=2` y el `uid` detrás de `--`. |

#### UT-MCP-05 — Resultado de una llamada

Requisitos: RF-86, AC-72, AC-74 · Archivo: `tests/test_mcp_server.py`

**Tabla: Casos de UT-MCP-05**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Exit 0 ⇒ un único bloque `text` con la salida estándar sin el salto final e `isError: false`. |
| .02 | P | Exit distinto de 0 ⇒ el mismo texto e `isError: true`. |
| .03 | N | Salida vacía, que no es JSON, con dos objetos o con un array ⇒ `E_INTERNAL` con `message` `the command did not write a JSON object`, `hint` ``run `mailquery doctor` and check the mailquery log``, `command` igual a la herramienta e `isError: true`. |
| .04 | N | Un proceso hijo que no se puede lanzar ⇒ el mismo `E_INTERNAL`. |
| .05 | P | Tras un `E_INTERNAL`, la llamada siguiente se atiende con normalidad. |
| .06 | P | El JSON de `E_INTERNAL` tiene las claves, el orden y el formato del JSON de error de la CLI. |
| .07 | P | El ejecutor real lanza el argv sin shell, con stdin vacío, stderr descartado, el entorno y el directorio de trabajo del servidor y, en Windows, sin ventana de consola (con el lanzamiento de procesos sustituido). |

#### UT-MCP-06 — Validación previa

Requisitos: RF-86, AC-73 · Archivo: `tests/test_mcp_server.py`

**Tabla: Casos de UT-MCP-06**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Un parámetro desconocido ⇒ `E_USAGE` con `command` igual a la herramienta, un `hint` que nombra el parámetro e `isError: true`, sin llamar al ejecutor. |
| .02 | N | Un `integer` con texto, un `boolean` con texto o un `array` con un elemento que no es texto ⇒ el mismo resultado. |
| .03 | N | `show` o `attachment` sin `uid` ⇒ el mismo resultado. |
| .04 | N | `show` con `show_native_id` ⇒ el mismo resultado. |
| .05 | N | Un valor con el carácter NUL ⇒ el mismo resultado. |
| .06 | B | Un argv que supera el límite de longitud de la plataforma ⇒ el mismo resultado, con el `hint` del parámetro más largo (también `uid`). |
| .07 | N | `tools/call` con una herramienta que no está en `tools/list` ⇒ error JSON-RPC `-32602`. |
| .08 | P | El JSON de `E_USAGE` tiene las claves, el orden y el formato del JSON de error de la CLI. |

#### UT-MCP-07 — Llamadas en serie y cierre

Requisitos: RF-84, RF-86, AC-74 · Archivo: `tests/test_mcp_server.py`

**Tabla: Casos de UT-MCP-07**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Dos peticiones escritas seguidas ⇒ respuestas en orden, y la segunda ejecución empieza después de que termina la primera. |
| .02 | P | `ping` y `tools/list` escritos durante una llamada responden después de ella. |
| .03 | P | Fin de stdin con una llamada en curso ⇒ la llamada se responde y `serve` devuelve 0. |
| .04 | N | Durante la sesión no se escribe nada en stderr. |

#### UT-MCP-08 — Dependencias e importaciones

Requisitos: RF-84, AC-76 · Archivo: `tests/test_mcp_server.py`

**Tabla: Casos de UT-MCP-08**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `mcp_server.py` solo importa módulos de la biblioteca estándar y de `mailquery`. |
| .02 | P | `[project].dependencies` de `pyproject.toml` es exactamente la lista de la línea base. |
| .03 | N | Importar `mcp_server` y generar las herramientas no carga entry points ni instancia drivers. |

#### UT-MCP-09 — Servidor real

Requisitos: RF-84, RF-86, AC-71, AC-72, AC-74 · Archivo: `tests/test_mcp_server.py`

**Tabla: Casos de UT-MCP-09**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Sin `config.toml`, `mailquery mcp serve` responde a `initialize` y a `tools/list`. |
| .02 | P | Con un `config.toml` inválido, arranca y responde a `tools/list`; una llamada devuelve `E_CONFIG_INVALID` con `isError: true`; tras corregir el archivo, la llamada siguiente ya no lo devuelve, sin reiniciar. |
| .03 | P | `search` con `{"since": "bogus"}` ⇒ el mismo JSON que `mailquery search --since=bogus` (salvo `generated_at`) con `isError: true`, también con un `json.py` en el directorio de trabajo del servidor. |
| .04 | P | Al cerrar stdin con una llamada en curso, el servidor la responde y sale con exit 0; su stderr queda vacío. |
| .05 | P | Cada línea de la salida estándar del proceso termina en `\n` sin `\r`, también en Windows. |
| .06 | N | `attachment` con `index` y `all` a la vez ⇒ el mismo JSON `E_USAGE` que la CLI con `--index` y `--all`, con `isError: true`: las reglas entre opciones las valida el proceso hijo. |
| .07 | P | Dos servidores lanzados a la vez con el mismo HOME responden cada uno a `tools/list` y a una llamada, sin interferir. |

#### UT-MCP-10 — Plugin que no carga

Requisitos: RF-84, AC-76 · Archivo: `tests/test_mcp_server.py`

**Tabla: Casos de UT-MCP-10**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con un plugin instalado cuya carga falla, el servidor responde a `initialize` y a `tools/list`. |

#### UT-MCP-11 — Log del servidor

Requisitos: RF-84, RF-88, AC-75 · Archivo: `tests/test_mcp_server.py`

**Tabla: Casos de UT-MCP-11**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | El log tiene `event=start command=mcp`, una línea `event=call` por llamada con `tool`, `exit_code` y `duration_ms`, y `event=end` al cerrar stdin. |
| .02 | N | Ninguna línea del servidor contiene los valores de los parámetros de una llamada. |
| .03 | P | Entre dos eventos, el archivo de log del servidor no está abierto: se puede renombrar y borrar, también en Windows. |
| .04 | P | `--log-level` antes de `mcp` fija el nivel del log del servidor; con `[logging].json = true`, los eventos del servidor van a `mailquery.jsonl`; un cambio de `[logging]` durante la sesión no cambia el log del servidor, que lee la tabla una vez al arrancar. |
| .05 | N | Un fallo al escribir el log del servidor no escribe en stdout ni en stderr y el servidor sigue respondiendo. |

#### UT-MCP-12 — Rotación con el servidor en marcha

Requisitos: RF-84, RF-88, AC-78 · Archivo: `tests/test_mcp_server.py`

**Tabla: Casos de UT-MCP-12**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | B | Formato de texto, `max_size_mb = 1` y `mailquery.log` precargado justo por debajo del tope: la llamada siguiente rota sin errores, aparece `mailquery.log.1` y la línea `event=call` está en el `mailquery.log` nuevo. |
| .02 | B | Lo mismo con `[logging].json = true`, `mailquery.jsonl` y `mailquery.jsonl.1`. |

#### UT-MCP-13 — Lock ocupado en una llamada MCP

Requisitos: RF-89, AC-79, AC-80 · Archivo: `tests/test_mcp_server.py`

**Tabla: Casos de UT-MCP-13**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | [pendiente] Lock retenido 2 s por otro proceso, sin `[lock]`: `tools/call` de `search` devuelve el resultado de la CLI con `isError: false` y una sola ejecución del comando. |
| .02 | N | [pendiente] `[lock] retries = 11`: `mailquery mcp serve` arranca, y una llamada a `search` devuelve `E_CONFIG_INVALID` con `isError: true`. |

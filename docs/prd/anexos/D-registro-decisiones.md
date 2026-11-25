---
aliases: ["Anexo D", "Registro de decisiones"]
tags: [prd]
---

### Anexo D — Registro de decisiones

**Tabla: Registro de decisiones**

| Pregunta original | Decisión |
|-------------------|----------|
| ¿Nombres visibles de cuenta? | Etiqueta legible resuelta en solo lectura; UUID como fallback (§15.2). |
| ¿Búsqueda de contenido sin filtros? | No (§22.1). |
| ¿Salida markdown? | No: solo JSON (ADR-04). |
| ¿Retención de logs? | Rotación por tamaño en lugar de diaria (§14; 2026-11-03). |
| ¿Frecuencia de tareas? | La decide el harness (ADR-05). |
| ¿Adjuntos? | Solo nombres y `has_attachments`, sin tamaño ni MIME (RF-03). |
| ¿Múltiples `V*` (macOS)? | La versión que usa Mail, sin override (§15.6). |
| ¿Base de datos propia? | No (ADR-02). |
| ¿Cómo se instala? | Con `pipx` en ambas plataformas (ADR-08). |
| ¿Encabezado `[scope]` explícito? | No hace falta (§15.1). |
| ¿Cómo se "observa" una cuenta? | Solo si está declarada (ADR-06, §15). |
| ¿Qué pasa si no hay cuentas declaradas? | No se observa ninguna (§15.3). |
| ¿Config ampliada? | Secciones `[logging]`, `[search]` y `[new]` (§15.1). |
| **¿Un PRD nuevo para Windows?** (2026-11-03) | No: un único PRD para ambas plataformas (ADR-10). |
| **¿Anexos por backend?** (2026-11-04) | No: un solo documento; los anexos (§24) son material de apoyo. |
| **¿Cómo se identifica un mensaje de Outlook?** (2026-11-03) | `uid` string (ADR-12). |
| **¿Qué pasa si Outlook está cerrado?** (2026-11-03) | Error con exit 6, sin lanzarlo (ADR-13). |
| **¿Qué dependencia COM?** (2026-11-03) | `pywin32` (ADR-14). |
| **¿Qué stores de Outlook?** (2026-11-03) | Locales de las cuentas del perfil + PST (ADR-15). |
| **¿Nuevo Outlook (`olk`)?** (2026-11-03) | Fuera de alcance (§3.3). |
| **¿Cómo se consulta la versión?** (2026-11-03) | Opción global `-v`/`--version` (RF-29, §12.9). |
| **Revisión de la v1.0: datos y búsqueda** (2026-11-03) | Mensaje sin identificador global, acotamiento de `--to`/`--cc` en Windows, S/MIME, `W_BODY_UNREADABLE` y UTF-8 (RF-06, RF-15, RF-04, §12.10, RF-30). |
| **Revisión de la v1.0: `show` y `new`** (2026-11-03) | `show` solo en cuentas declaradas; primera corrida y lookback de `new`; re-emisiones aceptadas (§12.4, §12.3, §18). |
| **Revisión de la v1.0: Outlook** (2026-11-03) | Timeout, alcance y exclusión de stores, `INBOX`, carpetas ocultas, contadores, detección del cliente, caché de `pywin32`, `home` y `object_model_guard` (RF-31, §15.7, §11.3, §12.6, §9.3, §12.8). |
| **Revisión del implementador** (2026-11-03) | Timeout dentro de `doctor`, `show` de un store excluido y cambios de macOS completos (§12.8, §12.4, §11.3, §22.2). |
| **Tercera revisión independiente** (2026-11-03) | Propiedades de nivel store y `unavailable`, `[scope]` en `show`, warnings en el log, LF, resolución de carpetas y fechas futuras en `new` (§4, §15.7, §12.4, §14, RF-30, §15.3, §12.3). |
| **Revisión final** (2026-11-03) | Direcciones, marcado, adjuntos ocultos y `account.uuid` en Outlook (§11.3). |
| **¿Plugins de backend y recuperación local de adjuntos?** (2026-11-11) | Sí, en `3.0.0`: entry points `mailquery.backends` con API 1, `[scope."<driver>:<cuenta>"]`, `uid` `"<driver>:<native_id>"`, comando `attachment` con caché fija y bloqueo del mensaje completo (ADR-17…ADR-27). |
| **¿Código para fallos de E/S de caché y staging?** (2026-11-11, DP-01) | `E_IO` (exit 3); `E_PERMISSION` queda para permisos (§12.6). |
| **¿Qué drivers lista `--version`?** (2026-11-11, DP-02) | Solo los disponibles en la plataforma: en macOS no `outlook`, en Windows no `apple_mail`; los plugins externos siempre (§12.9). |
| **¿Qué pasa al desinstalar un plugin?** (2026-11-11, DP-03) | Sus bloques `[scope]` dan `E_DRIVER_UNKNOWN`, su cursor `E_STATE_CORRUPT`, el anillo se poda y la caché se conserva (§11.2, §13.3). |
| **¿Versión en `develop`?** (2026-11-11, CR-02) | Pre-release `3.0.0a1` (`3.0.0-alpha.1` normalizada por PEP 440) hasta el release `3.0.0` (§22.3). |
| **¿Cómo se valida un acierto de caché?** (2026-11-12, CR-01) | Con un manifiesto SHA-256 por mensaje; se elimina la comparación con el tamaño esperado del driver, que en Outlook nunca coincidía (§10.3.4). |
| **¿Código cuando falla la re-extracción de un archivo borrado durante la ejecución?** (2026-11-12) | El código de ese fallo, como en cualquier extracción (§10.4). |
| **¿`attachment` con drivers `attachments: "remote"`?** (2026-11-12, corregido en F2 el 2026-11-12) | Sí: con el mismo motor que un driver `"local"` y sin red en el núcleo; solo `"none"` se rechaza (RF-48, ADR-39; BUG-01 cerrado en `KNOWN-DEFECTS.md`). |
| **¿Endurecimiento del contenido no confiable?** (2026-11-10 a 2026-11-13, F1) | Sí: saneado A2, cuerpo desde el HTML sin el contenido oculto con `css-inline`, URLs neutralizadas por defecto con `keep`, `strip` y `--strip-links`, avisos de enlaces, dominios no ASCII, remitente y contenido activo en adjuntos, y `content_notice`; sin cuarentena ni detección de inyección (RF-52–RF-66, ADR-29–ADR-38). |
| **¿Tope de extracción de adjuntos?** (2026-11-12, F2) | `[attachments].timeout_seconds`, 60 s por defecto (10–600), con corte duro en los plugins externos; los 30 s de metadatos y de cada llamada COM no cambian (RF-49, ADR-40). |
| **¿Salida a medida?** (2026-11-13, F3) | Fila mínima en `search` y `new`, `--fields`, `--group-by`, `--count`, `doctor --failures` y sección de plugins, diagnóstico sin *preflight* con `hint` de cero resultados y `mailboxes` agrupado por cuenta; se mantienen `new` y `search --unread` (RF-67–RF-79, ADR-41–ADR-49). |
| **¿Cómo se acorta el `uid` de Outlook?** (2026-11-22) | Con un id corto de 10 caracteres derivado del `EntryID`, a cargo del driver, sin cambiar el formato del `uid` ni el contrato JSON; Apple Mail no cambia (ADR-50, RF-81). |
| **¿Quién ofrece las herramientas del id corto?** (2026-11-22) | Una librería del núcleo, con el cálculo (recibe la cantidad de caracteres), la conexión y las operaciones de la tabla; cada driver decide si la usa (RF-80). |
| **¿Qué guarda la caché de ids nativos?** (2026-11-22) | `driver`, `short_id`, `seq` y `native_id` en la tabla `cache_native_ids`, y nada más; ninguna salida JSON tiene una propiedad `short_id` (RF-80). |
| **¿Qué pasa si dos mensajes tienen el mismo id corto?** (2026-11-22) | `seq` los distingue y va en el `uid` a partir de 2; cada `uid` apunta a un solo mensaje y no hay warning nuevo (RF-80). |
| **¿Qué mensajes se registran en la caché de ids nativos?** (2026-11-22) | Solo los que el comando imprime: el núcleo avisa de ellos a cada driver antes de imprimir (RF-82). |
| **¿Qué pasa si el `native_id` de una fila ya no existe?** (2026-11-22) | La fila se borra solo con la ausencia confirmada; con Outlook cerrado, sin conexión o con un PST desmontado no se borra nada; no se actualiza la fila ni se busca el mensaje en otras carpetas (RF-81). |
| **¿Hay transición desde el `state.json` y la caché de adjuntos anteriores?** (2026-11-22) | No: sin migración, compatibilidad ni validación; se asume que el producto siempre funcionó con ids cortos. El dueño borra a mano el `state.json` antiguo, que `new` vuelve a crear, y los directorios de adjuntos residuales de Outlook. |
| **¿Cómo se llaman el archivo y el módulo, y cambia `plugin_api`?** (2026-11-22) | `~/.mailquery/db/cache.db` y `native_ids.py`. Los dos ganchos nuevos, `printed_messages` y `display_native_id`, son opcionales y `plugin_api` sigue en 1 (RF-80, RF-82, RF-83). |
| **¿Qué errores da la caché de ids nativos?** (2026-11-22) | Los del PRD, sin código nuevo y sin cambiar RF-50. Con un driver interno: base ocupada por otro proceso más de 5 s ⇒ `E_LOCKED`; sin permiso ⇒ `E_PERMISSION`; otro fallo, base no válida o registro que falla ⇒ `E_IO`. Dentro de un plugin, por el protocolo de RF-50: `busy`, `permission` o `E_PLUGIN_FAILED` (RF-80). |
| **¿Qué pasa si dos mensajes nuevos con el mismo id corto aparecen en la misma ejecución?** (2026-11-22) | La asignación vale para toda la ejecución: un `native_id` conserva la primera parte del `uid` que recibió, aunque se lea en varias consultas, y los nuevos de un mismo id corto reciben `seq` siguientes en el orden de su `native_id` (RF-80). |
| **¿Hay una tabla aparte para el mayor `seq`?** (2026-11-23) | No: el `seq` siguiente sale del mayor `seq` de las filas del par, así que al borrar la última fila con ese sufijo el número queda libre. Una tabla que recordara el mayor `seq` solo evitaba ese caso, improbable, y obligaba a escribirla en cada registro (RF-80, §23). |
| **¿Se reutiliza el `seq` de una fila borrada?** (2026-11-22) | Sí: el `seq` siguiente es el mayor de las filas que quedan del par, así que al borrar la última fila con ese sufijo el número queda libre para otro mensaje con el mismo id corto (RF-80, §23). |
| **¿Cuándo está un mensaje ausente confirmado?** (2026-11-22) | Solo cuando su store está montado y Outlook, al abrir su `EntryID` en ese store, responde que no existe o que no es válido; cualquier otro resultado conserva la fila (RF-81). |
| **¿Dónde está la base y quién la crea?** (2026-11-22) | En la carpeta `~/.mailquery/db/`. Al abrir la base, la librería crea la carpeta si no existe y crea siempre el archivo si no lo encuentra; un archivo vacío se inicializa (RF-80, §11.4). |
| **¿Qué versión anuncia `develop`?** (2026-11-22) | La pre-release `3.0.0a2`, en lugar de `3.0.0a1` (§22.3). Sustituye a la decisión del 2026-11-11 que fijaba `3.0.0a1` hasta el release. |
| **¿Quién convierte los errores de la librería dentro de un plugin?** (2026-11-22) | La propia librería: el acceso que el núcleo da a un plugin entrega sus fallos con el protocolo de RF-50, aunque el plugin no los capture (RF-80). |
| **¿Qué hint lleva un uid que la caché no resuelve?** (2026-11-22) | El de repetir la búsqueda, tanto si el uid no está en la caché como si su mensaje está ausente confirmado; los demás casos de "no encontrado" conservan el hint actual (RF-81). |
| **¿Cómo se acepta el id corto en la entrada?** (2026-11-22) | Solo tal como se emite: minúsculas y sufijo sin ceros a la izquierda; si no, `invalid uid part '<id>': expected a short id` (RF-81). |
| **¿`new --peek` registra los mensajes que imprime?** (2026-11-22) | Sí: escribe en la caché de ids nativos y no en el estado; sin registro, sus uids no se podrían abrir (RF-82). |
| **¿Cambian `doctor` o los presupuestos de rendimiento?** (2026-11-22) | No: `doctor` no tiene chequeo nuevo y los presupuestos no cambian. |
| **¿Se puede ver el id nativo en la salida?** (2026-11-22) | Sí, solo para depurar: con `--show-native-id` en `show` y en ningún otro comando; es solo de presentación y el id nativo no se acepta como entrada (RF-83). |
| **¿Se expone `doctor` como herramienta MCP?** (2026-11-23) | Sí, siempre con `--json`; `failures` y `log_level` son sus parámetros (RF-85). |
| **¿Qué opciones de los comandos son parámetros de las herramientas MCP?** (2026-11-23) | Todas salvo `--help` y `--show-native-id`; `--log-level` sí se expone. `--show-native-id` no se expone porque es una opción de depuración sin utilidad para el harness (RF-85). |
| **¿Las herramientas MCP llevan prefijo en su nombre?** (2026-11-23) | No: se llaman como el comando (`search`); el harness ya las agrupa por servidor (RF-85). |
| **¿El servidor MCP atiende las llamadas en serie o en paralelo?** (2026-11-23) | En serie, en orden de llegada (RF-86). |
| **¿Se expone `--version` como herramienta MCP?** (2026-11-23) | No: su salida es texto y no JSON; la versión de la app llega en `serverInfo.version` y la de los drivers, en `doctor` (RF-85). |
| **¿Qué versión anuncia `develop`?** (2026-11-23) | La pre-release `3.0.0a3`, en lugar de `3.0.0a2` (§22.3). Sustituye a la decisión del 2026-11-22 que fijaba `3.0.0a2`. |
| **¿El log puede escribirse en JSON?** (2026-11-23) | Sí, con una clave de `[logging]` en `config.toml`, apagada por defecto; apagada, el log es el de texto de siempre (RF-88). |
| **¿El formato del log se puede elegir en la línea de comandos?** (2026-11-23) | No: solo en `config.toml`. |
| **¿El log JSON va al mismo archivo que el de texto?** (2026-11-23) | No: va a `mailquery.jsonl`, con su propia rotación; cada ejecución escribe solo en el archivo del formato activo (RF-88). |
| **¿Qué hace un comando cuando el lock de ejecución está ocupado?** (2026-11-24) | Lo reintenta con pausas crecientes; si el lock sigue ocupado al agotar los reintentos, falla con `E_LOCKED` como antes (RF-89). |
| **¿Qué se configura del reintento del lock?** (2026-11-24) | El número de reintentos, la primera pausa y el factor de crecimiento; no la espera total, que resulta de ellos, ni el tope por pausa, que es fijo. |
| **¿Dónde se configura el reintento del lock?** (2026-11-24) | Solo en `config.toml`, sin opción de la CLI ni parámetro de las herramientas MCP. Ninguna clave hace falta: lo que no se declara vale su valor por defecto. |
| **¿Dónde se documentan los valores por defecto del reintento del lock?** (2026-11-24) | En la ayuda que corresponda, en los README y en la documentación pertinente. |
| **¿La espera del lock va con el proceso hijo persistente del servidor MCP?** (2026-11-24) | No: es un cambio independiente. |
| **¿Dónde se declara la versión del paquete?** (2026-11-25) | Solo en `mailquery.__version__`; `pyproject.toml` la toma como versión dinámica, y el PRD y los documentos no repiten el número de la pre-release. Subir la pre-release de una versión sin publicar cambia solo ese archivo. |


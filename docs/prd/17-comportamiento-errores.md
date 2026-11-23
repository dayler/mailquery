---
aliases: ["Sección 17", "Comportamiento ante errores"]
tags: [prd]
---

## 17. Comportamiento ante errores

Comunes a ambos backends (los propios de cada plataforma están en §12.6; los de configuración en §15.3, los de `show` en §12.4 y los de `attachment` en §12.11):

**Tabla: Comportamiento ante errores comunes a ambos backends**

| Situación | Comportamiento |
|-----------|----------------|
| Fecha inválida o futura | Se ordena por lo que informe el cliente; se reporta ISO 8601. Una fecha nula, ≤ 0 o no representable se reporta como `null` y la consulta continúa. `new` ignora los mensajes con fecha nula, no representable o futura (§12.3). |
| Cero resultados | Exit 0 con `count: 0` (no es error). |
| Lock ocupado | `E_LOCKED`, exit 5. También cuando otro proceso mantiene bloqueada la caché de ids nativos más de 5 s, con el mensaje y el hint de RF-80. |
| Cliente ocupado de forma transitoria | Apple Mail y Outlook: reintento único; si persiste, `E_DB_BUSY` (Apple Mail) o `E_CLIENT_BUSY` (Outlook), exit 5. Un plugin que informa `busy` ⇒ `E_CLIENT_BUSY` (exit 5) sin reintento del núcleo. |
| Outlook cerrado (Windows) | `E_OUTLOOK_NOT_RUNNING`, exit 6; nunca se lanza. |
| Llamada a Outlook colgada más de 30 s (Windows) | RF-31. |
| Operación de un driver que supera el timeout (30 s de metadatos, `[attachments].timeout_seconds` por adjunto extraído) | `E_CLIENT_TIMEOUT` (exit 3), sin reintento automático; staging limpio (RNF-21). |
| `state.json` corrupto o con uids inválidos | `E_STATE_CORRUPT` (§11.2). |
| Uid que ya no existe (rebuild del índice en macOS; mensaje movido en Windows) | `new` es tolerante (cursor por fecha); `show` debe repetir la búsqueda. |
| Disco lleno al escribir estado | Exit 1; el cursor previo queda intacto (escritura atómica). |

---


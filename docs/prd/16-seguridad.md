---
aliases: ["Sección 16", "Seguridad, privacidad y permisos"]
tags: [prd]
---

## 16. Seguridad, privacidad y permisos

### 16.1 Permisos de plataforma

- macOS: leer `~/Library/Mail` requiere **Acceso total al disco (FDA)**, que protege TCC; sin él, la lectura falla sin diálogo (`E_PERMISSION`). El mismo permiso cubre `~/Library/Accounts`: si falta, solo funcionan los UUID. El permiso se concede a la **app que lanza el proceso** (harness, Terminal, iTerm, VS Code…), **no** al venv de pipx, y se asocia a la identidad del binario: tras actualizar el intérprete o la app, hay que verificarlo con `doctor`.
- Windows: no hay permiso equivalente; los requisitos son sesión e integridad compartidas con Outlook (§13.1) y un Object Model Guard que no muestre avisos (§12.8). Permisos del home: RNF-05.
- Uso de `doctor`: RF-75. En ejecución headless no hay prompts; si el Object Model Guard pudiera mostrarlos, lo indica el chequeo `object_model_guard` de `doctor` (§12.8), y una llamada bloqueada termina con `E_CLIENT_TIMEOUT` (RF-31).

### 16.2 Privacidad

- Cero telemetría o analytics. El núcleo y los backends internos no abren red; un plugin externo puede hacerlo si declara `network: true` (§4).
- Permisos de `~/.mailquery`: RNF-05.
- El estado no guarda contenido de correos (§11.2); los logs tampoco (§14); la caché de ids nativos tampoco: solo guarda identificadores (§11.4).
- Las fuentes de cuentas (`Accounts4.sqlite`, cuentas del perfil de Outlook) se leen solo para identificadores, proveedor y email visible (§4, regla 1).
- Nunca se versiona correo en el repositorio.

### 16.3 Prompt injection

El contenido de los correos (asunto, nombres, `headers`, cuerpos, nombres de adjuntos y archivos extraídos) es **entrada no confiable**. El JSON separa metadatos y contenido, y cada respuesta de éxito de `search`, `new`, `show` y `attachment` lo recuerda con `content_notice` (RF-66); las recetas y la skill del harness tratan el contenido como datos citados, nunca como instrucciones. Todos los campos de contenido se sanean (A2, RF-52); el cuerpo es el que ve el destinatario, sin el contenido oculto (A3, RF-53); las URLs salen neutralizadas por defecto (A4, RF-54), y los avisos de enlaces, del remitente y de contenido activo en adjuntos (RF-55–RF-62) dan señales al harness. Por defecto, `search` y `new` no entregan texto del cuerpo (RF-67). Nada de esto detecta ni bloquea una inyección ([anexo de seguridad](../security/threat-model.md), ADR-28). La herramienta no permite acciones destructivas, así que el daño posible se limita a la interpretación del texto por parte del agente.

---


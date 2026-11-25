---
aliases: ["Sección 15.7", "Alcance de stores en Windows"]
tags: [prd]
---

### 15.7 Alcance de stores en Windows (ADR-15)

**Candidatos** (lo que `mailboxes` lista en `accounts[]`/`mailboxes[]`):

**Tabla: Stores candidatos en Windows**

| Store | Condición | Etiqueta |
|-------|-----------|----------|
| Buzón de entrega de una cuenta del perfil | Cuenta Exchange, IMAP, POP3 o EAS cuyo store es local: Exchange en modo caché; las demás, con su archivo de datos en un disco local | `Exchange (…)`, `IMAP (…)`, `POP3 (…)`, `EAS (…)` (con el email SMTP) |
| Archivo de datos `.pst` | En un disco local (incluido un disco extraíble) y que no es el buzón de entrega de una cuenta | `PST ({nombre visible})` |

Si un `.pst` es el buzón de entrega de una cuenta POP3, se etiqueta como la cuenta (`POP3 (…)`), no como `PST (…)`.

**Excluidos** (lo que `mailboxes` lista en `excluded_stores[]`; RF-32):

**Tabla: Stores excluidos en Windows**

| Store | `reason` | Etiqueta | `path` |
|-------|----------|----------|--------|
| Buzón delegado/compartido | `shared_mailbox` | `Exchange shared ({nombre})` | `null` |
| Carpetas públicas | `public_folders` | `Public Folders ({nombre})` | `null` |
| Cuenta Exchange sin modo caché | `online_mode` | la de la cuenta (`Exchange (…)`) | `null` |
| Otro store sin copia local (p. ej. archivo en línea, grupos de Microsoft 365, store sin archivo de datos) | `online_mode` | su nombre visible | `null` |
| `.pst` (o archivo de una cuenta) en ruta UNC o unidad de red mapeada | `network_path` | la que tendría si fuera local | ruta completa |
| Cuenta de otro tipo | `unsupported_account_type` | `{tipo} ({smtp})` | ruta o `null` |
| Store del perfil cuyas propiedades no se pueden leer (p. ej. Outlook no logra conectar con el servidor de un store que no es local) | `unavailable` | su nombre visible si se pudo leer; si no, `unknown` | ruta si se pudo leer; si no, `null` |

Un store `unavailable` no impide leer el resto: los comandos siguen con los stores candidatos. La resolución de `[scope]` contra excluidos: §15.3.

**Carpetas ocultas:** las carpetas internas de sincronización (`Conflicts`, `Sync Issues`, `Local Failures`, `Server Failures` y sus subcarpetas) no se listan ni se leen, en cualquier idioma de Outlook.

Como en macOS, ser candidato no basta: solo se leen las cuentas **declaradas** en `[scope."<driver>:<cuenta>"]` (sin prefijo, con el driver nativo; §15).

---

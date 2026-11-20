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


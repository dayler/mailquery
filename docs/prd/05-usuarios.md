---
aliases: ["Sección 5", "Usuarios y casos de uso"]
tags: [prd]
---

## 5. Usuarios y casos de uso

**Usuario primario:** un harness de agentes (DeepSeek u otro) que invoca la CLI **bajo demanda** y consume su JSON.
**Usuario secundario:** el usuario humano, que verifica resultados y define los preceptos de cada tarea.

La herramienta no programa nada: no hay frecuencias ni cron internos; el harness decide cuándo ejecutar cada comando.

**Tabla: Casos de uso**

| ID | Caso de uso | Comando típico | Desencadenante |
|----|-------------|----------------|----------------|
| CU-01 | Resumen de correo nuevo | `mailquery new` | Cuando el harness lo decida |
| CU-02 | Buscar facturas/recibos por contenido | `mailquery search --text "*factura*" --since 1mo` | Bajo demanda |
| CU-03 | Correos de un remitente específico | `mailquery search --from "*@banco.com*" --since 2w` | Bajo demanda |
| CU-04 | Correos no leídos de un periodo | `mailquery search --unread --since 1w` | Bajo demanda |
| CU-05 | Ver un correo completo | `mailquery show <uid>` (uid tomado de `search`/`new`) | Bajo demanda |
| CU-06 | Descubrir cuentas y carpetas (contadores con `--fields total,unread`) | `mailquery mailboxes` | Al configurar o tras un `search` sin resultados |
| CU-07 | Verificar la instalación o diagnosticar un fallo | `mailquery doctor` | Al instalar o actualizar, o tras un fallo |
| CU-08 | Recuperar adjuntos locales de un correo a disco | `mailquery attachment <uid> --index 2` o `--all` | Bajo demanda, tras inspeccionar el correo con `show <uid>`. |
| CU-09 | Consultar una cuenta servida por un plugin instalado | `mailquery search --since 7d` con `[scope."graph:..."]` | Bajo demanda; el plugin debe estar instalado y declarado. |

---


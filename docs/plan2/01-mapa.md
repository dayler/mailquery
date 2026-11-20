# Mapa de la partición

Rangos de líneas del PRD base (`docs/PRD.md`, blob `ca24a3576fce0b6abd0c4f251aea5ebb313ad52a`, 2991 líneas). Cada archivo empieza en la línea de la columna **Primera línea del rango** (un encabezado, salvo en `12.05-2-ejemplos-show-attachment.md`, que empieza por el párrafo que presenta sus ejemplos) y termina en la línea anterior a la primera línea del archivo siguiente. Si el blob no coincide (P-02), los rangos se recalculan con esas mismas primeras líneas.

## 1. Archivos

La columna **Líneas** es el tamaño del rango base más 5 de frontmatter y lo que añade E-05.

**Tabla: Mapa de archivos de `docs/prd/`**

| Archivo | Rango base | Primera línea del rango | Líneas | `aliases` |
|---|---|---|---|---|
| `01-resumen.md` | 36–106 | `## 1. Resumen ejecutivo` | 78 | "Sección 1", "Resumen ejecutivo" |
| `02-problema.md` | 107–143 | `## 2. Problema y contexto` | 42 | "Sección 2", "Problema y contexto" |
| `03-objetivos.md` | 144–240 | `## 3. Objetivos` | 102 | "Sección 3", "Objetivos" |
| `04-solo-lectura.md` | 241–265 | `## 4. Garantía de solo lectura (requisito de primer nivel)` | 30 | "Sección 4", "Garantía de solo lectura" |
| `05-usuarios.md` | 266–288 | `## 5. Usuarios y casos de uso` | 28 | "Sección 5", "Usuarios y casos de uso" |
| `06-requisitos-funcionales.md` | 289–440 | `## 6. Requisitos funcionales` | 159 | "Sección 6", "Requisitos funcionales" |
| `07-requisitos-no-funcionales.md` | 441–471 | `## 7. Requisitos no funcionales` | 36 | "Sección 7", "Requisitos no funcionales" |
| `08-adr.md` | 472–529 | `## 8. Decisiones de arquitectura (ADR resumidas)` | 63 | "Sección 8", "Decisiones de arquitectura" |
| `09-arquitectura.md` | 530–691 | `## 9. Arquitectura` | 167 | "Sección 9", "Arquitectura" |
| `10-carpetas-y-cache.md` | 692–827 | `## 10. Estructura de carpetas` | 143 | "Sección 10", "Estructura de carpetas" |
| `11-modelo-de-datos.md` | 828–910 | `## 11. Modelo de datos` | 88 | "Sección 11", "Modelo de datos" |
| `12-cli.md` | 911–925 | `## 12. CLI` | 20 | "Sección 12", "CLI" |
| `12.01-opciones-comunes.md` | 926–935 | `### 12.1 Opciones comunes` | 17 | "Sección 12.1", "Opciones comunes" |
| `12.02-search.md` | 936–961 | ``### 12.2 `search` `` | 31 | "Sección 12.2", "search" |
| `12.03-new.md` | 962–991 | ``### 12.3 `new` `` | 35 | "Sección 12.3", "new" |
| `12.04-show.md` | 992–1023 | ``### 12.4 `show` `` | 37 | "Sección 12.4", "show" |
| `12.05-1-contrato-json.md` | 1024–1093 | `### 12.5 Contrato de salida (JSON)` | 77 | "Sección 12.5", "Contrato de salida (JSON)" |
| `12.05-2-ejemplos-show-attachment.md` | 1094–1266 | ``**Ejemplos de `show` y `attachment`.** Los valores abreviados…`` | 178 | "Sección 12.5 (ejemplos A–H)", "Ejemplos de show y attachment" |
| `12.05-3-ejemplos-contenido-salida.md` | 1267–1542 | `#### Ejemplos de contenido no confiable y de salida a medida` | 281 | "Sección 12.5 (ejemplos de contenido y salida)", "Ejemplos de contenido no confiable y de salida a medida" |
| `12.06-errores.md` | 1543–1615 | `### 12.6 Códigos de salida y diccionario de errores` | 80 | "Sección 12.6", "Códigos de salida y diccionario de errores" |
| `12.07-ayuda.md` | 1616–1699 | ``### 12.7 Ayuda (`-h` / `--help`)`` | 89 | "Sección 12.7", "Ayuda" |
| `12.08-doctor.md` | 1700–1808 | ``### 12.8 `doctor` `` | 118 | "Sección 12.8", "doctor" |
| `12.09-version.md` | 1809–1841 | ``### 12.9 `--version` (`-v`)`` | 38 | "Sección 12.9", "version" |
| `12.10-warnings.md` | 1842–1870 | `### 12.10 Catálogo de warnings` | 34 | "Sección 12.10", "Catálogo de warnings" |
| `12.11-attachment.md` | 1871–1921 | ``### 12.11 `attachment` `` | 58 | "Sección 12.11", "attachment" |
| `12.12-precedencia.md` | 1922–1936 | `### 12.12 Precedencia e interacciones del contenido y de la salida` | 20 | "Sección 12.12", "Precedencia e interacciones del contenido y de la salida" |
| `13-despliegue.md` | 1937–2003 | `## 13. Despliegue e instalación` | 72 | "Sección 13", "Despliegue e instalación" |
| `14-logs.md` | 2004–2031 | `## 14. Logs` | 33 | "Sección 14", "Logs" |
| `15-configuracion.md` | 2032–2320 | `## 15. Configuración` | 296 | "Sección 15", "Configuración" |
| `16-seguridad.md` | 2321–2342 | `## 16. Seguridad, privacidad y permisos` | 27 | "Sección 16", "Seguridad, privacidad y permisos" |
| `17-comportamiento-errores.md` | 2343–2363 | `## 17. Comportamiento ante errores` | 26 | "Sección 17", "Comportamiento ante errores" |
| `18-procesamiento-unico.md` | 2364–2391 | `## 18. Procesamiento único e idempotencia` | 35 | "Sección 18", "Procesamiento único e idempotencia" |
| `19-rendimiento.md` | 2392–2421 | `## 19. Rendimiento` | 35 | "Sección 19", "Rendimiento" |
| `20-criterios-aceptacion.md` | 2422–2555 | `## 20. Criterios de aceptación` | 139 | "Sección 20", "Criterios de aceptación" |
| `21-harness.md` | 2556–2588 | `## 21. Operación con el harness` | 38 | "Sección 21", "Operación con el harness" |
| `22-versiones.md` | 2589–2695 | `## 22. Versiones` | 114 | "Sección 22", "Versiones" |
| `23-riesgos.md` | 2696–2798 | `## 23. Riesgos y mitigaciones` | 108 | "Sección 23", "Riesgos y mitigaciones" |
| `24-anexos.md` | 2799–2800 | `## 24. Anexos` | 16 | "Sección 24", "Anexos" |
| `anexos/A-spike-outlook.md` | 2801–2847 | `### Anexo A — Resumen del spike de Outlook (2026-11-03)` | 52 | "Anexo A", "Resumen del spike de Outlook" |
| `anexos/B-hechos-macos.md` | 2848–2868 | `### Anexo B — Hechos verificados en macOS (2026-11-01/02)` | 26 | "Anexo B", "Hechos verificados en macOS" |
| `anexos/C-alternativas.md` | 2869–2890 | `### Anexo C — Alternativas evaluadas por cliente` | 31 | "Anexo C", "Alternativas evaluadas por cliente" |
| `anexos/D-registro-decisiones.md` | 2891–2935 | `### Anexo D — Registro de decisiones` | 50 | "Anexo D", "Registro de decisiones" |
| `anexos/E-ejemplos-invocacion.md` | 2936–2972 | `### Anexo E — Ejemplos de invocación` | 42 | "Anexo E", "Ejemplos de invocación" |

Archivos que no salen de un rango único del PRD base:

**Tabla: Archivos con origen mixto o nuevo**

| Archivo | Origen | `aliases` y `tags` |
|---|---|---|
| `00-indice.md` | Líneas 1–9 (cabecera, con E-01) + texto nuevo de `02-textos.md`, sección 1 | "PRD", "Índice del PRD" · `[prd]` |
| `HISTORIAL.md` | Líneas 10–33 (tabla de versiones, con E-02) | "Historial del PRD" · `[prd]` |
| `GLOSARIO.md` | Líneas 2975–2991 (términos, con E-07) | "Glosario", "Anexo F" · `[prd, glosario]` |
| `PLANTILLA-CAMBIO.md` | Texto nuevo de `02-textos.md`, sección 2 | "Plantilla de cambio" · `[prd, plantilla]` |

Las líneas 34–35 (`---` y una línea en blanco) y 2973–2974 (`### Anexo F — Glosario` y una línea en blanco) no pasan a ningún archivo (E-01, E-07).

`12.05-2-ejemplos-show-attachment.md` empieza por el párrafo que presenta los ejemplos A–H (línea base 1094), para que quede junto a ellos, y termina con el ejemplo genérico de error y la regla de formato de los warnings (líneas base 1258–1266), que siguen al ejemplo H en el PRD. Se quedan ahí porque R-03 no permite cambiar el orden de las líneas. La regla "si un ejemplo contradice una regla del contrato, manda la regla" de la portada no depende de en qué archivo esté cada texto.

## 2. Frontmatter

Cada archivo de `docs/prd/` empieza con estas cinco líneas: los dos alias de su fila entre comillas dobles y la etiqueta `prd`. La quinta línea queda en blanco.

```markdown
---
aliases: ["Sección 6", "Requisitos funcionales"]
tags: [prd]
---

```

Los archivos de la tabla de origen mixto usan sus propios `aliases` y `tags`.

## 3. Cambios de contenido permitidos

Son los únicos cambios de contenido (R-02). Todo lo demás se copia sin cambios.

**Tabla: Cambios de contenido permitidos**

| ID | Archivo | Líneas base | Cambio |
|---|---|---|---|
| E-01 | `00-indice.md` | 1–9, 34–35 | Las líneas 1–9 pasan a la portada, con tres cambios. Línea 4: `2.2 (un solo documento para todas las plataformas;` pasa a ser `2.3 (un solo PRD para todas las plataformas, en un archivo por sección;` y el resto de la línea no cambia. Línea 6: la fecha pasa a ser la del commit de M2. Línea 8: se añade al final ` v2.3: el documento se parte en un archivo por sección, sin cambiar el producto.` Las líneas 34–35 se eliminan. |
| E-02 | `HISTORIAL.md` | 10–33 | Tras el frontmatter van `# Historial del PRD`, una línea en blanco y las líneas 10–33 sin cambios. La fila 2.3 de `02-textos.md`, sección 3, se inserta después de la línea base 32 (la última fila de la tabla) y antes de la línea en blanco 33. |
| E-03 | `10-carpetas-y-cache.md` | 704 | `│   ├── PRD.md                      # este documento` pasa a ser `│   ├── prd/                        # este documento, un archivo por sección (portada: 00-indice.md)`, con la columna del comentario alineada como las demás. |
| E-04 | Varios | 70, 72, 133, 505, 2339 · 87 · 2408 | Enlaces relativos un nivel más abajo: `](security/threat-model.md)` → `](../security/threat-model.md)`; `](KNOWN-DEFECTS.md)` → `](../KNOWN-DEFECTS.md)`; `](PERFORMANCE-BACKLOG.md)` → `](../PERFORMANCE-BACKLOG.md)`. |
| E-05 | Varios | Ver tabla de títulos | Encima de cada tabla sin título se añaden su línea `**Tabla: <título>**` y una línea en blanco. Si justo encima hay una etiqueta en negrita o una frase introductoria, el título va entre esa etiqueta y la tabla. |
| E-06 | `24-anexos.md` | 2799–2800 | Tras `## 24. Anexos` y su línea en blanco se añade la lista de `02-textos.md`, sección 4. |
| E-07 | `GLOSARIO.md` | 2973–2991 | Estructura de `02-textos.md`, sección 5: dos grupos `##`, un `###` por término en orden alfabético y la definición literal en su propio párrafo, con la primera letra en mayúscula. |

**Tabla: Títulos de las tablas sin título (E-05)**

| Línea base de la tabla | Archivo | Título |
|---|---|---|
| 40 | `01-resumen.md` | Plataformas, clientes y forma de lectura |
| 388 | `06-requisitos-funcionales.md` | Requisitos del contrato de errores y de la caché |
| 781 | `10-carpetas-y-cache.md` | Extensiones peligrosas por categoría |
| 928 | `12.01-opciones-comunes.md` | Opciones comunes |
| 1066 | `12.05-1-contrato-json.md` | Valores de `body` en `search` y `new` |
| 1602 | `12.06-errores.md` | Correspondencia entre `reason` y código de error |
| 1704 | `12.08-doctor.md` | Chequeos de `doctor` por backend |
| 1711 | `12.08-doctor.md` | Chequeos propios de cada backend |
| 1879 | `12.11-attachment.md` | Opciones de `attachment` |
| 2292 | `15-configuracion.md` | Stores candidatos en Windows |
| 2378 | `18-procesamiento-unico.md` | Riesgos y mitigaciones del procesamiento único |
| 2662 | `22-versiones.md` | Cambios visibles en macOS en 3.0.0 |
| 2873 | `anexos/C-alternativas.md` | Alternativas evaluadas para Apple Mail |
| 2884 | `anexos/C-alternativas.md` | Alternativas evaluadas para Outlook clásico |

Si M1 encuentra un número distinto de tablas sin título, las que falten se titulan con el mismo criterio (lo que dice la tabla, sin justificar) y se anotan en el registro. Cuentan para R-01.

## 4. Presupuesto previsto (R-01)

**Tabla: Líneas añadidas y eliminadas previstas**

| Cambio | Añadidas | Eliminadas |
|---|---|---|
| E-01 | 3 | 5 |
| E-02 | 3 | 0 |
| E-03 | 1 | 1 |
| E-04 | 7 | 7 |
| E-05 | 28 | 0 |
| E-06 | 9 | 0 |
| E-07 | ~70 | 19 |
| **Total** | **~121** | **32** |

Total previsto: unas 155 líneas (una simulación de la partición dio 156), frente a un límite de 299. El ~ de E-07 es por los encabezados de grupo y las líneas en blanco entre términos.

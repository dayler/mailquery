---
aliases: ["Versión del paquete en un solo archivo"]
tags: [cambio]
---

# Versión del paquete en un solo archivo

**Tipo:** refactor
**Base:** PRD 2.7
**Fecha:** 2026-11-25
**Aprobación:** dueño del producto, 2026-11-25
**Paquete:** 3.0.0 (sin efecto)

## Estado

implementado

## Contexto

El número de versión del paquete está repetido en `pyproject.toml`, `mailquery.__version__`, los goldens de `doctor`, los tests de documentación, los dos README, `docs/INTERFACES.md`, el modelo de amenazas y cuatro puntos del PRD. Subir la pre-release obliga a cambiarlos todos a la vez, y un cambio de código que no subió el número (la espera del lock) se integró sin que nadie lo notara.

Alternativas descartadas:

- **`pyproject.toml` como única fuente y `__version__` leído de los metadatos instalados.** Con una instalación editable los metadatos no se regeneran al cambiar el número, y `--version` mostraría el número viejo hasta reinstalar.
- **Un script que reescribe todos los archivos.** El número seguiría repetido en todos ellos.

## Requerimiento

### Fuente única de la versión

- **Dónde se declara.** El número de versión del paquete se declara solo en `__version__` de `src/mailquery/__init__.py`.
- **Metadatos.** `pyproject.toml` no lleva un `version` propio: declara la versión como dinámica, tomada de `mailquery.__version__`. Los metadatos del paquete construido o instalado llevan ese número.
- **Quién lo muestra.** `--version`, el `detail` del chequeo `driver` de `doctor`, el `serverInfo.version` del servidor MCP y los metadatos instalados muestran ese mismo número. No cambia ninguna salida.
- **Documentos.** Ni el PRD (salvo `HISTORIAL.md` y el Anexo D, que registran hechos pasados) ni los documentos consumidores repiten el número de la pre-release: dicen que `develop` anuncia una pre-release de la versión en curso (`3.0.0aN`) y, donde muestran una salida de `--version` o de `doctor`, usan un marcador en lugar del número.
- **Tests.** Los goldens de `doctor` guardan el marcador `pkg <VERSION>`, y la comparación sustituye la versión del paquete antes de comparar.
- **Subir la pre-release.** Subir el número de pre-release de una versión sin publicar cambia solo `__version__`; el resto del repositorio no cambia.

### Elementos del PRD que cambian

- **Portada.** La línea "Versión del paquete" dice que `develop` anuncia una pre-release de `3.0.0`, sin su número.
- **ADR-27.** Dice que `develop` anuncia una pre-release de `3.0.0`, sin su número.
- **§9.** La fila de `__init__.py` dice que `__version__` es la única declaración del número de versión.
- **§10.** El comentario de `pyproject.toml` dice que la versión se toma de `__version__`.
- **§12.9.** En `develop`, `<versión>` es una pre-release de `3.0.0` (`3.0.0aN`), sin su número.
- **§22.3.** El estado dice que `develop` anuncia una pre-release de `3.0.0` (`3.0.0aN`), que su número se declara solo en `__version__`, de donde la toman los metadatos, `--version`, `doctor` y el servidor MCP, y que el PRD y los documentos no repiten el número.

## Criterios de aceptación

- `pyproject.toml` no tiene la clave `version` en `[project]`, lista `version` en `dynamic` y declara `[tool.setuptools.dynamic].version = { attr = "mailquery.__version__" }`.
- Con el paquete instalado, `importlib.metadata.version("mailquery")`, `mailquery --version` y el `detail` de `doctor` muestran `mailquery.__version__`.
- Los goldens `doctor` y `outlook/doctor` contienen `pkg <VERSION>` y pasan con cualquier valor de `__version__`.
- Los dos README, `docs/INTERFACES.md`, `docs/security/` y el PRD (salvo `HISTORIAL.md` y el Anexo D) no contienen el valor de `__version__`.
- Los ejemplos de `--version` de los README usan `<version>` (o `<versión>`) en lugar del número y conservan la forma con `drivers:`.
- Cambiar solo `__version__` a otra pre-release y reinstalar el paquete deja la suite completa en verde sin tocar ningún otro archivo.

## IDs

- Crea: —
- Elimina: —

## Dependencias

Ninguna

## Decisiones

- **¿Dónde se declara la versión del paquete?** (2026-11-25) Solo en `mailquery.__version__`; `pyproject.toml` la toma como versión dinámica, y el PRD y los documentos no repiten el número de la pre-release. Subir la pre-release de una versión sin publicar cambia solo ese archivo.

## Glosario

Sin cambios

## Conciliación con el PRD

**Tabla: Conciliación con el PRD**

| ID | Contrato | Archivo | Ancla | Qué cambia | Estado |
|---|---|---|---|---|---|
| RC-01 | Versión del paquete en la portada | `00-indice.md` | `**Versión del paquete:**` | `develop` anuncia una pre-release de `3.0.0`, sin su número. | implementado |
| RC-02 | Versión `3.0.0` | `08-adr.md` | `ADR-27` | `develop` anuncia una pre-release de `3.0.0`, sin su número. | implementado |
| RC-03 | Módulo `__init__.py` | `09-arquitectura.md` | `` `__init__.py` `` | `__version__` es la única declaración del número de versión. | implementado |
| RC-04 | `pyproject.toml` en el árbol del repositorio | `10-carpetas-y-cache.md` | `├── pyproject.toml` | El comentario dice que la versión se toma de `__version__`. | implementado |
| RC-05 | Salida de `--version` | `12.09-version.md` | `Formato:` | En `develop`, `<versión>` es una pre-release de `3.0.0` (`3.0.0aN`), sin su número. | implementado |
| RC-06 | Estado de la versión del paquete | `22-versiones.md` | `**Estado:**` | `develop` anuncia una pre-release de `3.0.0` (`3.0.0aN`); su número se declara solo en `__version__`, de donde lo toman los metadatos, `--version`, `doctor` y el servidor MCP; el PRD y los documentos no lo repiten. | implementado |

## Documentos consumidores

- README.md: actualizado
- README.es.md: actualizado
- docs/INTERFACES.md: actualizado
- docs/security/threat-model.md: actualizado
- docs/tests/end-to-end.md: actualizado
- docs/tests/docs-packaging.md: actualizado

## Checklist de conciliación

**Tabla: Checklist de conciliación**

| ID | Ítem | Cómo se verifica | Estado |
|---|---|---|---|
| CL-01 | Cada fila de "Conciliación con el PRD" está aplicada en su archivo | Revisión fila por fila | pendiente |
| CL-02 | El resto del PRD no cambia | Diff del PRD limitado a los archivos de la tabla, el glosario, el Anexo D, la portada y el historial | pendiente |
| CL-03 | Los IDs de la unidad están creados y eliminados en el PRD, sin huecos ni referencias rotas | `doc_14` | pendiente |
| CL-04 | Las decisiones están en el Anexo D y el glosario está aplicado | Revisión de "Decisiones" y "Glosario" | pendiente |
| CL-05 | Los documentos consumidores están actualizados | Ninguno está `pendiente` | pendiente |
| CL-06 | No quedan textos obsoletos en el PRD ni en los documentos consumidores: `3.0.0a3`, `3.0.0-alpha.3`, `version = "` en `pyproject.toml` | Búsqueda de cada texto | pendiente |
| CL-07 | El defecto registrado está cerrado | Su entrada de `docs/KNOWN-DEFECTS.md` | pendiente |
| CL-08 | La versión del documento, el historial y los próximos IDs libres están al día | Portada e `HISTORIAL.md` | pendiente |
| CL-09 | La suite pasa | Suite completa, con `doc_14` y `doc_15` | pendiente |
| CL-10 | Subir la pre-release cambia solo `__version__` | Con `__version__` en otra pre-release y el paquete reinstalado, la suite pasa sin cambiar otro archivo | pendiente |

## Desviaciones aprobadas

Ninguna

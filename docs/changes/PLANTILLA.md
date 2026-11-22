---
aliases: ["Plantilla de unidad de cambio"]
tags: [cambio, plantilla]
---

# {Título de la unidad}

**Tipo:** {funcionalidad | cambio | defecto | errata | refactor | versión}
**Base:** PRD {versión}
**Fecha:** {AAAA-MM-DD de creación}
**Aprobación:** —
**Paquete:** {versión sin sufijo de pre-release} ({mayor | menor | parche | sin efecto})

## Estado

borrador

## Contexto

{Problema, motivo y alternativas descartadas. No se copia al PRD. Una unidad de tipo defecto cita aquí el ID de su entrada del registro de defectos, si la tiene.}

## IDs

- Crea: {marcadores en borrador (RF-x1, AC-x1), IDs reales desde la aprobación, o —}
- Elimina: {IDs o —}

## Dependencias

{Ninguna, o una línea "- nombre" por cada unidad que debe estar conciliada antes.}

## Cambios en el PRD

### {archivo} — {sección N | sección 12.M | Anexo X | Portada}

{Un encabezado por archivo, en el orden de la portada. Bajo él, Operación, Ubicación y Texto final se repiten por cada cambio del archivo. Si la unidad solo cambia el glosario o el Anexo D, esta sección lleva solo: Ninguno.}

- **Operación:** {añadir | modificar | eliminar}
- **Ubicación:**

```markdown
{el principio de una línea del archivo, que solo una línea tiene, o: archivo nuevo}
```

- **Texto final:**

```markdown
{texto literal que queda en el PRD; no se escribe en eliminar}
```

## Decisiones

{Ninguna, o la tabla "Tabla: Filas para el Anexo D" con las columnas Pregunta original y Decisión.}

## Glosario

Sin cambios

## Secciones relacionadas y textos obsoletos

- Un objetivo (3) o un caso de uso (5): {cambia | sin cambio}
- Un RF o RNF (6, 7): {cambia | sin cambio}
- La salida JSON (12.5): {cambia | sin cambio}
- Un error o código de salida (12.6): {cambia | sin cambio}
- Un warning (12.10): {cambia | sin cambio}
- Una opción de configuración (15): {cambia | sin cambio}
- Una decisión de arquitectura (8): {cambia | sin cambio}
- Un comportamiento visible para el usuario: {cambia | sin cambio}
- Textos obsoletos: {frases o reglas que deben desaparecer, o Ninguno}

## Documentos consumidores

{Ninguno, o una línea "- documento: estado" por documento, con el estado pendiente, actualizado o sin cambio.}

## Desviaciones aprobadas

Ninguna

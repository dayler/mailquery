---
aliases: ["Plantilla de cambio"]
tags: [prd, plantilla]
---

# {Título del documento de cambio}

**Base:** PRD {versión} · **Fecha:** {AAAA-MM-DD}

**Numeración:** {tipo}-{primero}…{tipo}-{último} por cada tipo de ID que crea el documento, o —.

**Fuente de verdad:** hasta que una unidad está `conciliado`, para lo que cambia manda este documento.

**Tabla: Unidades del documento**

| Unidad | Título | Estado | IDs reservados | Depende de |
|---|---|---|---|---|
| {ID} | {título} | borrador | {IDs o —} | Ninguna |

## {ID} — {título}

### Estado

borrador

### Contexto

{Problema, motivo y alternativas descartadas. No se copia al PRD.}

### IDs

- Crea: {IDs o —}
- Sustituye: {IDs o —}
- Elimina: {IDs o —}
- Renumera: {ID antiguo → ID nuevo, o —}

### Dependencias

Ninguna

### Cambios en el PRD

#### {archivo} — sección {N.M}

- **Operación:** {añadir | modificar | sustituir | eliminar}
- **Ubicación:** {ID, encabezado o primera frase actual; en añadir, el texto después del cual va}
- **Texto final:**

```markdown
{texto literal que queda en el PRD}
```

### Decisiones

Ninguna

### Glosario

Sin cambios

### Secciones relacionadas y textos obsoletos

- {Fila de la tabla "Secciones que suelen cambiar a la vez"}: {cambia | sin cambio}
- Textos obsoletos: {frases o reglas que deben desaparecer, o Ninguno}

### Documentos consumidores

- {documento}: {pendiente | actualizado | sin cambio}

### Desviaciones aprobadas

Ninguna

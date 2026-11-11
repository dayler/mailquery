# Evidencia por milestone

Un archivo por milestone (`MNN.md`), escrito por el **orquestador** al cerrar su gate local (plan maestro §6.3, §9.1). El subagente entrega los datos crudos; nunca escribe aquí ni en `docs/plan/` en general.

## Convención

- Nombre: `M01.md` … `M11.md`; sin subdirectorios y sin adjuntos binarios.
- Se versiona en git: es la evidencia que sustituye al PR por milestone (la integración es por lote, §3.2). No hay evidencia de release: esta fase no publica (D15).
- Cada archivo se enlaza desde el registro de ejecución (§11) con una línea de resumen.
- Higiene: rutas relativas al repo, sin rutas del home ni nombres de usuario, sin direcciones de correo reales, sin tokens ni salidas con datos de mensajes reales (usar fixtures).

## Plantilla

```markdown
# MNN — <título del milestone>

| Campo | Valor |
|---|---|
| Tag | `prd-v2.1-MNN` |
| Base del lote | <rama del lote> @ <commit base> |
| Commit de cierre | <sha corto> |
| Lote | I<N> |
| Fecha | AAAA-MM-DD |

## 1. Suite completa (host macOS del dueño)

- Comando: `python -B -m unittest discover -s tests -t . -v`
- Resultado: <corridos> tests, <fallos> fallos, <saltados> saltados (<duración>)
- Fallos nuevos frente a la línea base: <ninguno | detalle y justificación>

## 2. Grupos del milestone, solos

- Comando: `python -B -m unittest tests.<módulo> -v` / `-k <patrón>`
- Resultado por grupo: <UT-XXX-NN: verde>

## 3. Goldens

| Golden | Estado | Motivo |
|---|---|---|
| `<ruta>` | creado / actualizado / intacto | <motivo> |

## 4. Cobertura

- Tests nuevos: <n>
- AC cubiertos: <AC-NN (UT-XXX-NN.01..0k), …>

## 5. Diff

- `git diff --check`: limpio
- `git diff --stat <base del lote>..<commit>`: <n archivos, +a/−b>

## 6. Riesgos, deuda y HITL

- <riesgo o deuda aceptada, con referencia al PRD/plan>
- <preguntas abiertas, si las hay; ninguna si el milestone cerró limpio>

## 7. CI del lote (solo el último milestone del lote)

- PR: <URL> · run: <URL> · jobs: 15 (12 `unittest` + 3 `install-scripts`) · resultado: <verde>
```

## CI

La matriz se ejecuta por lote (§7.5): los 4 PRs de lote (I1–I4). Esta fase no tiene corrida de tag ni de release. El archivo del **último milestone de cada lote** añade la sección 7 con la URL del run; los demás la omiten.

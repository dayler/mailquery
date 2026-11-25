# Fases, lotes y gates — espera-del-lock

Solo lo escribe el orquestador. La leyenda de los semáforos es la de `MASTER-PLAN.md`.

## Fases del plan

**Tabla: Fases del plan**

| Fase | Contenido | Estado |
|---|---|---|
| 0 Preparación | Tareas de "Fase 0" | 🟢 |
| 1 Implementación | Oleadas 1 a 3 | 🟢 |
| 2 Integración | Cierre del lote 1, PR único y matriz verde | 🟡 |
| 3 Cierre | Tareas de "Fase 3" | ⚪ |

### Fase 0

1. Aplicar a la unidad la aprobación del dueño (D-01): estado `aprobado`, cabecera con la aprobación, IDs reales en lugar de `RF-x1`, `AC-x1` y `AC-x2`, y la unidad en `develop`, como fija `docs/changes/PROTOCOLO.md`.
2. Sustituir los marcadores por los IDs reales en todo el plan, anotar el commit de referencia en los briefs y comprobar los rangos de línea que citan.
3. Escribir en `docs/tests/` las definiciones `[pendiente]` de los grupos nuevos, desde la sección "Tests" de cada brief: UT-CFG-07 y UT-CLI-15 en `cli-config.md`, UT-ST-08 en `state-backends.md`, UT-MCP-13 en `mcp-server.md`, DOC-19 en `docs-packaging.md`.
4. Partir `docs/tests/cli-config.md` por prefijo si con los grupos nuevos pasa de 300 líneas, y actualizar la tabla de prefijos de `TEST-CATALOG.md`.
5. Añadir a `docs/tests/acceptance-matrix.md` las filas de los dos AC con sus grupos.
6. Marcar `[por actualizar]` los casos existentes cuyo esperado cambia: DOC-06.02 (secciones documentadas en el ejemplo de configuración).
7. Tomar la línea base de la suite y crear `feature/espera-del-lock` y `feature/espera-del-lock-lote-1`.

### Fase 3

1. Aplicar a la unidad las transiciones propuestas: filas de conciliación a `implementado`, documentos consumidores a `actualizado`, desviaciones aprobadas; unidad a `implementado`.
2. Prueba manual del checklist de la unidad (dos sesiones, veinte llamadas solapadas): la ejecuta el dueño en macOS y en Windows y basta su confirmación (D-02).
3. Conciliación según `docs/changes/PROTOCOLO.md`, como último commit de la rama de la unidad.
4. Merge a `develop` por orden del dueño.

## Lotes e integración

**Tabla: Lotes de integración**

| Lote | Milestones | Rama de integración | Corridas de CI previstas |
|---|---|---|---|
| 1 | M01, M02, M04, M03 | `feature/espera-del-lock-lote-1` | 1 al cerrar el lote, 1 tras el commit de conciliación, 1 de margen para correcciones |

**Tabla: Presupuesto de integración**

| Escenario | PRs | Corridas de matriz | Jobs (15 por corrida: 12 de suite + 3 de instaladores) |
|---|---|---|---|
| Este plan | 1 | 3 en el PR + 1 por el push a `develop` del merge | 60 |
| Un PR por milestone | 5 (4 milestones + conciliación) | 5 en PR + 5 por push a `develop` | 150 |

- **Milestone → lote.** Con el gate local verde, el orquestador integra la rama del milestone en la del lote con `--no-ff`. Sin PR por milestone y sin esperar CI. Un milestone no cierra con la suite local roja, con deuda de documentación o sin su evidencia.
- **Lote → unidad.** Al cerrar el lote, su rama se integra en `feature/espera-del-lock` con `--no-ff`.
- **PR único.** De `feature/espera-del-lock` a `develop`, abierto al cerrar el lote. Las correcciones se empujan al mismo PR. Solo se integra con la matriz completa verde.
- **CI.** `.github/workflows/tests.yml` ya corre solo en PR a `develop` y en push a `develop`, con cancelación de corridas y tiempos límite de 20 y 15 minutos: no cambia (D-04).
- **Versión.** `pyproject.toml` no cambia (D-03).
- **Restricciones.** Sin tags, sin release y sin merge a `main` salvo orden del dueño.

## Gates

- **Milestone:** suite local sin fallos nuevos frente a la línea base; grupos del milestone verdes solos; evidencia escrita; semáforos, tabla de conciliación y documentos consumidores de la unidad actualizados y coincidentes.
- **Lote:** matriz completa verde en el PR; diff acumulado dentro de los alcances de escritura; integración `--no-ff`; URL de la corrida en `REGISTRO.md`.
- **Fase:** todos los AC con evidencia; documentación sin los textos obsoletos que lista el checklist de la unidad; `tests/test_readonly.py` verde; SMOKE del equipo verdes o saltadas con motivo; tabla de conciliación de la unidad actualizada.

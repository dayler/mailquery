# Riesgos del plan servidor-mcp

Riesgos de la ejecución del plan. Los riesgos del producto están en la sección "Riesgos" de la unidad.

**Tabla: Riesgos de ejecución**

| ID | Riesgo | Milestone | Mitigación | Estado |
|---|---|---|---|---|
| RP-01 | El refactor de eventos cambia un byte del log de texto (espacios, orden, `True`/`true`, traceback) | M01 | Test de regresión que, para cada evento migrado, compara la línea con la que producía el código base; UT-LOG-03 y UT-LOG-04 siguen verdes | 🟢 |
| RP-02 | Los tests con procesos reales (servidor más proceso hijo) son lentos en Windows y alargan la matriz | M05, M07 | Pocos casos con proceso real (UT-MCP-09 a UT-MCP-12); el resto con el ejecutor sustituido; tope de 120 s por subproceso como en `tests/test_cli.py`; DP-16 vigila el `timeout-minutes` | 🟢 |
| RP-03 | Tests de orden y de cierre de stdin dependientes del tiempo (AC-74) que fallan de forma intermitente | M02, M05 | Sincronizar con eventos (`threading.Event`) o con un ejecutor que registra inicio y fin, nunca con `sleep` como aserción | 🟢 |
| RP-04 | En Windows, el servidor o un test retiene `mailquery.log` y la rotación del hijo falla | M05 | DP-07 (manejador que cierra el archivo tras cada evento); UT-MCP-11.03 y UT-MCP-12 corren en la matriz de Windows | 🟢 |
| RP-05 | Ciclo de importación entre `cli.py` y `mcp_server.py`, o carga de entry points al importar `cli` | M02, M05 | DP-13; UT-MCP-08.03 y UT-MCP-10 | 🟢 |
| RP-06 | La cobertura total baja del 85 % por código del servidor que solo corre en procesos hijo | M02, M05 | La lógica (protocolo, esquemas, argv, validación, resultado) se prueba en proceso con el ejecutor sustituido; el ejecutor real se prueba también en proceso con `subprocess.run` simulado | 🟢 |
| RP-07 | M05 no cabe en el presupuesto de llamadas de un subagente | M05 | Fases con commit por fase; partición prevista DP-19 | 🟢 |
| RP-08 | La aprobación de la unidad cambia criterios de aceptación ya planificados | todos | La unidad se aprobó el 2026-11-23 sin cambios en sus criterios; solo se sustituyeron los marcadores por los IDs reservados | 🟢 |
| RP-09 | `docs/tests/cli-config.md` o `docs/tests/docs-packaging.md` superan 300 líneas al añadir los grupos y los títulos de tabla de los grupos nuevos y modificados (`cli-config.md` llega a unas 290) | F0 | F0 cuenta las líneas tras insertar; si una pasa de 300, parte el archivo por prefijo como dice `TEST-CATALOG.md` y actualiza la tabla de prefijos | 🟢 |
| RP-10 | `develop` avanza mientras el plan está abierto y el PR entra en conflicto | lotes | Al abrir cada lote, el orquestador integra `develop` en `feature/servidor-mcp` si avanzó, y vuelve a medir la línea base | 🟢 |
| RP-11 | No hay equipos o tiempo del dueño para los SMOKE de CL-10 en macOS y Windows | M07, F4 | M07 se cierra con los tests escritos y el procedimiento; la ejecución del dueño es un gate de F4 y no bloquea el cierre del lote 2; DA-03 se pregunta al cerrar M07 | 🟢 |
| RP-12 | El adaptador de `get_logger` sustituye los datos extra del llamador en todas las versiones soportadas (`merge_extra` solo existe desde Python 3.13), y los campos del evento no llegarían al formateador JSON | M01, M04 | DP-02 exige conservar el `run` y los datos del evento sin depender de `merge_extra`; UT-LOG-05 corre en la matriz con Python 3.11–3.14 | 🟢 |

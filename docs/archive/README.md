# Archivo — historial de implementación de 2.0.0

Documentos de las fases ya cerradas de la implementación de 2.0.0 (Windows +
Outlook clásico, paridad macOS), guardados como registro histórico. **No se
mantienen actualizados**: el contrato vigente está en [`../PRD.md`](../PRD.md) y
las reglas de desarrollo y pruebas en [`../INTERFACES.md`](../INTERFACES.md).

El prefijo de cada archivo es la fecha del informe (campo «Fecha» del propio
documento), para poder identificarlo.

| Documento | Fase | Fecha | Contenido | Commit de la fase |
|---|---|---|---|---|
| [`2026-11-04-Walkthrough-w0-parity.md`](2026-11-04-Walkthrough-w0-parity.md) | W0 | 2026-11-04 | Portabilidad, paridad macOS y auditoría de tests | `437ec2c` |
| [`2026-11-04-Walkthrough-w2-backend-interface.md`](2026-11-04-Walkthrough-w2-backend-interface.md) | W2 | 2026-11-04 | Interfaz de backend y adaptador de Apple Mail | `c52825b` |
| [`2026-11-04-Walkthrough-w3-outlook-read.md`](2026-11-04-Walkthrough-w3-outlook-read.md) | W3 | 2026-11-04 | Backend de lectura de Outlook, fake, proxy de solo lectura y goldens | `595891b` |
| [`2026-11-04-Walkthrough-w4-outlook-complete.md`](2026-11-04-Walkthrough-w4-outlook-complete.md) | W4 | 2026-11-04 | `new`, `--text`/`--to`/`--cc`, `doctor`, exit 6 y pruebas cross-backend | `6e8b439` |
| [`2026-11-04-Walkthrough-w5-polish.md`](2026-11-04-Walkthrough-w5-polish.md) | W5 | 2026-11-04 | Instaladores, empaquetado 2.0.0, SMOKE, rendimiento de Outlook y documentación de usuario | `bf1d50d` |

El plan de ejecución `2026-11-03-v2.0.0-windows-outlook.md` (rev. 18) se eliminó al
cerrar la fase: era un artefacto de proceso y sigue disponible en el historial de git
(commit `0784651`).

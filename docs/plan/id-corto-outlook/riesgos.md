# Riesgos del plan

Riesgos de la ejecución del plan. Los riesgos del producto están en la sección "Riesgos" de la unidad.

- **R-01. El driver `outlook` usa el `EntryID` como clave interna en muchos sitios.** Probabilidad alta, impacto alto: un punto sin traducir rompe `show`, adjuntos o destinatarios con uids cortos. Mitigación: M02 aísla la traducción en dos funciones antes del cambio y prueba un traductor no trivial; M05 solo cambia esas dos funciones.
- **R-02. Goldens de Outlook con uids largos.** Probabilidad alta, impacto medio: TC-02 y TC-09 fallan en cuanto cambia el uid. Mitigación: M05 los regenera con `MAILQUERY_UPDATE_GOLDENS=1` y su evidencia justifica que solo cambian el uid, `last_uid` y los directorios de `cached_path`.
- **R-03. Tests que usan el backend de Outlook sin home.** Probabilidad media, impacto alto: escribirían en el `~/.mailquery` real. Mitigación: D-06 (en memoria sin home) y el gate de solo lectura `tests/test_readonly.py`.
- **R-04. SQLite y el hilo trabajador de los plugins.** Probabilidad media, impacto medio. Mitigación: D-15 y el caso UT-NID-04.02.
- **R-05. Ciclo de importación entre `native_ids` y `mailquery.plugins`.** Probabilidad media, impacto medio. Mitigación: D-14 y el caso UT-PL-05.04.
- **R-06. Diferencias de plataforma en permisos y bloqueos.** Probabilidad media, impacto bajo: Windows no tiene permisos POSIX. Mitigación: aserciones de permisos condicionales (salto permitido por `docs/tests/infrastructure.md`, sección 5) y casos de `E_PERMISSION` con un sustituto inyectado que corren igual en los tres sistemas.
- **R-07. Tiempo de la suite.** Probabilidad baja, impacto bajo: los casos de bloqueo esperarían 5 s. Mitigación: `BUSY_TIMEOUT_SECONDS` se acorta en los tests y un caso aparte comprueba que el valor por defecto es 5.
- **R-08. Entorno local distinto de la CI.** Probabilidad media, impacto bajo: sin `css-inline` o con un `mailquery` instalado aparecen fallos ajenos. Mitigación: D-02 y la línea base de F0.
- **R-09. Archivos centrales tocados por varios milestones.** Probabilidad media, impacto medio: `cli.py`, `search.py`, `outlook.py` y algunos tests pasan por dos o tres milestones. Mitigación: nunca en la misma oleada (tabla de propiedad del plan maestro); cada milestone sale del tip del lote con los anteriores integrados.
- **R-10. `develop` avanza durante el plan.** Probabilidad media, impacto medio. Mitigación: al cerrar cada lote, el orquestador integra `develop` en la rama de la unidad antes de empujar, y vuelve a correr la suite.

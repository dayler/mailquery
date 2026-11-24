# Decisiones, riesgos y respuestas del dueño — espera-del-lock

## Decisiones abiertas

Ninguna.

## Decisiones aplicadas

- **D-01.** El dueño aprobó la unidad el 2026-11-24. El archivo de la unidad sigue en `borrador`, sin commit y con IDs marcadores (`RF-x1`, `AC-x1`, `AC-x2`): aplicarle la aprobación y sustituir los marcadores en el plan son las tareas 1 y 2 de la fase 0.
- **D-02.** La prueba manual del checklist de la unidad (dos sesiones, veinte llamadas solapadas) la ejecuta el dueño en macOS y en Windows; basta su confirmación y no se copia ningún log a la evidencia. No es un AC ni entra en la suite.

- **D-03.** `pyproject.toml` no cambia: la unidad es `menor` y se suma a la versión 3.0.0 que `develop` ya anuncia (`3.0.0a3`).
- **D-04.** El workflow de CI no cambia: ya corre solo en PR y en push a `develop`, con cancelación de corridas y tiempo límite.
- **D-05.** `sleep` recibe segundos, como `time.sleep`; los tests comparan las pausas en milisegundos enteros.
- **D-06.** En los `hint` de sección o clave de primer nivel desconocida, `[lock]` va después de `[content]`.
- **D-07.** Las pruebas del AC-x1 con otro proceso reteniendo el lock usan un subproceso de Python que toma `RunLock` y duerme; las de pausas simuladas sustituyen `sleep`.
- **D-08.** Forma de los `hint` de un valor inválido de `[lock]`: fuera de rango, `valid range: <mín>..<máx>`; de otro tipo, `set <clave> to an integer between <mín> and <máx>` (para `backoff_factor`, `a number`). Es la forma del resto del esquema; los textos de `_parse_int` no cambian.
- **D-09.** "Sin decimales" es truncar la pausa en milisegundos (respuesta del dueño).
- **D-10.** Las pruebas que necesitan un `search` o un `new` con éxito en otro proceso usan el mecanismo de `_LAUNCHER` de `tests/test_cli.py`; la de MCP usa el servidor en proceso con un runner que cuenta las ejecuciones, porque el proceso hijo del servidor real no tiene acceso al fixture.
- **D-11.** El subagente escribe y confirma su evidencia cruda en `work/M<NN>-evidencia.md`; el orquestador redacta `evidence/M<NN>.md` a partir de ella.

## Riesgos

- **R-01. Pruebas con tiempo real.** Los casos con el lock retenido 2 s y 3 s añaden unos 10 s por job (el test existente con el lock real declara `retries = 0` para no sumar 4,65 s) y su cota superior (2 s) puede fallar en un runner cargado. Mitigación: medir con reloj monótono solo alrededor del comando, arrancar la medida cuando el proceso que retiene confirma que tiene el lock, y dejar todo lo demás a las pruebas con pausas simuladas.
- **R-02. Dobles de `RunLock` en los tests.** `tests/test_cli.py` sustituye `RunLock` por dobles con el constructor actual; el parámetro nuevo los rompe. Mitigación: M03 los adapta en su alcance.
- **R-03. Descriptor del lock entre reintentos.** Un descriptor abierto que no se cierra al agotar los reintentos o al interrumpirse deja el archivo abierto en Windows. Mitigación: casos de M02 para reintentos agotados e interrupción.
- **R-04. Rangos de línea desfasados.** La unidad aún puede cambiar antes de aprobarse. Mitigación: D-01; cada subagente recoloca los rangos por encabezado.

## Respuestas del dueño

- **2026-11-24. ¿Cómo queda el plan con la unidad en `borrador`?** "La apruebo ahora." (D-01)
- **2026-11-24. ¿Qué regla vale para las pausas "sin decimales"?** Truncar. (D-09)
- **2026-11-24. ¿Quién ejecuta la prueba manual y dónde queda el log?** "Yo en ambas plataformas; basta con mi confirmación, no es necesario copiar nada a evidencias." (D-02)

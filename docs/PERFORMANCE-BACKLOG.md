# Pendientes de rendimiento — presupuesto p95

Estado: **abierto**. Documento de seguimiento para futuras versiones. No cambia el
PRD: el presupuesto p95 de macOS (§19 de [`PRD.md`](PRD.md)) sigue vigente y **hoy no se
cumple** para `mailboxes` ni para `show` en equipos con un store grande.

Medición del 2026-11-04, `develop` @ `11b81fa`, Mac del dueño, macOS 27.0.1 arm64,
Python 3.15.2 (venv de `pipx`), `mailquery 2.0.0 (backend apple_mail)`. Store: 3 cuentas,
44 carpetas, 148.054 mensajes (Gmail 30/137.873; iCloud 10/10.178; `On My Device` 4/3).

## Cómo se mide

`SMOKE-NEW.07` (`tests/test_smoke.py`) ejecuta cada comando 20 veces (10 en `mailboxes`)
y compara el p95 por rango más cercano del `duration_ms` que la CLI registra en
`event=end` — conexión al store + trabajo del comando, sin el arranque del intérprete ni
el lanzador de `pipx` (`src/mailquery/cli.py:545`); `doctor`, que no registra
`duration_ms`, se mide en tiempo de pared. El tiempo de pared se imprime solo como
información. Reproducción: `python3 -B -m unittest tests.test_smoke -v` y leer el bloque
«SMOKE budgets» de la salida (requiere Acceso total al disco para la app que lanza los
tests).

## Resultado

| Comando | Presupuesto p95 (macOS) | Medido | Estado |
|---------|-------------------------|--------|--------|
| `mailboxes` | < 150 ms | 169–216 ms (10 corridas sueltas: 169, 200, 191, 173, 185, 170, 188, 191, 198, 183 ms; la suite da 209–216 ms) | **no cumple**, sistemático |
| `show` | < 150 ms | 165–200 ms | **no cumple**, al límite |
| `search` | < 500 ms | 337 ms | cumple |
| `new` | < 500 ms | 242–295 ms | cumple |
| `doctor` | < 2 s | 420 ms (pared) | cumple |
| `search --text` | < 3 s | 285 ms | cumple |

Nota metodológica: con n = 10 el p95 por rango más cercano es la corrida más lenta, así
que un solo pico hace fallar `mailboxes`; con n = 20 (`show`) es la segunda más lenta.

## Diagnóstico

- `mailboxes` recorre **todas** las carpetas de **todas** las cuentas para publicar
  contadores, incluidas las no declaradas (`included: false`), porque RF-03 lista cuentas
  y carpetas aunque no estén en `[scope]` (`run_mailboxes`, `src/mailquery/search.py`).
  Con 44 carpetas y 148.054 mensajes el costo ronda 170–200 ms.
- `show` abre el mensaje: cabeceras + cuerpo `.emlx` + nombres de adjuntos.
- El presupuesto de 150 ms viene del spike de macOS (anexo A.9, citado en
  [`Walkthrough-w5-polish.md`](archive/2026-11-04-Walkthrough-w5-polish.md) §3), validado
  «en proceso»; es probable que se midiera con menos cuentas y mensajes.
- Hipótesis sin verificar: las mediciones de arriba se tomaron dentro del sandbox del
  harness, que puede añadir latencia de I/O; falta la medición sin sandbox en la
  Terminal del dueño.

## Impacto

`SMOKE-NEW.07` falla en macOS con Mail real y un store de este tamaño. La CI no lo
detecta: SMOKE se salta en los runners alojados (Linux; macOS sin store `V9`/`V10`/`V11`;
Windows sin Outlook clásico). No hay fallo funcional: datos, garantía de solo lectura y
contadores intactos.

## Cómo se cierra (futuras versiones)

1. Medir sin sandbox en el Mac del dueño (10 corridas de `mailboxes`, 20 de `show`) y
   anotar aquí el resultado.
2. Si sigue por encima: optimizar `mailboxes` (p. ej. contadores agregados en una sola
   consulta, o lectura diferida de las carpetas no declaradas, sin romper RF-03) y/o
   `show`; validar que no cambia la salida ni el gate de solo lectura.
3. Si el presupuesto no es realista para stores grandes, revisar §19 del PRD con
   aprobación del dueño (decisión de producto).
4. Cerrar este documento cuando `SMOKE-NEW.07` pase en un Mac con un store comparable o
   cuando §19 se actualice, dejando aquí la nueva medición.

## Referencias

- [`PRD.md` §19](PRD.md) — presupuestos p95.
- [`tests/test_smoke.py`](../tests/test_smoke.py) — SMOKE-NEW.07.
- [`src/mailquery/search.py`](../src/mailquery/search.py) — `run_mailboxes`.
- [`src/mailquery/cli.py`](../src/mailquery/cli.py) — `duration_ms` de `event=end`.
- [`Walkthrough-w5-polish.md`](archive/2026-11-04-Walkthrough-w5-polish.md) §3 —
  medición de rendimiento en Windows.

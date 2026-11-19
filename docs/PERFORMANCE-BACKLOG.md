# Pendientes de rendimiento — presupuesto p95

Estado: **abierto**. Documento de seguimiento para futuras versiones. No cambia el
PRD: el presupuesto p95 de macOS (§19 de [`PRD.md`](PRD.md)) sigue vigente. La
medición del 2026-11-14 con la salida por defecto de `3.0.0` cumple los
presupuestos de `search`, `new`, `show` y `mailboxes` sin contadores. El
pendiente abierto queda limitado a `mailboxes --fields total` o `unread` (sin
aserción de presupuesto) y al acierto de caché de `attachment` en Outlook (126 ms
frente a < 50 ms, «Medición del 2026-11-14 en Windows»). La medición en Windows
con Outlook clásico cumple el resto de presupuestos, incluida la extracción real
de adjuntos.

`mailboxes` ya solo cuenta mensajes cuando se piden los contadores con
`--fields total` o `unread`; sin ellos el comando lista el catálogo de carpetas sin
leer ningún mensaje. El pendiente de rendimiento de `mailboxes` queda por tanto
limitado a esas dos variantes con contadores; la medición de la salida por
defecto y de la variante con contadores está en «Medición del 2026-11-14».

Medición **histórica** del 2026-11-04, `develop` @ `11b81fa`, Mac del dueño, macOS
27.0.1 arm64, Python 3.15.2 (venv de `pipx`), versión medida `mailquery 2.0.0`
(`backend apple_mail`). Store: 3 cuentas, 44 carpetas, 148.054 mensajes (Gmail
30/137.873; iCloud 10/10.178; `On My Device` 4/3).

## Presupuestos de adjuntos (PRD §19)

**Tabla: Presupuesto p95 de `mailquery attachment` (`3.0.0`, todavía no publicado)**

| Operación | Apple Mail | Outlook | Plugin local | Plugin remoto |
|-----------|------------|---------|--------------|---------------|
| `attachment` acierto de caché (archivo local) | < 50 ms | < 50 ms | < 50 ms | < 50 ms |
| `attachment` 1 adjunto ≤ 5 MB | < 200 ms | < 600 ms | sin objetivo fijo | sin presupuesto (red) |
| `attachment --all` de N adjuntos | presupuesto × N (lineal) | presupuesto × N (lineal) | sin objetivo fijo | sin presupuesto (red) |

Un plugin local solo está acotado por el timeout de metadatos/extracción
(RNF-21): 30 s por operación de metadatos y `[attachments].timeout_seconds`
(60 s por defecto, 10–600) por adjunto. Un plugin remoto no tiene objetivo de
latencia. Ese tope acota el peor caso y se registra como riesgo aceptado en el
PRD.

## Cómo se mide


`SMOKE-NEW.07` (`tests/test_smoke.py`) ejecuta cada comando 20 veces (10 en `mailboxes`)
y compara el p95 por rango más cercano del `duration_ms` que la CLI registra en
`event=end` — conexión al store + trabajo del comando, sin el arranque del intérprete ni
el lanzador de `pipx` (`src/mailquery/cli.py:545`); `doctor`, que no registra
`duration_ms`, se mide en tiempo de pared. `search --fields snippet` comparte el
presupuesto de `search`. `mailboxes --fields total,unread` se mide de forma
informativa, 5 corridas y sin aserción, porque el coste de los contadores es el
pendiente abierto. El tiempo de pared se imprime solo como información.
Reproducción: `python3 -B -m unittest tests.test_smoke -v` y leer el bloque
«SMOKE budgets» de la salida (requiere Acceso total al disco para la app que lanza los
tests).

## Resultado (medición histórica del 2026-11-04)

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

- `mailboxes --fields total` o `--fields unread` recorre **todas** las carpetas de
  **todas** las cuentas para publicar contadores, incluidas las no declaradas
  (`included: false`), porque el comando lista cuentas y carpetas aunque no estén en
  `[scope]` (`run_mailboxes`, `src/mailquery/search.py`). Con 44 carpetas y 148.054
  mensajes el costo ronda 170–200 ms. Sin `--fields total` ni `unread` no se cuenta
  ningún mensaje: el catálogo se lee sin contadores y el coste de esa parte es el de
  listar las carpetas.
- `show` abre el mensaje: cabeceras + cuerpo `.emlx` + nombres de adjuntos. En Apple Mail,
  `attachments()` decodifica cada adjunto para calcular `size_bytes`
  (`emlx.parse_attachments`), así que un mensaje con adjuntos grandes alarga `show`.
- El presupuesto de 150 ms viene del spike de macOS (citado en
  [`Walkthrough-w5-polish.md`](archive/2026-11-04-Walkthrough-w5-polish.md) §3), validado
  «en proceso»; es probable que se midiera con menos cuentas y mensajes.
- Hipótesis sin verificar: las mediciones de arriba se tomaron dentro del sandbox del
  harness, que puede añadir latencia de I/O; falta la medición sin sandbox en la
  Terminal del dueño.

## Medición del 2026-11-11 (adjuntos integrados)

Rama `feature/prd-v2.1-w3` con los adjuntos integrados, Mac del dueño, macOS 27.0.1
arm64, Python 3.12.13, versión `__version__` = 2.0.1, store real con 1 cuenta incluida. `SMOKE-NEW.07`, 20 corridas por comando (10 en
`mailboxes`), p95 por rango más cercano del `duration_ms`:

| Comando | Presupuesto p95 | Medido | Estado |
|---------|-----------------|--------------|--------|
| `mailboxes` | < 150 ms | 218 ms | **no cumple** (deuda conocida) |
| `show` | < 150 ms | 164 ms | **no cumple** (deuda conocida) |
| `search` | < 500 ms | 312 ms | cumple |
| `new` | < 500 ms | 266 ms | cumple |
| `doctor` | < 2 s (pared) | 443 ms (pared) | cumple |
| `attachment` caché / extracción | §19 | sin medir: no hubo equipo Windows con Outlook clásico; cubierto por el doble y por `SMOKE-ATT-AM`/`SMOKE-ATT-OL` (se saltan donde no aplica) | medido el 2026-11-14 en Windows (ver «Medición del 2026-11-14 en Windows») |

Los dos fallos de `SMOKE-NEW.07` (`mailboxes`, `show`) son la misma deuda de la
medición anterior; los adjuntos no la introdujeron. La extracción real de Outlook
(materialización COM) y el presupuesto de `attachment` siguen sin medirse en un
equipo Windows (riesgo aceptado, PRD §23.1).

## Medición del 2026-11-14 (3.0.0a0)

Mac del dueño, macOS 27.0.1 arm64, Python 3.12.13 (`.venv`), paquete instalado con
`pipx` desde el commit `294805d`, `mailquery 3.0.0a0` (`backend apple_mail`). Store
real: 44 carpetas y 148.678 mensajes (solo recuentos). `SMOKE-NEW.07`, 20 corridas
por comando (10 en `mailboxes`), p95 por rango más cercano del `duration_ms` y
`doctor` en tiempo de pared, sin otras corridas en marcha:

| Comando | Presupuesto p95 (macOS) | p95 medido | Estado |
|---------|-------------------------|------------|--------|
| `doctor` | < 2 s (pared) | 0,356 s (pared) | cumple |
| `mailboxes` sin contadores | < 150 ms | 130 ms | cumple |
| `search` (fila mínima) | < 500 ms | 128 ms | cumple |
| `search --fields snippet` | < 500 ms | 257 ms | cumple |
| `new` (fila mínima) | < 500 ms | 143 ms | cumple |
| `show` | < 150 ms | 53 ms | cumple |
| `search --text` | < 3 s | 133 ms | cumple |

Medición informativa, sin aserción: `mailboxes --fields total,unread` da un p95 de
229 ms (n = 5) en este store. Es el pendiente de los contadores: si se le aplicara
el presupuesto de 150 ms, no lo cumpliría. Sin `total` ni `unread` no se cuenta
ningún mensaje y el comando cumple.

Los dos fallos históricos de `SMOKE-NEW.07` (`mailboxes` y `show`) no aparecen
en esta medición: `mailboxes` sin contadores ya no recorre todas las carpetas
para contar y `show` bajó con los cambios de salida de F3. **Windows no se
midió**: este host no tiene Outlook clásico, así que la extracción real de
adjuntos y su p95 siguen pendientes de un equipo Windows. `doctor` se midió sin
plugins: su p95 excluye las llamadas a plugins y este equipo no tiene plugins
reales. El tamaño del store es comparable al de la medición histórica (148.054
mensajes y 44 carpetas), así que la medición de macOS se considera
representativa.

## Medición del 2026-11-14 en Windows (3.0.0a1)

Windows 11 Enterprise (build 26200) x64, Outlook clásico 16.0.20527 abierto,
Python 3.14.7 (`.venv`), paquete instalado con `pipx` desde el commit `fd62c8a`,
`mailquery 3.0.0a1` (`backend outlook`). Store real: 38 carpetas y 134.165
mensajes (solo recuentos); alcance de la prueba: 1 cuenta con 1 carpeta incluida
de 1.211 mensajes. `SMOKE-NEW.07`, 20 corridas por comando (10 en `mailboxes`),
p95 por rango más cercano del `duration_ms` y `doctor` en tiempo de pared, sin
otras corridas en marcha; `attachment` medido a mano con el mismo método (20
extracciones con `--force` y 20 aciertos de caché):

| Comando | Presupuesto p95 (Windows) | p95 medido | Estado |
|---------|---------------------------|------------|--------|
| `doctor` | < 3 s (pared) | 0,459 s (pared) | cumple |
| `mailboxes` sin contadores | < 1 s | 0,204 s | cumple |
| `search` (fila mínima) | < 1 s | 0,234 s | cumple |
| `search --fields snippet` | < 1 s | 0,258 s | cumple |
| `new` (fila mínima) | < 1 s | 0,202 s | cumple |
| `show` | < 0,5 s | 0,185 s | cumple |
| `search --text` | < 10 s | 0,238 s | cumple |
| `attachment` 1 adjunto ≤ 5 MB (19.205 bytes) | < 600 ms | 144 ms | cumple |
| `attachment` acierto de caché | < 50 ms | 120 ms y 126 ms (dos series de 20) | **no cumple** (deuda abierta) |

Medición informativa, sin aserción: `mailboxes --fields total,unread` da un p95 de
505 ms (n = 5) en este store.

**Deuda abierta: acierto de caché de `attachment` en Outlook.** Cada acierto
tarda entre 106 y 126 ms, de forma estable en dos series de 20. Antes de servir
la caché, el comando se conecta a Outlook por COM y lista los adjuntos del
mensaje para aplicar la regla de bloqueo de nombres (`PRD.md` §10.3.1), así que
el acierto de caché no evita el coste de COM y no baja de 50 ms en este equipo.
No hay fallo funcional: el archivo servido coincide con su SHA-256 del manifiesto
y los contadores de Outlook no cambian. El coste de las cabeceras de A6 en
`search`/`new` queda dentro del presupuesto (`search` 0,234 s).

## Impacto

`SMOKE-NEW.07` cumple en macOS con Mail real y este store en la medición del
2026-11-14.
La variante `mailboxes --fields total` o `unread` (229 ms) sigue por encima del
presupuesto de 150 ms y no tiene aserción. La CI no lo detecta: SMOKE se salta en
los runners alojados (Linux; macOS sin store `V9`/`V10`/`V11`; Windows sin Outlook
clásico). No hay fallo funcional: datos, garantía de solo lectura y contadores
intactos. En Windows, el acierto de caché de `attachment` (126 ms) supera el
presupuesto de 50 ms; la CI tampoco lo detecta, porque SMOKE-ATT-OL comprueba el
contrato y no la latencia.

## Cómo se cierra (futuras versiones)

1. Hecho el 2026-11-14: medir sin sandbox en el Mac del dueño (10 corridas de
   `mailboxes`, 20 de `show`) y anotar aquí el resultado; ambos cumplen.
2. Si la variante con contadores sigue por encima: optimizar el recuento de
   `mailboxes --fields total` o `unread` (p. ej. contadores agregados en una sola
   consulta) y/o `show`; validar que no cambia la salida ni el gate de solo lectura.
3. Si el presupuesto no es realista para stores grandes, revisar §19 del PRD con
   aprobación del dueño (decisión de producto).
4. Acierto de caché de `attachment` en Outlook: decidir (decisión de producto)
   entre optimizar el camino de caché (p. ej. evitar la conexión COM cuando el
   manifiesto ya permite aplicar la regla de bloqueo) o revisar el presupuesto de
   §19 para Outlook, y medir de nuevo en un equipo Windows con Outlook clásico.
5. Cerrar este documento cuando `mailboxes --fields total` o `unread` cumpla en un
   Mac con un store comparable y el acierto de caché de `attachment` cumpla en
   Outlook, o cuando §19 se actualice, dejando aquí la nueva medición.

## Referencias

- [`PRD.md` §19](PRD.md) — presupuestos p95.
- [`tests/test_smoke.py`](../tests/test_smoke.py) — SMOKE-NEW.07 y SMOKE-ATT.
- [`PRD.md` §19](PRD.md) — presupuestos de `attachment`.
- [`src/mailquery/search.py`](../src/mailquery/search.py) — `run_mailboxes`.
- [`src/mailquery/cli.py`](../src/mailquery/cli.py) — `duration_ms` de `event=end`.
- [`Walkthrough-w5-polish.md`](archive/2026-11-04-Walkthrough-w5-polish.md) §3 —
  medición de rendimiento en Windows.

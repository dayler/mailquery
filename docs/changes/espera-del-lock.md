---
aliases: ["Espera del lock de ejecución"]
tags: [cambio]
---

# Espera del lock de ejecución

**Tipo:** cambio
**Base:** PRD 2.6
**Fecha:** 2026-11-24
**Aprobación:** Ariel Salazar Hinojosa, 2026-11-24
**Paquete:** 3.0.0 (menor)

## Estado

conciliado (2026-11-24)

## Contexto

### Problema

- **Dos ejecuciones a la vez se rechazan.** El lock de ejecución es exclusivo y no espera (RF-20): la segunda ejecución termina al instante con `E_LOCKED` (exit 5).
- **El reintento queda en manos de quien llama.** Con la skill, el modelo ve un error y decide si repite el comando; con el servidor MCP, la herramienta devuelve `isError: true` y el servidor no reintenta. En los dos casos se gasta un turno del modelo en un fallo que se habría resuelto solo.
- **El choque es corto y frecuente.** Un comando retiene el lock entre 130 y 500 ms (medido el 2026-11-24 en macOS). Basta con dos sesiones del harness abiertas, una sesión con MCP y otra con la CLI, un agente que lanza llamadas en paralelo o una tarea programada que coincide con el uso interactivo.

### Solución elegida

- **Reintentar en lugar de rechazar.** Un comando que encuentra el lock ocupado lo reintenta un número limitado de veces, con una pausa antes de cada reintento.
- **Pausas crecientes.** Cada pausa es la anterior multiplicada por un factor, hasta un tope fijo de 5 segundos por pausa.
- **El backoff se configura en `config.toml`.** Se configuran el número de reintentos, la primera pausa y el factor. Ninguna clave hace falta en `config.toml`: sin declararlas valen los valores por defecto. Con cero reintentos, el comando se comporta como hoy.
- **Los valores por defecto están documentados.** La ayuda raíz, los README y el archivo de configuración de ejemplo los muestran, para que nadie tenga que declararlos para conocerlos.
- **El error no cambia.** Si los reintentos se agotan, el resultado sigue siendo `E_LOCKED` (exit 5); solo cambia su `hint`.
- **El lock protege lo mismo.** Sigue habiendo como mucho una ejecución a la vez sobre el estado de `~/.mailquery`.

### Alternativas descartadas

- **Configurar solo la espera total.** Una sola clave con el tiempo máximo deja fijos la primera pausa y el ritmo de crecimiento, que son lo que hay que ajustar cuando cambian el número de sesiones o lo que tarda un comando.
- **Reintentar en el servidor MCP.** Solo cubre las llamadas MCP; la CLI que usa la skill seguiría fallando al instante.
- **Dejar el reintento al harness, como hoy.** Cada choque cuesta un turno del modelo y depende de que el modelo decida repetir.
- **Bloqueo del sistema operativo con tiempo límite.** `flock` y `msvcrt.locking` no ofrecen la misma espera con límite en macOS y en Windows; el reintento con pausas da el mismo comportamiento en las dos plataformas.
- **Lock de lector compartido y escritor exclusivo.** Quita la contención entre lecturas, pero `state.json` no es transaccional: sin el lock global hay que hacer atómicos el cursor de `new` y la caché de adjuntos. Es otro cambio de garantías.
- **Tope por pausa configurable.** Una cuarta clave para el tope sobra: con los rangos de las otras tres, un tope fijo basta para acotar la espera.
- **Opción de línea de comandos y parámetro de herramienta MCP.** Añade opciones comunes y cambia el esquema de las seis herramientas para valores que casi nunca cambian de una llamada a otra.

### Preguntas abiertas

Ninguna.

## Requerimiento

### Lo que no cambia

- El código `E_LOCKED`, su exit 5, su `message` (`another mailquery run is already in progress`) y la regla del harness de reintentar solo con exit 5 (§21.1).
- La ruta del lock, `~/.mailquery/locks/mailquery.lock`, y lo que protege.
- El bloqueo de la caché de ids nativos, con su propio tope de 5 s (RF-80).
- Los topes de los drivers (RNF-21): los reintentos del lock ocurren antes de abrir un driver y no cuentan para ellos.
- El contrato JSON de los comandos y el esquema de las herramientas MCP (RF-85).
- `--help`, `--version` y `mcp serve`, que no toman el lock.

### Elementos del PRD que cambian

- **RF-20.** El lock deja de rechazar al instante: un comando sale con código 5 solo cuando el lock sigue ocupado después de los reintentos de RF-89.
- **§15.6, fila "Lock".** La ruta sigue fija, y el tope de 5000 ms por pausa también; los reintentos se configuran en `[lock]`.
- **§12.7, ayuda raíz.** Nombra el reintento del lock, sus valores por defecto y la sección `[lock]`.
- **§17, fila "Lock ocupado".** Describe los reintentos, sus valores por defecto y el `hint` de los reintentos agotados.
- **§23, riesgo de varias sesiones del harness a la vez.** Su mitigación pasa a ser el reintento del lock; `E_LOCKED` queda para los reintentos agotados.

### Requerimientos

**RF-89. Reintento del lock de ejecución con pausas crecientes.** Prioridad S.

**Como** harness de agentes, **quiero** que un comando reintente tomar el lock de ejecución cuando lo encuentra ocupado, **para** que dos ejecuciones que coinciden no fallen por turnarse.

Condiciones:

- **Quién reintenta.** Los comandos de datos: `search`, `new`, `show`, `attachment` y `mailboxes`.
- **Sección.** La sección `[lock]` de `config.toml` es opcional y todas sus claves también; una clave que no se declara vale su valor por defecto.
- **`retries`.** Número de reintentos después del primer intento: entero de 0 a 10, por defecto `5`.
- **`initial_delay_ms`.** Pausa antes del primer reintento, en milisegundos: entero de 10 a 5000, por defecto `150`.
- **`backoff_factor`.** Factor por el que crece cada pausa respecto de la anterior: número entero o decimal de 1 a 10, por defecto `2`. Con `1`, todas las pausas son iguales.
- **Tope por pausa.** Ninguna pausa dura más de 5000 ms. El tope es fijo: no se configura.
- **Valor inválido.** Un valor fuera de rango o de otro tipo da `E_CONFIG_INVALID` (exit 2) en los comandos de datos, con el rango válido en el `hint`, como el resto del esquema (§15.3).
- **Clave desconocida.** Una clave desconocida dentro de `[lock]` da `E_CONFIG_INVALID` (exit 2) en los comandos de datos, con las claves admitidas en el `hint`.
- **Sección admitida.** Los `hint` de sección o clave de primer nivel desconocida nombran `[lock]` entre las secciones admitidas.
- **Errores previos.** Un error que el comando detecta antes de tomar el lock (uso, configuración, alcance) llega sin espera. Uno que detecta con el lock tomado llega después de los reintentos; si se agotan, el comando da `E_LOCKED` en su lugar.
- **Primer intento.** El comando intenta tomar el lock al llegar; si está libre, no espera nada.
- **Qué se reintenta.** Se reintenta el intento de tomar el lock que falla, que es el caso que hoy da `E_LOCKED`. No poder crear o abrir el archivo del lock sigue dando `E_PERMISSION` al instante, sin reintento.
- **Pausas.** Antes del reintento número `n` hay una pausa de `initial_delay_ms × backoff_factor^(n−1)` milisegundos, sin decimales y como mucho 5000. Con los valores por defecto, las pausas son de 150, 300, 600, 1200 y 2400 ms: 4650 ms en total.
- **Lock conseguido.** El comando empieza a trabajar en cuanto toma el lock; su salida y su código de salida son los de una ejecución sin espera.
- **Reintentos agotados.** Si el último reintento falla, el error es `E_LOCKED` (exit 5), con el `message` `another mailquery run is already in progress` y el `hint` `still held after <R> retries: <ruta>; retry later ([lock] in ~/.mailquery/config.toml sets the retries)`, donde `<R>` es el valor de `retries` y `<ruta>` la del archivo del lock.
- **Sin reintentos.** Con `retries = 0`, el comando hace un solo intento y, si falla, da `E_LOCKED` con el mismo `message` y el `hint` `wait for the running invocation to finish and retry (the harness should only retry exit code 5)`.
- **Interrupción.** Un comando interrumpido durante una pausa termina sin haber tomado el lock y sin leer ni escribir el estado.
- **Orden.** Los reintentos no garantizan el orden de llegada: toma el lock el primer comando que lo reintenta después de liberarse.
- **`doctor`.** El chequeo `lock` hace un solo intento, con cualquier configuración, e informa `available` o `held by another mailquery process` en el acto. Un `[lock]` inválido aparece en el chequeo `config`, como el resto de la configuración, y no cambia el chequeo `lock`.
- **Ayuda.** La ayuda raíz (`mailquery --help`) dice, junto a la línea de configuración, que un lock ocupado se reintenta, con los tres valores por defecto y el nombre de la sección: `Lock: a busy run lock is retried 5 times, pausing 150 ms and doubling each time ([lock] in config.toml)`. Para no pasar del ancho de 100 columnas de la ayuda, el texto ocupa dos líneas: la segunda, `([lock] in config.toml)`, va sangrada hasta debajo del texto de la primera, como las continuaciones de `Output:`.
- **MCP.** Una llamada MCP reintenta lo que reintenta su comando: el servidor no añade espera ni reintento propios. `mcp serve` no lee `[lock]`: arranca aunque la sección sea inválida, y entonces cada llamada devuelve el `E_CONFIG_INVALID` de su comando.

Se comprueba con AC-79 y AC-80.

### Configuración

Ninguna de las tres claves hace falta en `config.toml`. Sin sección `[lock]`, el comportamiento es el de este bloque:

**Figura: Sección `[lock]` con sus valores por defecto**

```toml
[lock]
retries = 5                    # 0..10; 0 = un solo intento
initial_delay_ms = 150         # 10..5000
backoff_factor = 2             # 1..10, entero o decimal
```

### Interfaz de los módulos

- `LockConfig`: `retries: int = 5`, `initial_delay_ms: int = 150`, `backoff_factor: float = 2.0`. `Config` añade el campo `lock: LockConfig`.
- `RunLock(home: Path, retry: LockConfig | None = None, *, sleep: Callable[[float], None] = time.sleep)`: parámetros nuevos; sin `retry` hace un solo intento, como hoy. `acquire() -> None` reintenta según `retry` y pausa con `sleep`, que una prueba puede sustituir.
- `mailquery.cli` construye el lock de los comandos de datos con `config.lock`, y el del chequeo `lock` de `doctor` sin `retry`.

### Riesgos

- **Un comando puede quedarse sin turno.** Sin orden de llegada, con muchas ejecuciones a la vez alguna puede agotar sus reintentos aunque el lock se haya liberado varias veces. Mitigación: sigue terminando con `E_LOCKED` (exit 5), que el harness ya reintenta; el caso esperado son dos o tres sesiones.
- **Las últimas pausas son largas.** Con los valores por defecto, las dos últimas pausas duran 1,2 y 2,4 s: un comando puede seguir en pausa con el lock ya libre. Mitigación: los choques esperados, de 130 a 500 ms, se resuelven en los tres primeros reintentos; un `backoff_factor` menor acorta las pausas.
- **Un fallo por lock ocupado tarda más en llegar.** Lo que hoy falla en milisegundos tarda la suma de las pausas: 4,65 s por defecto y hasta 50 s con los valores máximos. Mitigación: `retries = 0` recupera el rechazo inmediato.
- **Una llamada MCP dura más.** A su duración se suman las pausas, y el servidor atiende en serie. Mitigación: los rangos de las claves acotan la suma, y por defecto es de 4,65 s.

### Cambios visibles

- En ambas plataformas: un comando que encuentra el lock ocupado lo reintenta hasta 5 veces, durante 4,65 s como mucho, antes de fallar con `E_LOCKED`; la sección `[lock]` y sus claves `retries`, `initial_delay_ms` y `backoff_factor` son nuevas en `config.toml`, todas opcionales; la ayuda raíz nombra el reintento y sus valores por defecto.

## Criterios de aceptación

**AC-79.** En macOS y en Windows, con el lock retenido por otro proceso durante 2 s y sin sección `[lock]`: `search` termina con exit 0 después de liberarse el lock, y su salida es la de una ejecución sin espera salvo `generated_at` y `scan.duration_ms`; la misma llamada por MCP devuelve ese resultado con `isError: false` y una sola ejecución del comando. Con `retries = 2`, `initial_delay_ms = 100` y el lock retenido 3 s: `E_LOCKED` (exit 5), no antes de 300 ms ni después de 2 s, con el `message` y el `hint` de los reintentos agotados, que nombra los reintentos y la ruta del lock. Con `retries = 0`: `E_LOCKED` sin esperar, con el `hint` de "Sin reintentos". Con las pausas simuladas y el lock siempre ocupado: sin sección `[lock]` hay seis intentos y las pausas son de 150, 300, 600, 1200 y 2400 ms; con `retries = 3`, `initial_delay_ms = 1000` y `backoff_factor = 3`, de 1000, 3000 y 5000 ms; con `retries = 3`, `initial_delay_ms = 100` y `backoff_factor = 1.5`, de 100, 150 y 225 ms. Si el archivo del lock no se puede abrir, el comando da `E_PERMISSION` sin esperar. Con el lock retenido, el chequeo `lock` de `doctor` informa `held by another mailquery process` sin esperar. Dos `new` lanzados a la vez, cada uno de menos de 2 s, terminan los dos con exit 0, y cada mensaje nuevo sale en uno solo de los dos.

**AC-80.** `retries` acepta `0` y `10`; `initial_delay_ms`, `10` y `5000`; `backoff_factor`, `1`, `1.5` y `10`. Cada comando de datos da `E_CONFIG_INVALID` (exit 2) con el rango válido en el `hint` con `retries` igual a `-1`, `11`, `"5"`, `5.0` o `true`; con `initial_delay_ms` igual a `9` o `5001`; con `backoff_factor` igual a `0.5`, `11`, `"2"` o `true`. La clave `max_delay_ms` es una clave desconocida. Una clave desconocida en `[lock]` da `E_CONFIG_INVALID` con las claves admitidas en el `hint`, y el `hint` de una sección desconocida nombra `[lock]`. Una sección `[lock]` que solo declara `retries` usa los valores por defecto de las demás claves. Con `retries = 11`, `doctor` informa el error en su chequeo `config` y su chequeo `lock` responde sin esperar; `mailquery mcp serve` arranca, y una llamada a `search` devuelve `E_CONFIG_INVALID` con `isError: true`. `mailquery --help` muestra la línea `Lock:` con los tres valores por defecto y la sección `[lock]`.

## IDs

- Crea: RF-89, AC-79, AC-80
- Elimina: —

## Dependencias

Ninguna

## Decisiones

- **¿Qué hace un comando cuando el lock de ejecución está ocupado?** (2026-11-24) Lo reintenta con pausas crecientes; si el lock sigue ocupado al agotar los reintentos, falla con `E_LOCKED` como antes.
- **¿Qué se configura del reintento?** (2026-11-24) El número de reintentos, la primera pausa y el factor de crecimiento; no la espera total, que resulta de ellos, ni el tope por pausa, que es fijo.
- **¿Dónde se configura?** (2026-11-24) Solo en `config.toml`, sin opción de la CLI ni parámetro de las herramientas MCP. Ninguna clave hace falta: lo que no se declara vale su valor por defecto.
- **¿Dónde se documentan los valores por defecto?** (2026-11-24) En la ayuda que corresponda, en los README y en la documentación pertinente.
- **¿La espera del lock va con el proceso hijo persistente del servidor MCP?** (2026-11-24) No: es una unidad propia. La del proceso hijo persistente se archivó sin aprobar.

## Glosario

- **Reintento del lock** (nuevo): nuevo intento de tomar el lock de ejecución que un comando de datos hace, tras una pausa creciente, cuando lo encuentra ocupado; el número de reintentos y las pausas se configuran en `[lock]` (RF-89).

## Conciliación con el PRD

**Tabla: Conciliación con el PRD**

| ID | Contrato | Archivo | Ancla | Qué cambia | Estado |
|---|---|---|---|---|---|
| RC-01 | Lock de ejecución | `06-requisitos-funcionales.md` | RF-20 | El comando sale con código 5 solo si el lock sigue ocupado después de los reintentos de RF-89. | conciliado |
| RC-02 | Requisito del reintento | `06-requisitos-funcionales.md` | después de RF-88 | Nueva subsección 6.13 con RF-89 y sus condiciones. | conciliado |
| RC-03 | Responsabilidad de `state.py` | `09-arquitectura.md` | `` `state.py` `` | El lock deja de describirse como no bloqueante: es un lock con reintentos y pausas crecientes (RF-89). | conciliado |
| RC-04 | Propiedades configurables | `15-configuracion.md` | después de `` `content.url_display` `` | Nuevas filas: la sección `[lock]` y las claves `lock.retries`, `lock.initial_delay_ms` y `lock.backoff_factor`, todas opcionales, con su tipo, su valor por defecto, su rango y su descripción (RF-89). | conciliado |
| RC-05 | Archivo completo de ejemplo | `15-configuracion.md` | después de `url_display = "neutralize"`; `El ejemplo de macOS muestra`; `# ([logging], [search]` | El ejemplo añade la sección `[lock]` con sus tres claves, sus valores por defecto y sus comentarios de rango; el párrafo que presenta el ejemplo y el comentario del ejemplo de Windows nombran `[lock]` entre las secciones comunes a las dos plataformas (RF-89). | conciliado |
| RC-06 | Valores fijos | `15-configuracion.md` | `Lock` | La fila dice que la ruta y el tope de 5000 ms por pausa son fijos y que los reintentos se configuran en `[lock]` (RF-89). | conciliado |
| RC-07 | Partición de la sección 15 | `15-2-stores-windows.md` (nuevo) | — | La subsección 15.7 pasa a este archivo sin cambiar su texto, para que `15-configuracion.md` no supere 300 líneas. | conciliado |
| RC-08 | Archivos del PRD | `00-indice.md` | `15 Configuración` | La fila enlaza los dos archivos de la sección 15. | conciliado |
| RC-09 | Ayuda raíz | `12.07-ayuda.md` | `Configuration: ~/.mailquery/config.toml` | Nueva línea `Lock:` después de la de configuración, con el reintento, sus tres valores por defecto y la sección `[lock]`, partida en dos líneas para no pasar de 100 columnas (RF-89). | conciliado |
| RC-10 | Chequeo `lock` de `doctor` | `12.08-doctor.md` | `### 12.8` | El párrafo "Formato de `detail`" dice que el chequeo `lock` hace un solo intento y no aplica los reintentos de `[lock]` (RF-89). | conciliado |
| RC-11 | Comportamiento con el lock ocupado | `17-comportamiento-errores.md` | `Lock ocupado` | La fila describe los reintentos con pausas crecientes, sus valores por defecto, `retries = 0` y el `hint` de los reintentos agotados; el caso de la caché de ids nativos no cambia (RF-89). | conciliado |
| RC-12 | Alcance de los criterios | `20-criterios-aceptacion.md` | `3. **Plugins, adjuntos` | El punto nombra el reintento del lock y su rango incluye AC-79 y AC-80. | conciliado |
| RC-13 | Criterios de aceptación | `20-criterios-aceptacion.md` | después de AC-78 | AC-79 y AC-80. | conciliado |
| RC-14 | Concurrencia | `21-harness.md` | `### 21.3 Idempotencia y concurrencia` | Nueva entrada: dos ejecuciones que coinciden se turnan con los reintentos del lock, y `E_LOCKED` queda para los reintentos agotados; la entrada de MCP dice que una llamada reintenta lo que su comando (RF-89). | conciliado |
| RC-15 | Cambios visibles en 3.0.0 | `22-versiones.md` | `**Tabla: Cambios visibles de 3.0.0 en ambas plataformas**` | Nueva fila: con el lock ocupado, antes `E_LOCKED` al instante y después hasta 5 reintentos con pausas crecientes, configurables en `[lock]` (RF-89). | conciliado |
| RC-16 | Riesgo de varias sesiones | `23-riesgos.md` | `Varias sesiones del harness a la vez` | La mitigación son los reintentos del lock; `E_LOCKED` solo aparece con los reintentos agotados y se reintenta (RF-89). | conciliado |
| RC-17 | Riesgos del reintento | `23-riesgos.md` | después de `Un harness lanza el servidor MCP` | Nuevas filas: un comando sin turno por falta de orden de llegada, las últimas pausas largas, un fallo por lock ocupado que tarda más en llegar y una llamada MCP que dura más mientras el servidor atiende en serie, con sus mitigaciones (RF-89). | conciliado |

## Documentos consumidores

- README.md: actualizado
- README.es.md: actualizado
- docs/INTERFACES.md: actualizado
- docs/config.example.toml: actualizado
- docs/security/threat-model.md: actualizado
- docs/tests/TEST-CATALOG.md: actualizado
- docs/tests/acceptance-matrix.md: actualizado
- docs/tests/state-backends.md: actualizado
- docs/tests/cli-config.md: actualizado
- docs/tests/docs-packaging.md: actualizado
- docs/tests/mcp-server.md: actualizado
- skills/mailquery/SKILL.md: sin cambio
- docs/recipes/: sin cambio

## Checklist de conciliación

**Tabla: Checklist de conciliación**

| ID | Ítem | Cómo se verifica | Estado |
|---|---|---|---|
| CL-01 | Cada fila de "Conciliación con el PRD" está aplicada en su archivo | Revisión fila por fila | cumplido |
| CL-02 | El resto del PRD no cambia | Diff del PRD limitado a los archivos de la tabla, el glosario, el Anexo D, la portada y el historial | cumplido |
| CL-03 | Los IDs de la unidad están creados y eliminados en el PRD, sin huecos ni referencias rotas | `doc_14` | cumplido |
| CL-04 | Las decisiones están en el Anexo D y el glosario está aplicado | Revisión de "Decisiones" y "Glosario" | cumplido |
| CL-05 | Los documentos consumidores están actualizados | Ninguno está `pendiente` | cumplido |
| CL-06 | No quedan textos obsoletos en el PRD ni en los documentos consumidores: "lock no bloqueante", `E_LOCKED` descrito como rechazo inmediato del lock de ejecución, y "más `E_LOCKED`" como efecto de varias sesiones | Búsqueda de cada texto | cumplido |
| CL-07 | El defecto registrado está cerrado | Su entrada de `docs/KNOWN-DEFECTS.md` | no aplica |
| CL-08 | La versión del documento, el historial y los próximos IDs libres están al día | Portada e `HISTORIAL.md` | cumplido |
| CL-09 | La suite pasa | Suite completa, con `doc_14` y `doc_15` | cumplido |
| CL-10 | Los valores por defecto de `[lock]` son los mismos en §15.1, §15.5, la ayuda raíz, `README.md`, `README.es.md` y `docs/config.example.toml` | Revisión cruzada de los seis textos | cumplido |
| CL-11 | Dos sesiones a la vez, veinte llamadas solapadas cada una, sin sección `[lock]`: ninguna termina con `E_LOCKED`; con `retries = 0`, las que coinciden sí | Prueba manual en macOS y en Windows, con su log | cumplido |

## Desviaciones aprobadas

- **Línea `Lock:` en dos líneas.** El texto de la condición "Ayuda" de RF-89 mide 103 columnas y la ayuda tiene un ancho máximo de 100: ocupa dos líneas, con la continuación sangrada; las palabras no cambian. Cambian la condición "Ayuda" y la fila RC-09. Aprobada por Ariel Salazar Hinojosa, 2026-11-24.
- **`scan.duration_ms` en AC-79.** La salida de `search` tras la espera es la de una ejecución sin espera salvo `generated_at` y `scan.duration_ms`, que cambia entre dos ejecuciones cualesquiera. Cambia AC-79. Aprobada por Ariel Salazar Hinojosa, 2026-11-24.

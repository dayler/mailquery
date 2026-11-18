# doctor

#### UT-DR-01 — `--failures` con todo correcto

Requisitos: AC-56 · Archivo: `tests/test_doctor.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `doctor --json --failures` ⇒ `{"ok": true, "command": "doctor", "generated_at": …, "checks": [], "not_evaluated": [], "plugins": [], "warnings": []}`, en ese orden de claves; exit 0. |

#### UT-DR-02 — `--failures` con un chequeo que falla

Requisitos: AC-56 · Archivo: `tests/test_doctor.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Apple Mail con `store` fallido (mock de TCC): `checks` solo con los que fallan (con su `detail`) y `not_evaluated` con `envelope_index`, `schema`, `readonly_strategy` y, con bloques declarados, `config`, en el orden habitual. |
| .02 | N | Outlook cerrado (doble): `checks` con `outlook` y `not_evaluated` con `stores`, `readonly_strategy` y `config`. |
| .03 | B | Un chequeo con `not evaluated: <causa concreta>` que no es `<chequeo> failed` se lista en `checks`, no en `not_evaluated` (D-05). |
| .04 | P | Exit 0 y `ok: true` en todos los casos. |

#### UT-DR-03 — `--failures` en texto

Requisitos: AC-56 · Archivo: `tests/test_doctor.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Todo bien ⇒ título, `Generated at`, `Checks:` y `all checks passed`, sin filas `[ok]` ni `Plugins:`. |
| .02 | N | Con fallos ⇒ una fila por chequeo que falla y la línea `not evaluated: <nombres>`; las secciones sin fallos se ocultan. |

#### UT-DR-04 — `doctor` sin `--failures`

Requisitos: AC-56, AC-57 · Archivo: `tests/test_doctor.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | JSON igual que antes salvo `plugins` (vacío sin plugins) y sin `not_evaluated`; texto igual salvo el título `mailquery doctor - environment and read-only diagnosis` y sin sección `Plugins:` cuando no hay plugins. |

#### UT-DR-05 — Sección de plugins

Requisitos: AC-61 · Archivo: `tests/test_doctor.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Plugin falso declarado con `doctor_checks()` válido: `plugins` con su `driver`, sus chequeos sin cambios y después `config` con la resolución de sus bloques. |
| .02 | N | Un bloque del plugin que no resuelve ⇒ `config` del plugin `ok: false` con `<clave>: <código>: <mensaje> (hint: …)`. |
| .03 | P | `checks[]` de primer nivel igual que sin el plugin salvo el detalle de `driver` y que `config` ya no lista sus bloques; con solo bloques de plugins, `config` de primer nivel `0 account block(s) declared for driver <nativo>` y `ok: true` cuando no falla ninguna de sus dependencias. |
| .04 | P | Varios plugins en el orden de su primer bloque. |
| .05 | B | `close()` del plugin lanza una excepción: el resultado del plugin y el resto del informe no cambian; exit 0. |

#### UT-DR-06 — Plugin que no pasa `driver` o no se abre

Requisitos: AC-61 · Archivo: `tests/test_doctor.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Plugin declarado incompatible: sus `checks` son solo `config` con `not evaluated: driver failed` y `doctor_checks()` no se llama. |
| .02 | N | El chequeo `driver` pasa pero `registry.open_drivers` falla al abrir el plugin: chequeo `plugin` `ok: false` con `E_PLUGIN_FAILED: …` y `config` con `not evaluated: plugin failed`; el resto del informe igual; exit 0. |

#### UT-DR-07 — `doctor_checks()` inválido o colgado

Requisitos: AC-61 · Archivo: `tests/test_doctor.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Lanza una excepción ⇒ chequeo `plugin` `ok: false` con `E_PLUGIN_FAILED: …`, seguido de `config`; el detalle del caso no mapeado es `E_PLUGIN_FAILED: <tipo>: <texto>`. |
| .02 | N | Devuelve algo que no es lista; un elemento que no es un dict; un elemento sin la forma; `ok` que no es booleano; `detail` que no es texto; un `name` repetido; un `name` `config` o `plugin`; un `detail` con `\n` o solo con `\r` ⇒ ídem. |
| .03 | N | No responde (plazo inyectado con `mock.patch("mailquery.plugins.api.METADATA_TIMEOUT_SECONDS", 0.05)`) ⇒ `plugin` `ok: false` con `timeout after 30 s: plugin '<driver>' did not respond`; el resto de `doctor` se muestra igual. |
| .04 | N | `accounts()` o `resolve_mailbox()` del plugin lanzan una excepción o no responden (mismo plazo inyectado) ⇒ `config` del plugin `ok: false` con el formato de error de RF-79; una cuenta malformada y un fallo del wrapper también se reportan; exit 0 y el resto del informe intacto. |

#### UT-DR-08 — Texto y `Result:`

Requisitos: AC-61 · Archivo: `tests/test_doctor.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | El texto muestra `Plugins:`, el driver y sus filas con el formato de `Checks:`, con líneas de hasta 100 caracteres. |
| .02 | P | `Result:` cuenta los chequeos de primer nivel y los de los plugins; exit 0. |

#### UT-DR-09 — `--failures` con plugins

Requisitos: AC-62 · Archivo: `tests/test_doctor.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Solo salen los plugins con algún chequeo que falla o sin evaluar, con sus `checks` que fallan y su `not_evaluated`; el texto pinta también la línea de no evaluados de un plugin. |
| .02 | P | Si solo falla un plugin (pasa el chequeo `driver` común y falla en su `doctor_checks()`): el texto muestra solo `Plugins:` (sin `Checks:`) y el JSON da `checks: []`, `not_evaluated: []` y el plugin. |
| .03 | P | Si no falla nada: `plugins: []` y en texto `all checks passed`. |

#### UT-DR-10 — Timeout COM con `--failures`

Requisitos: AC-56, AC-61, AC-62 · Archivo: `tests/test_outlook.py`

Plazo de 0,2 s, en subproceso con `run_cli.py`; el plugin se descubre por una distribución
`graph-0.1.0.dist-info` temporal en `PYTHONPATH`.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Doble de Outlook colgado en el chequeo `outlook` y un plugin falso declarado que no resuelve su cuenta: `doctor --json --failures` da exit 0, `checks` con `outlook` (timeout), `not_evaluated` con `stores`, `readonly_strategy` y `config`, y `plugins` con el plugin, su `config` que falla y `not_evaluated: []`; el texto con `--failures` muestra lo mismo. |
| .02 | P | Mismo cuelgue sin `--failures`: el JSON incluye `checks` completos y `plugins` completo después; exit 0. |

# M13 — `doctor --failures`, sección de plugins y diagnóstico sin *preflight*

**Lote:** I4 · rama del lote `integration/i4-mailboxes-doctor-close` · **Oleada:** W8 (sola)
**Rama:** `feature/m13-doctor-failures-plugins`, creada desde la punta de `integration/i4-mailboxes-doctor-close` (con M12 integrado) · **Worktree:** `../mailquery-wt/m13`
**Estado:** 🟡 (fases F1–F6 cerradas; pendiente de integración) (leyenda y protocolo en [`00-master-plan.md`](00-master-plan.md))

## 1. Objetivo

Añadir a `doctor` la opción `--failures` (RF-76) y la sección `plugins` con los chequeos de cada plugin declarado y la resolución de sus cuentas (RF-81), y pasar `doctor` de *preflight* a diagnóstico en la ayuda, el informe de texto, la skill y los README (RF-77).

## 2. Alcance

**Dentro (`src/mailquery/cli.py`, salvo indicación):**

1. **Sección `plugins` (RF-81):**
   - `doctor --json` añade, después de `checks`, `plugins`: un elemento por cada driver externo declarado en `[scope."<driver>:…"]`, en el orden de su primer bloque, con `driver` y `checks[]`; sin plugins declarados, `plugins: []`. `checks[]` de primer nivel no cambia (comunes y del backend nativo).
   - Por plugin: si su entrada del chequeo `driver` común falló, no se carga ni se llama a `doctor_checks()`, y `checks` es solo `{"name": "config", "ok": false, "detail": "not evaluated: driver failed"}`. Si no, se abre el plugin con el registro (`registry.open_drivers([driver], context=PluginContext(...))`, como en `_open_drivers`), y:
     1. se llama a `doctor_checks()` con `plugins.api.call_driver("doctor_checks", …, driver=<driver>)` (corte duro de 30 s de RNF-22, mismo mecanismo que los metadatos);
     2. se valida el resultado: lista de `{"name", "ok", "detail"}` con `name` único dentro del plugin, distinto de `config` y `plugin`, `ok` booleano y `detail` de una línea (sin `\n` ni `\r`); válido ⇒ se copian sin cambios;
     3. si `doctor_checks()` lanza, devuelve algo inválido o vence el corte ⇒ un chequeo `{"name": "plugin", "ok": false, "detail": "E_PLUGIN_FAILED: …"}` (al vencer: `timeout after 30 s: plugin '<driver>' did not respond`);
     4. después, `config` del plugin: el núcleo resuelve los bloques `[scope]` y la `mailbox_list` de ese driver con `accounts()` y `resolve_mailbox()` del plugin envuelto (`wrap_driver`, mismo corte duro), con el mismo formato de detalle y de errores que el `config` del backend nativo (`<clave> → <etiqueta> (<uuid>): INBOX, …` o `<clave>: <código>: <mensaje> (hint: …)`).
     - El plugin se cierra al terminar (`close`, sin enmascarar el resultado).
   - **Orden de cálculo (D-25):** la sección `plugins` se calcula antes que los chequeos del backend nativo (cada llamada al plugin tiene su propio corte de 30 s); el orden de la salida no cambia (`checks` y después `plugins`).
   - El `config` de primer nivel deja de listar los bloques de otros drivers (`… → declared for driver <x>`); si todos los bloques son de plugins, su detalle es `0 account block(s) declared for driver <nativo>` con `ok: true`.
   - Texto: después de `Checks:`, la sección `Plugins:` con el nombre de cada driver y sus filas debajo con el formato de `Checks:` (ejemplo de PRD-v2.2 sección 8); sin plugins declarados no se muestra. `Result:` cuenta todos los chequeos, también los de los plugins. Exit 0 y `ok` de primer nivel sin cambios.
   - `src/mailquery/plugins/api.py`: solo si hace falta un validador o una constante para `doctor_checks` (el PRD lo asigna a ese módulo); si `call_driver` basta, no se toca.
2. **`--failures` (RF-76):** opción `store_true` de `doctor`. Se ejecutan los mismos chequeos con las mismas dependencias y el mismo orden; solo se filtra lo que se muestra.
   - JSON: la respuesta de `doctor --json` con `checks` filtrado a los `ok: false` que se evaluaron (incluidos `not evaluated: <causa concreta>`), `not_evaluated` (justo después de `checks`) con los nombres de los que no se evaluaron porque dependían de otro que falló (D-05: `detail` exactamente `not evaluated: <chequeo> failed`), y `plugins` filtrado igual (solo los plugins con algún chequeo que falla o sin evaluar, cada uno con `driver`, sus `checks` que fallan y su `not_evaluated`). Todo bien ⇒ `checks: []`, `not_evaluated: []`, `plugins: []`.
   - Texto: título y `Generated at` como siempre; cada sección (`Checks:` y cada plugin de `Plugins:`) muestra solo sus filas que fallan y, si hay alguno sin evaluar, la línea `not evaluated: <nombres>`; una sección sin fallos no se muestra; si no falla nada, bajo `Checks:` sale `all checks passed`.
   - Sin `--failures`, `doctor` no cambia (salvo el título y la sección de plugins).
3. **Diagnóstico sin *preflight* (RF-77):**
   - Línea de `doctor` en la ayuda general (epílogo raíz): `environment and read-only preflight` → `environment and read-only diagnosis`; lo mismo en la tabla de comandos de la skill (`environment, drivers and read-only preflight`, `skills/mailquery/SKILL.md:59`) y en la línea del título que muestran los README (`README.md:275`, `README.es.md:277`).
   - Título del informe de texto: `mailquery doctor - environment and read-only diagnosis`.
   - Epílogo de `doctor`: `--failures` y el ejemplo `mailquery doctor --json --failures`.
   - Skill: se elimina "Preflight once per session"; los comandos se ejecutan directamente porque todo fallo devuelve `code` y `hint`; `mailquery doctor --json --failures` solo tras un exit 3 o 6, tras instalar o actualizar `mailquery`, un plugin o la app que lanza el harness, o cuando un resultado no cuadra; `mailquery mailboxes` solo para ver etiquetas de cuentas y carpetas al editar `config.toml` o cuando `search` devuelve 0 mensajes y el correo puede estar en otra carpeta (repetir con `--include-mailbox`); una petición típica es un `search` y como mucho un `show`; los ejemplos empiezan por `search` y presentan `doctor` y `mailboxes` como diagnóstico; tabla de comandos con `doctor` = diagnóstico.
   - README: `doctor` como verificación tras instalar o actualizar y como diagnóstico de un fallo; `--failures`; la sección de plugins; el ejemplo de uso que empieza por `mailquery doctor        # 1. preflight: …` (`README.md:178`, `README.es.md:180`) pasa a empezar por un `search`, con `doctor` como diagnóstico.
   - Instaladores: el mensaje `running 'mailquery doctor' (preflight)...` de `scripts/install.sh:300` y `scripts/install.ps1:277` pasa a `running 'mailquery doctor' (post-install check)...` (ningún test lo compara; si INS-SMOKE lo comprobara, se ajusta en `tests/test_install_scripts.py`).
   - Recetas: si alguna pide `doctor` antes de cada uso, se cambia por el diagnóstico tras un fallo.
4. **Timeout COM de `doctor` en Windows (RF-76, RF-81, D-25):** `_bind_doctor_timeout` y `_emit_doctor_report` reciben `failures` y la sección `plugins` ya calculada; tras un timeout COM, el informe (JSON y texto) aplica el mismo filtrado de `--failures`, incluye `plugins` completo y termina con exit 0, como el informe normal.
5. **Documentación de la API de plugins:** `INTERFACES.md` documenta la forma de retorno de `doctor_checks()` y los nombres reservados `config` y `plugin`, y retira "Un plugin externo no añade chequeos propios" y `declared for driver` (bloque para el orquestador).

**Fuera:** cambiar `plugin_api`, los chequeos existentes o el exit; ejecutar los chequeos de `doctor` dentro de otros comandos.

## 3. Dependencias y ACs

- **Entrada:** M12 (orden de archivos); lote I3 mergeado.
- **Salida:** M14.
- **ACs:** AC-O10 (`doctor --help`), AC-O11, AC-O12, AC-O16, AC-O17.

## 4. Archivos

| Acción | Archivo |
|---|---|
| Modifica | `src/mailquery/cli.py`; `src/mailquery/plugins/api.py` solo si hace falta (sección 2, punto 1) |
| Modifica | Goldens `tests/fixtures/expected/doctor.json`, `tests/fixtures/expected/outlook/doctor.json` (`plugins: []`) |
| Crea | `tests/test_doctor.py` |
| Modifica (título, `declared for driver`, forma de `doctor --json`, skill) | `tests/test_cli.py`, `tests/test_integration.py`, `tests/test_outlook.py` (también UT-DR-10 junto a OL-04 y el barrido de OL-30), `tests/test_plugins.py`, `tests/test_multidriver.py` (solo los que fallen) |
| Modifica (barrido de solo lectura) | `tests/test_readonly.py` (TC-03.01) |
| Modifica | `scripts/install.sh`, `scripts/install.ps1` (mensaje del paso de `doctor`); `tests/test_install_scripts.py` solo si alguna aserción lo compara |
| Modifica si hace falta | `tests/fakes/plugin.py` (`doctor_checks` configurable: lista válida, inválida, excepción, bloqueo) |
| Modifica | `README.md`, `README.es.md`, `skills/mailquery/SKILL.md`, `docs/recipes/*` (si piden *preflight*) |
| Bloques para el orquestador | `docs/TEST-CATALOG.md` (secciones 2, 3, 7, 8), `docs/INTERFACES.md` (`cli.py`, API de plugins, sección 4 `doctor`) |

## 5. Refactorizaciones previas

Ninguna (se descartó extraer `doctor` a un módulo propio: sección 5 del plan maestro).

## 6. Fases

| Fase | Tareas | Estado |
|---|---|---|
| F1 — Plugins | Sección `plugins` (JSON y texto), `config` de primer nivel, orden de cálculo (D-25); UT-DR-05–UT-DR-08 | 🟢 |
| F2 — `--failures` | Filtrado JSON y texto; UT-DR-01–UT-DR-03, UT-DR-09 | 🟢 |
| F3 — Diagnóstico | Título, ayuda general, epílogo, instaladores; UT-DR-04; timeout COM (sección 2, punto 4); UT-DR-10 | 🟢 |
| F4 — Goldens y tests existentes | `plugins: []`, título, `declared for driver` | 🟢 |
| F5 — Documentación | Sección 2, puntos 3 y 5; DOC-12 | 🟢 |
| F6 — Cierre | Suite completa, evidencia cruda, bloques | 🟢 |

## 7. Tests

Archivo `tests/test_doctor.py`, prefijo nuevo **UT-DR** ("`doctor`: fallos y plugins").

**UT-DR-01 — `--failures` con todo correcto**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `doctor --json --failures` → `{"ok": true, "command": "doctor", "generated_at": …, "checks": [], "not_evaluated": [], "plugins": [], "warnings": []}`, en ese orden de claves; exit 0. |

**UT-DR-02 — `--failures` con un chequeo que falla**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Apple Mail con `store` fallido (mock de TCC): `checks` solo con los que fallan (con su `detail`) y `not_evaluated` con `envelope_index`, `schema`, `readonly_strategy` y, con bloques declarados, `config` (los que dependían, según UT-CLI-10.01), en el orden habitual. |
| .02 | N | Outlook cerrado (doble): `checks` con `outlook` y `not_evaluated` con los que dependían (ejemplo de PRD-v2.2 sección 8). |
| .03 | B | Un chequeo con `not evaluated: <causa concreta>` que no es `<chequeo> failed` se lista en `checks`, no en `not_evaluated` (D-05). |
| .04 | P | Exit 0 y `ok: true` en todos los casos. |

**UT-DR-03 — `--failures` en texto**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Todo bien → título, `Generated at`, `Checks:` y `all checks passed`. |
| .02 | N | Con fallos → una fila por chequeo que falla y la línea `not evaluated: <nombres>`; secciones sin fallos ocultas. |

**UT-DR-04 — `doctor` sin `--failures`**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | JSON igual que antes salvo `plugins` (vacío sin plugins); texto igual salvo el título `mailquery doctor - environment and read-only diagnosis` y sin sección `Plugins:` cuando no hay plugins. |

**UT-DR-05 — Sección de plugins**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Plugin falso declarado con `doctor_checks()` válido: `plugins` con su `driver`, sus chequeos sin cambios y después `config` con la resolución de sus bloques. |
| .02 | N | Un bloque del plugin que no resuelve → `config` del plugin `ok: false` con `<clave>: <código>: <mensaje> (hint: …)`. |
| .03 | P | `checks[]` de primer nivel igual que sin el plugin salvo el detalle de `driver` y que `config` ya no lista sus bloques; con solo bloques de plugins, `config` de primer nivel `0 account block(s) declared for driver <nativo>` y `ok: true`. |
| .04 | P | Varios plugins en el orden de su primer bloque. |
| .05 | B | `close()` del plugin lanza una excepción: el resultado del plugin y el resto del informe no cambian; exit 0. |

**UT-DR-06 — Plugin que no pasa `driver`**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Plugin declarado no instalado o incompatible: sus `checks` son solo `config` con `not evaluated: driver failed` y `doctor_checks()` no se llama. |
| .02 | N | El chequeo `driver` pasa pero `registry.open_drivers` falla al abrir el plugin: chequeo `plugin` `ok: false` con `E_PLUGIN_FAILED: …` y `config` del plugin; el resto del informe igual; exit 0. |

**UT-DR-07 — `doctor_checks()` inválido o colgado**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Lanza una excepción → chequeo `plugin` `ok: false` con `E_PLUGIN_FAILED: …`, seguido de `config`. |
| .02 | N | Devuelve algo que no es lista; un elemento que no es un dict; un elemento sin la forma; `ok` que no es booleano; `detail` que no es texto; un `name` repetido; un `name` `config` o `plugin`; un `detail` con `\n` o solo con `\r` → ídem. |
| .03 | N | No responde (plazo inyectado con `mock.patch("mailquery.plugins.api.METADATA_TIMEOUT_SECONDS", 0.05)`) → `plugin` `ok: false` con `timeout after 30 s: plugin '<driver>' did not respond`; el resto de `doctor` se muestra igual. |
| .04 | N | `accounts()` o `resolve_mailbox()` del plugin lanzan una excepción o no responden (mismo plazo inyectado) → `config` del plugin `ok: false` con el formato de error de RF-81; exit 0 y el resto del informe intacto. |

**UT-DR-08 — Texto y `Result:`**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | El texto muestra `Plugins:`, el driver y sus filas con el formato de `Checks:` (ejemplo de PRD-v2.2 sección 8). |
| .02 | P | `Result:` cuenta los chequeos de primer nivel y los de los plugins; exit 0. |

**UT-DR-09 — `--failures` con plugins**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Solo salen los plugins con algún chequeo que falla o sin evaluar, con sus `checks` que fallan y su `not_evaluated`. |
| .02 | P | Si solo falla un plugin (pasa el chequeo `driver` común y falla en su `doctor_checks()` o en su `config`): el texto muestra solo `Plugins:` (sin `Checks:`) y el JSON da `checks: []`, `not_evaluated: []` y el plugin. |
| .03 | P | Si no falla nada: `plugins: []` y en texto `all checks passed`. |

**UT-DR-10 — Timeout COM con `--failures`** · `tests/test_outlook.py` (junto a OL-04, con su helper de `doctor` colgado)

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | N | Doble de Outlook colgado en el chequeo `outlook` y un plugin falso declarado: `doctor --json --failures` da exit 0, `checks` con `outlook` (timeout), `not_evaluated` con sus dependientes y `plugins` presente y filtrado; el texto con `--failures` muestra lo mismo. |
| .02 | P | Mismo cuelgue sin `--failures`: el JSON incluye `plugins` completo después de `checks`. |

**DOC-12 — Diagnóstico sin *preflight*** (nuevo) · `tests/test_doctor.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `doctor --help` describe `--failures`; la ayuda general muestra `environment and read-only diagnosis`. |
| .02 | N | La skill, los README y la ayuda general no contienen "Preflight once per session", `# 1. preflight` ni `read-only preflight`, ni piden `doctor`/`mailboxes` antes de cada uso. |
| .03 | P | La skill indica `mailquery doctor --json --failures` en los casos de RF-77, `mailboxes` solo para editar la configuración o tras un `search` sin resultados, y su primer ejemplo es un `search`. |
| .04 | P | Los dos README describen `doctor` como verificación tras instalar o actualizar y como diagnóstico de un fallo, con `--failures` y la sección de plugins. |

**Goldens (TC-01, TC-02):** `doctor.json` y `outlook/doctor.json` añaden `"plugins": []` tras `checks`.

Comandos:

```bash
python -B -m unittest discover -s tests -t . -k test_ut_dr_
python -B -m unittest discover -s tests -t . -k test_doc_12_
python -B -m unittest discover -s tests -t . -k test_tc_01_
python -B -m unittest discover -s tests -t . -k test_tc_02_
python -B -m unittest discover -s tests -t . -k test_tc_03_
python -B -m unittest discover -s tests -t . -k test_ol_04_
python -B -m unittest discover -s tests -t . -k test_ol_30_
python -B -m coverage erase
python -B -m coverage run -m unittest discover -s tests -t .
python -B -m coverage report
python -B -m coverage report --include="src/mailquery/cli.py,src/mailquery/plugins/api.py" --fail-under=85
```

`-k test_ut_dr_` no selecciona los `test_ut_drv_*` existentes.

## 8. Tests existentes afectados (previsibles)

- Goldens de `doctor` (TC-01.01, TC-02.07).
- Tests que comprueban el título `… preflight` del informe de texto o la línea de la ayuda general (`tests/test_cli.py`, `tests/test_integration.py` DOC-05).
- UT-DRV-05 y casos de `config` con bloques de plugins que esperan `declared for driver` (`tests/test_cli.py`, `tests/test_plugins.py`, `tests/test_multidriver.py`).
- OL-26 (`doctor` en Windows) si compara el texto o la forma completa.
- DOC-04 si verifica frases de *preflight* de la skill.
- OL-04.03/.04 (`doctor` colgado en Windows): la salida añade `plugins`.
- Los dos tests sin ID que comprueban el título `mailquery doctor - environment and read-only preflight` (`tests/test_cli.py:1088`, `tests/test_integration.py:426`).
- Barrido de solo lectura: TC-03.01 (`tests/test_readonly.py`) y OL-30 (`tests/test_outlook.py`) añaden `doctor --failures` y `doctor --json --failures`, sin tocar las aserciones de solo lectura.
- Si un caso nuevo de UT-DR verificaría exactamente lo mismo que un caso heredado (UT-CLI-10, UT-DRV-05), se actualiza el heredado en lugar de crear el nuevo.

## 9. Documentación

- Sección 2, puntos 3 y 5.
- Bloques para `TEST-CATALOG.md`: sección 2, prefijo `UT-DR` → `tests/test_doctor.py` y `tests/test_outlook.py` (UT-DR-10); sección 3, goldens de `doctor`; sección 8, UT-DR-01–10, DOC-12 y casos existentes modificados (incluidos OL-04.03/.04, TC-03.01 y OL-30); sección 7, filas de AC-O10–AC-O12, AC-O16, AC-O17.

## 10. Actualizaciones de `PRD-v2.2.md` (las escribe el orquestador)

- Registro de conciliación: "`doctor`" (F3) → `Implementado y documentado`, con la nota de D-05 (qué chequeos van a `not_evaluated`), redactada sin citar el plan; "Recetas, skill y README" (F3) → completo.
- Checklist: CL-05 avanza (retirados `doctor` como *preflight* en skill, ayuda y README, "Un plugin externo no añade chequeos propios" y `declared for driver` en `INTERFACES.md`, "Diagnóstico antes de usar la herramienta").
- Tabla de supersesión: sin cambios.

## 11. Datos crudos de evidencia a entregar

(a) suite completa con commit y conteo; (b) grupos `test_ut_dr_`, `test_doc_12_`, `test_tc_01_`, `test_tc_02_`, `test_tc_03_`, `test_ol_04_` y `test_ol_30_` solos; (c) goldens de `doctor` con su diff y justificación; (d) tests nuevos y existentes ajustados con IDs, AC y motivo; (e) `git diff --check` y `git diff --stat integration/i4-mailboxes-doctor-close...HEAD`; (f) riesgos (plugins colgados alargan `doctor`), decisiones y pendientes; (g) cobertura: `coverage report` completo y de los módulos tocados, con la línea base del lote de esos módulos, las líneas sin cubrir y la justificación de cada pragma nuevo. Más los bloques de la sección 9.

## 12. Definition of Done

- [ ] Sección `plugins` en JSON y texto, con validación de `doctor_checks()`, corte duro y `config` por plugin; `config` de primer nivel sin bloques de plugins.
- [ ] `--failures` filtra JSON y texto según RF-76, también tras un timeout COM, con `plugins` presente (D-25); exit 0.
- [ ] Título y ayuda general dicen `diagnosis`; skill, README e instaladores sin *preflight*; recetas actualizadas.
- [ ] UT-DR-01–10, DOC-12 y goldens verdes solos; TC-03.01 y OL-30 recorren `doctor --failures`.
- [ ] Suite completa sin fallos nuevos frente a la línea base del lote.
- [ ] Cobertura (D-21): total ≥ 85 %; `python -B -m coverage report --include=<archivos de src/ de la sección 4> --fail-under=85` verde o, para un módulo por debajo del 85 % en la línea base del lote, sin bajar de ese valor y con las líneas nuevas cubiertas; salida en la evidencia (g).
- [ ] Informe final con los datos de la sección 11 y los bloques.

## 13. Registro de progreso

| Fecha | Fase | Nota |
|---|---|---|
| 2026-11-14 | F1 — Plugins | Sección `plugins` en JSON y texto, validación de `doctor_checks()`, corte duro con `call_driver`, `config` por plugin y `config` de primer nivel sin bloques de plugins; UT-DR-05–UT-DR-08 verdes. |
| 2026-11-14 | F2 — `--failures` | Filtrado de `checks`/`not_evaluated` y de cada sección `Plugins:` en JSON y texto; UT-DR-01–UT-DR-03 y UT-DR-09 verdes. |
| 2026-11-14 | F3 — Diagnóstico | Título y ayuda general con `diagnosis`, epílogo con `--failures`, instaladores, skill y README; timeout COM completa el informe y aplica `--failures`; UT-DR-04 y UT-DR-10 verdes. |
| 2026-11-14 | F4 — Goldens y tests existentes | `doctor.json` y `outlook/doctor.json` con `plugins: []`; título, barridos TC-03.01 y OL-30 con `--failures`; módulos de test existentes verdes. |
| 2026-11-14 | F5 — Documentación | Skill y ambos README sin *preflight*, con `--failures` y la sección de plugins; DOC-12 verde; `INTERFACES.md` y `TEST-CATALOG.md` quedan como bloques para el orquestador. |
| 2026-11-14 | F6 — Cierre | Suite completa `Ran 1425`, `OK (skipped=7)`; cobertura total 91,3 % y `cli.py` 93,2 %; informe de evidencia con los datos crudos y los bloques para el orquestador. |

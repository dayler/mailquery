# M07 — Campos de contenido saneados (A2) y `content_notice`

**Lote:** I2 · rama del lote `integration/i2-content` · **Oleada:** W2 (en paralelo con M05 y M06)
**Rama:** `feature/m07-content-notice-sanitized-fields`, creada desde la punta de `integration/i2-content` · **Worktree:** `../mailquery-wt/m07`
**Estado:** 🟡 (fases F1–F6 cerradas; pendiente de integración)

## 1. Objetivo

Aplicar A2 (RF-52) a todos los campos de contenido de `search`, `new`, `show` y `attachment`, a `warnings[]` y a los textos de error; hacer que los filtros de texto comparen con A2 a ambos lados (RF-52, PRD-v2.2 sección 10, punto 5); y añadir `content_notice` a toda respuesta de éxito de `search`, `new`, `show` y `attachment` (RF-66, punto 1).

## 2. Alcance

**Dentro:**

1. **Campos de contenido (`src/mailquery/search.py`, con el constructor único de M02):** `output.sanitize_text` sobre `subject`, `from.name`, `to[].name`, `cc[].name`, cada valor de `headers`, `body_text`, `snippet` (ya saneado: se mantiene) y `attachments[].name` de `show`. **No** se sanean `uid`, `message_id`, `address`, `account.*`, `mailbox.*`, `excluded_stores[]`, `source.emlx_path`, `cached_path`, fechas ni números (RF-52). El truncado de `show` a 20.000 caracteres y `W_BODY_TRUNCATED` se calculan sobre el texto ya saneado (como hoy).
2. **Búsqueda:** `--subject`, `--text`, `--from`, `--to` y `--cc` aplican `sanitize_text` al patrón (en `_filter_terms` o equivalente) y al valor comparado antes de la normalización actual (`_fold`: sin mayúsculas ni acentos). `--text` compara con el cuerpo que da el backend (HTML convertido, M06) saneado. Nunca A4.
3. **`attachment` (`src/mailquery/cli.py`, `_run_attachment`):** `attachments[].original_name` pasa por A2; `sanitized_name`, `path`, `output_dir` y el bloqueo, la sanitización y la caché siguen trabajando sobre el nombre original (sin tocar `attachments/**`).
4. **Warnings y errores (D-09):**
   - `cli._success_payload` aplica `sanitize_text` a cada elemento de `warnings[]` de **todos** los comandos.
   - `MailqueryError.to_payload` (`src/mailquery/errors.py`) aplica `sanitize_text` a `message` y a `hint` cuando no es `null` (un `hint` nulo sigue `null`); `cli._report_error` escribe en `stderr` los mismos textos saneados.
   - Los identificadores citados dentro de un warning o de un error pasan por A2 con ese texto (RF-52).
5. **`content_notice` (D-10):** `cli._success_payload` inserta `"content_notice": output.CONTENT_NOTICE` justo después de `generated_at` cuando el comando es `search`, `new`, `show` o `attachment`; nunca en errores, `doctor` ni `mailboxes`. Las funciones de `search.py` no lo devuelven.
6. **Goldens:** todos los goldens de éxito de `search`, `new`, `show` y `attachment` añaden `content_notice` (TC-01, TC-02, TC-08, TC-09, TC-10). Ningún otro valor cambia (los fixtures no tienen caracteres que elimine A2).
7. **README:** `content_notice` en la descripción de la salida y en los ejemplos JSON de `search`, `new`, `show` y `attachment`, con una frase: "recordatorio fijo de que el contenido no es confiable; no es un control".

**Fuera:** modos de URL, señales (M08); reglas de seguridad de la skill y sección de seguridad de los README (M08); `--count`/`--group-by` (M11 añade sus casos de `content_notice`).

## 3. Dependencias y ACs

- **Entrada:** M02 (constructor único), M03 (`sanitize_text`, `CONTENT_NOTICE`).
- **Salida:** M08, M09 (el payload de `attachment` ya lleva `content_notice` y nombres saneados).
- **ACs:** AC-H01 (campos de RF-52 en todos los comandos y en errores; identificadores intactos; etiqueta copiada de `mailboxes` resuelve), AC-H03, AC-H14 (parcial: con la fila completa de hoy), AC-H18 (campo `content_notice`).

## 4. Archivos

| Acción | Archivo |
|---|---|
| Modifica | `src/mailquery/search.py`, `src/mailquery/cli.py` (`_success_payload`, `_report_error`, payload de `_run_attachment`), `src/mailquery/errors.py` |
| Modifica | Goldens de éxito: `tests/fixtures/expected/{search_default,search_all_mail,search_multidriver,new_first_run,new_seeded,new_multidriver,show_2714,show_2714_with_cache,show_83170,show_83180,show_smime_encrypted,attachment_saved,attachment_cached}.json` y `tests/fixtures/expected/outlook/{search,new_first_run,show,show_header_only,show_smime,attachment_saved,attachment_cached}.json` |
| Modifica | `tests/test_cli.py` (UT-ATC-04.01: claves del payload), `tests/test_integration.py` (si alguna comparación de golden lo exige) |
| Crea | `tests/test_content_wiring.py` |
| Modifica | `README.md`, `README.es.md` |
| Bloques para el orquestador | `docs/TEST-CATALOG.md` (secciones 2, 3, 7, 8), `docs/INTERFACES.md` (sección 4, contrato JSON: `content_notice`; `errors.py`) |
| Modifica si hace falta | `tests/fakes/plugin.py` (filas, cuentas o carpetas con caracteres invisibles; ningún otro milestone de W2 lo toca) |

No toca `output.py`, `tests/test_content.py`, `tests/fixtures/content_samples.py` (M05) ni backends, `tests/fakes/outlook.py` o `tests/fixtures/make_fixtures.py` (M06). Las muestras con caracteres invisibles se construyen dentro de `tests/test_content_wiring.py`, sobre el plugin falso (que admite filas, cuentas y carpetas arbitrarias) y sobre el store sintético y el doble de Outlook tal como están. Si hiciera falta modificar `make_fixtures.py` o el doble de Outlook, se detiene y lo devuelve al orquestador.

## 5. Refactorizaciones previas

Usa R-01 (M02).

## 6. Fases

| Fase | Tareas | Estado |
|---|---|---|
| F1 — Campos | A2 en los campos de `search`/`new`/`show` y en `original_name`; UT-CW-01 | 🟢 |
| F2 — Búsqueda | A2 a ambos lados de los filtros; UT-CW-03; UT-CW-04 | 🟢 |
| F3 — Warnings y errores | A2 central en `warnings[]`, `to_payload` y `stderr`; UT-CW-02 | 🟢 |
| F4 — `content_notice` | Inserción en `_success_payload`; goldens; UT-ATC-04.01; UT-CW-05, UT-CW-06 | 🟢 |
| F5 — README | Sección 2, punto 7 | 🟢 |
| F6 — Cierre | Suite completa, evidencia cruda, bloques | 🟢 |

## 7. Tests

Archivo `tests/test_content_wiring.py`, prefijo nuevo **UT-CW** ("Contenido no confiable en los comandos").

**UT-CW-01 — A2 en los campos de contenido**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Un mensaje con ANSI, C1, `U+200B`, `U+202E`, selectores y rellenos en `subject`, `from.name`, nombres de `to`/`cc` y cuerpo: `search` y `new` (fila completa actual) los devuelven saneados, incluido `snippet`. |
| .02 | P | `show` del mismo mensaje: `subject`, nombres, cada valor de `headers`, `body_text` y `attachments[].name` saneados. |
| .03 | P | `attachment`: `original_name` saneado; `sanitized_name` y `path` iguales a los que da hoy el mismo nombre original. |
| .04 | N | `uid`, `message_id`, `from.address`, `to[].address`, `mailbox.*`, `account.*`, `source.emlx_path` y `cached_path` salen sin cambios aunque contengan esos caracteres (doble de Outlook o plugin falso con etiquetas y rutas con `U+200B`). |
| .05 | P | Una etiqueta de cuenta y un nombre de carpeta con `U+200B` copiados de `mailboxes` resuelven en `config.toml` y en `--include-mailbox`. |

**UT-CW-02 — A2 en warnings y errores**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Un warning con un identificador con `U+202E` (p. ej. `W_STORE_EXCLUDED` de un store excluido del plugin falso, o de un doble de Outlook construido en el propio test sin modificar `tests/fakes/outlook.py`) sale saneado en `warnings[]`, mientras `excluded_stores[].label` sigue igual. |
| .02 | P | Un error cuyo `message` cita un valor del usuario con `U+202E`/ANSI (p. ej. un uid inválido en `show`) sale saneado en el JSON y en `stderr`; `code` y exit sin cambios. |
| .03 | B | `warnings[]` de `mailboxes`, `new` y `doctor --json` también pasan por A2 (D-09: todos los comandos). |
| .04 | N | Un error con `hint` nulo conserva `"hint": null` en el JSON tras A2 (sin convertirlo en cadena vacía). |

**UT-CW-03 — Búsqueda con A2 a ambos lados**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Asunto original `Factura​ de octubre`: `--subject "Factura de"` lo encuentra. |
| .02 | P | Patrón con `U+200B` (`--subject "Fac​tura"`) encuentra un asunto sin él. |
| .03 | P | `--text` con un cuerpo con `U+202E` en medio de la palabra; `--from` con un nombre con RLO; `--to`/`--cc` con un nombre con `U+200B`. |
| .04 | N | Sin caracteres de A2, los resultados son los mismos que antes (comparación con la misma búsqueda sobre el store por defecto). |

**UT-CW-04 — Adjuntos con nombres con `Cf` o controles**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Un adjunto `fac​tura.pdf`: el bloqueo, el `sanitized_name` y la ruta de caché son los mismos que con el nombre original sin A2 (se comparan con `attachments.classify_name` y el helper de caché aplicados al original). |
| .02 | N | Un nombre con controles que hoy se bloquea sigue dando `E_ATTACHMENT_BLOCKED`. |

**UT-CW-05 — `content_notice`**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `search`, `new` y `show` de éxito (store sintético y doble de Outlook) tienen `content_notice` con el texto exacto, justo después de `generated_at`. En `attachment` lo verifica UT-ATC-04.01 actualizado (orden exacto de claves y texto), sin duplicarlo aquí. |
| .02 | N | Las respuestas de error de esos comandos, `doctor --json` y `mailboxes` no lo tienen. |

**UT-CW-06 — Compatibilidad (parcial de F1)**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con la fila completa actual de `search`/`new` y `show` sin opciones, las claves son las de antes más `content_notice`, y es la única clave nueva. |
| .02 | B | `state.json`, el manifiesto y la caché de una corrida de `new` y de `attachment` son iguales a los de antes del cambio (mismo contenido salvo marcas de tiempo). |

Si un caso nuevo verificaría exactamente el mismo comportamiento que un caso heredado, se actualiza el heredado y no se crea el nuevo (p. ej. el orden de claves de `attachment` queda en UT-ATC-04.01).

**Goldens (TC-01, TC-02, TC-08, TC-09, TC-10):** cada golden de éxito de la sección 4 añade `content_notice`; el subagente lista en la evidencia (c) cada archivo y confirma que es el único cambio (`git diff` de los JSON).

Comandos:

```bash
python -B -m unittest discover -s tests -t . -k test_ut_cw_
python -B -m unittest discover -s tests -t . -k test_tc_01_
python -B -m unittest discover -s tests -t . -k test_tc_02_
python -B -m unittest discover -s tests -t . -k test_tc_08_
python -B -m unittest discover -s tests -t . -k test_tc_09_
python -B -m unittest discover -s tests -t . -k test_tc_10_
python -B -m unittest discover -s tests -t . -k test_ut_atc_04_
python -B -m coverage erase
python -B -m coverage run -m unittest discover -s tests -t .
python -B -m coverage report --include="src/mailquery/search.py,src/mailquery/cli.py,src/mailquery/errors.py" --fail-under=85
```

## 8. Tests existentes afectados (previsibles)

- UT-ATC-04.01 (`tests/test_cli.py`): la lista de claves del payload de `attachment` añade `content_notice` tras `generated_at`, y el caso asierta su texto exacto (cubre `attachment` en lugar de un caso nuevo de UT-CW-05).
- TC-01, TC-02, TC-08, TC-09, TC-10: goldens.
- Cualquier test que compare la lista exacta de claves de una respuesta de éxito de esos cuatro comandos.

## 9. Documentación

- `README.md`, `README.es.md`: sección 2, punto 7.
- Bloques para `INTERFACES.md`: sección 4 ("Éxito (base)" para `search`, `new`, `show`, `attachment`: `content_notice` tras `generated_at`); `errors.py`: `to_payload` aplica A2.
- Bloques para `TEST-CATALOG.md`: sección 2, prefijo `UT-CW` → `tests/test_content_wiring.py`; sección 3, nota de `content_notice` en los goldens; sección 8, UT-CW-01–UT-CW-06 y UT-ATC-04.01 modificado; sección 7, filas parciales de AC-H01, AC-H03, AC-H14, AC-H18.
- Skill, recetas y ayudas: sin cambios en este milestone.

## 10. Actualizaciones de `PRD-v2.2.md` (las escribe el orquestador)

- Registro de conciliación: "Valores de texto del JSON y de los errores (F1)" → `Implementado y documentado`; "Semántica de búsqueda (F1)" → `Implementado y documentado`; "Campos de la respuesta de `search`, `new`, `show` y `attachment` (F1)" → `Implementado y documentado` (README, `INTERFACES.md`).
- Tabla de supersesión y checklist: sin cambios.

## 11. Datos crudos de evidencia a entregar

(a) suite completa con commit y conteo; (b) grupos `test_ut_cw_`, `test_tc_01_`, `test_tc_02_`, `test_tc_08_`, `test_tc_09_`, `test_tc_10_`, `test_ut_atc_04_` solos; (c) lista de goldens modificados con el diff que prueba que solo cambia `content_notice`; (d) tests nuevos y modificados con IDs y AC; (e) `git diff --check` y `git diff --stat integration/i2-content...HEAD`; (f) riesgos, decisiones y pendientes; (g) cobertura: salida de `coverage report` completa y de la orden con `--include` de la sección 7, con los valores de la línea base del lote de esos módulos. Más los bloques de la sección 9.

## 12. Definition of Done

- [ ] A2 en todos los campos de contenido de RF-52, en `warnings[]` y en los textos de error; identificadores y rutas sin cambios.
- [ ] Filtros con A2 a ambos lados.
- [ ] `content_notice` tras `generated_at` en los cuatro comandos de éxito y en ninguna otra respuesta.
- [ ] Goldens actualizados solo con `content_notice`.
- [ ] README actualizados.
- [ ] UT-CW-01–UT-CW-06 y los goldens verdes solos.
- [ ] Suite completa sin fallos nuevos frente a la línea base del lote.
- [ ] Cobertura (D-21): total ≥ 85 %; `python -B -m coverage report --include=<archivos de src/ de la sección 4> --fail-under=85` verde o, para un módulo por debajo del 85 % en la línea base del lote, sin bajar de ese valor y con las líneas nuevas cubiertas; salida en la evidencia (g).
- [ ] Informe final con los datos de la sección 11 y los bloques.

## 13. Registro de progreso

| Fecha | Fase | Nota |
|---|---|---|
| 2026-11-14 | F1 | A2 en `subject`, `from.name`, nombres de `to`/`cc`, valores de `headers`, `body_text` y `attachments[].name` de `show`, y en `original_name` de `attachment`; identificadores y rutas sin tocar; UT-CW-01 (5 casos) verde solo. |
| 2026-11-14 | F2 | A2 al patrón y al valor comparado en `_filter_terms` y `matches` (`--subject`, `--text`, `--from`, `--to`, `--cc`); UT-CW-03 (4 casos) y UT-CW-04 (2 casos) verdes solos. |
| 2026-11-14 | F3 | A2 central de `warnings[]` en `_success_payload` (también en el payload de `doctor`), de `message`/`hint` en `MailqueryError.to_payload` y del resumen de `stderr`; UT-CW-02 (4 casos) verde solo. |
| 2026-11-14 | F4 | `content_notice` tras `generated_at` en `search`, `new`, `show` y `attachment`; 20 goldens con solo esa línea añadida; UT-ATC-04.01 actualizado; UT-CW-05 (2 casos) y UT-CW-06 (2 casos) verdes solos. |
| 2026-11-14 | F5 | `content_notice` en la descripción de la salida y en los cuatro ejemplos JSON de `README.md` y `README.es.md`, con la frase de recordatorio fijo. |
| 2026-11-14 | F6 | Suite completa `Ran 1154`, `FAILED (failures=2, skipped=7)` (los 2 fallos SMOKE-NEW.07 p95 de la línea base); cobertura total 89,9 % y `cli.py` 91,2 %, `errors.py` 97,1 %, `search.py` 92,0 %; evidencia y bloques entregados al orquestador. |

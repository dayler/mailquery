# M02 — Refactor: armado único de mensajes en `search.py`

**Lote:** I1 · rama del lote `integration/i1-prep` · **Oleada:** W1 (en paralelo con M01, M03 y M04)
**Rama:** `feature/m02-message-assembly-refactor`, creada desde la punta de `integration/i1-prep` · **Worktree:** `../mailquery-wt/m02`
**Estado:** ⚪ (leyenda y protocolo en [`00-master-plan.md`](00-master-plan.md))

## 1. Objetivo

Refactorización R-01 del plan maestro: que `search`, `new` y `show` construyan sus mensajes con las mismas funciones, con los warnings agrupados por mensaje y con el orden de campos fijado en constantes, **sin cambiar ninguna salida**.

**Justificación.** Hoy la fila de `search`/`new` se arma en `_message_payload` y la de `show` en un dict en línea dentro de `run_show` (`src/mailquery/search.py`, funciones `run_show`, `_build_messages`, `_message_payload`, `_body_fields`, `_body_from_cached`). F1 tiene que sanear (A2), aplicar modos de URL (A4) y contar señales (A5) en los mismos campos de los tres comandos, y F3 tiene que elegir campos en los tres (`--fields`). Con dos construcciones, cada regla se escribiría dos veces y `show` podría quedar sin una de ellas. Además, el orden de warnings de F1 es por mensaje (PRD-v2.2 sección 10, punto 8), y hoy los warnings del cuerpo se vuelcan en una lista plana.

## 2. Alcance

**Dentro (solo `src/mailquery/search.py`):**

1. Constantes públicas del módulo con el orden canónico de campos:
   - `SEARCH_ROW_FIELDS = ("uid", "message_id", "duplicate_count", "subject", "from", "to", "cc", "date_sent", "date_received", "mailbox", "is_read", "is_flagged", "has_attachments", "size_bytes", "snippet", "body")` (orden de `PRD.md` sección 12.5).
   - `SHOW_FIELDS = ("uid", "message_id", "subject", "from", "to", "cc", "date_sent", "date_received", "mailbox", "is_read", "is_flagged", "has_attachments", "size_bytes", "headers", "body_text", "body_truncated", "attachments", "partial", "readable", "source")` (orden de `PRD.md` sección 12.4).
2. Una función que arma los campos comunes de metadatos de un mensaje (`uid`, `message_id`, `subject`, `from`, `to`, `cc`, `date_sent`, `date_received`, `mailbox`, `is_read`, `is_flagged`, `has_attachments`, `size_bytes`) a partir de la fila del backend, el mapa de cuentas, la carpeta mostrada, los destinatarios y el driver. `_message_payload` y `run_show` la usan; cada comando añade solo sus campos propios (`duplicate_count`, `snippet`, `body` en `search`/`new`; `headers`, `body_text`, `body_truncated`, `attachments`, `partial`, `readable`, `source` en `show`). El dict final se ordena con la constante del comando.
3. Un cargador de cuerpo por mensaje que devuelve, en una estructura interna (p. ej. un `dataclass` privado), el texto del cuerpo, las banderas `available`/`readable`/`partial`, las cabeceras crudas, los adjuntos del cuerpo y **la lista de warnings de ese mensaje**; lo usan `_build_messages` (con el atajo actual de cuerpos ya leídos por `--text`) y `run_show`.
4. `_build_messages` acumula los warnings por mensaje (lista de listas) y los aplana en el mismo orden que hoy; `run_show` igual con su único mensaje.

**Fuera:** cualquier cambio de comportamiento, de texto, de orden de warnings o de lecturas al backend; `run_mailboxes`; `cli.py`; las firmas públicas `run_search`, `run_new`, `run_show`, `run_mailboxes`, `Filters`, `parse_relative_time`, `wildcard_to_regex`, `matches`.

## 3. Dependencias y ACs

- **Entrada:** ninguna.
- **Salida:** M07, M08, M10 y M11 se apoyan en las funciones y constantes de este milestone.
- **ACs:** ninguno (refactor que preserva comportamiento). Verificación: suite y goldens idénticos.

## 4. Archivos

| Acción | Archivo |
|---|---|
| Modifica | `src/mailquery/search.py` |
| Modifica | `tests/test_search.py` (solo el grupo nuevo de la sección 8) |
| Bloques para el orquestador | `docs/TEST-CATALOG.md` (sección 8), `docs/INTERFACES.md` (contrato de `search.py`: las dos constantes) |

## 5. Refactorizaciones previas

Este milestone es la refactorización R-01.

## 6. Reglas de la refactorización

- Mismas llamadas al backend, en el mismo orden y número (el doble de Outlook registra cada acceso en su `CallLog`: los tests OL que comparan llamadas deben pasar sin cambios).
- Mismos valores, mismo orden de claves y mismos warnings en el mismo orden en `search`, `new` y `show`; los goldens de `tests/fixtures/expected/` no se tocan.
- `scan.messages_read` igual (se sigue sumando por driver como hoy).
- Los tests que parchean `search._body_fields` (`tests/test_search.py`, un uso) siguen funcionando: si la función cambia de nombre o de firma, el test se adapta en este milestone sin cambiar lo que verifica, y se anota en la evidencia.

## 7. Fases

| Fase | Tareas | Estado |
|---|---|---|
| F1 — Constantes | `SEARCH_ROW_FIELDS`, `SHOW_FIELDS`; tests UT-SR-17 | 🟢 |
| F2 — Campos comunes | Función de metadatos usada por `_message_payload` y `run_show` | 🟢 |
| F3 — Cuerpo y warnings por mensaje | Cargador único; warnings por mensaje aplanados en el mismo orden | 🟢 |
| F4 — Cierre | Suite completa idéntica a la línea base, evidencia cruda, bloques | 🟢 |

## 8. Tests

**UT-SR-17 — Orden canónico de campos** (nuevo) · `tests/test_search.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Las claves de cada fila de `search` sobre el store sintético son exactamente `SEARCH_ROW_FIELDS`, en ese orden. |
| .02 | P | Las claves de `message` de `show` son exactamente `SHOW_FIELDS`, en ese orden (macOS sobre el store sintético y Windows sobre el doble de Outlook). |

Métodos: `test_ut_sr_17_01_search_row_keys_follow_the_canonical_order`, `test_ut_sr_17_02_show_keys_follow_the_canonical_order`.

Comandos:

```bash
python -B -m unittest discover -s tests -t . -k test_ut_sr_17_
python -B -m unittest discover -s tests -t . -v
python -B -m coverage erase
python -B -m coverage run -m unittest discover -s tests -t .
python -B -m coverage report
python -B -m coverage report --include=src/mailquery/search.py --fail-under=85
```

La prueba principal de este milestone es la suite completa: mismo número de tests (más los dos nuevos), los mismos fallos y saltos que la línea base del lote y ningún golden modificado. La cobertura es la segunda red del refactor: la de `search.py` no baja de la de la línea base del lote (91,7 % en `cf164ff`, medida en Windows durante la planificación); una rama que quede sin recorrer tras el refactor se elimina si es código muerto o se cubre con un test.

## 9. Tests existentes afectados

Ninguno debería cambiar. Si un test cambia, el cambio es solo de seam (nombre de la función parcheada) y se justifica en la evidencia.

## 10. Documentación

- Bloque para `INTERFACES.md`, contrato de `search.py`: `SEARCH_ROW_FIELDS` y `SHOW_FIELDS` como orden canónico de la fila y de `show`.
- Bloque para `TEST-CATALOG.md` sección 8: UT-SR-17.
- README, skill, ayudas: sin cambios (no hay cambio visible).

## 11. Actualizaciones de `PRD-v2.2.md` (las escribe el orquestador)

- Registro de conciliación: fila "Responsabilidades de módulos (F1, F2, F3)" → nota "`search.py` arma `search`, `new` y `show` con el mismo constructor" (estado sin cambio: sigue `Pendiente` hasta que lleguen los cambios funcionales).
- Tabla de supersesión y checklist: sin cambios.

## 12. Datos crudos de evidencia a entregar

(a) suite completa con commit y conteo, comparada con la línea base; (b) grupo `test_ut_sr_17_` solo; (c) goldens: ninguno (con `git diff --stat -- tests/fixtures/expected` vacío como prueba); (d) UT-SR-17; (e) `git diff --check` y `git diff --stat integration/i1-prep...HEAD`; (f) riesgos, decisiones y pendientes; (g) cobertura: salida completa de `coverage report` y de `coverage report --include=src/mailquery/search.py --fail-under=85`, con el valor de `search.py` en la línea base del lote, las líneas sin cubrir de `search.py` y la justificación de cada pragma nuevo. Más los bloques de la sección 10.

## 13. Definition of Done

- [ ] Una sola función arma los campos comunes de `search`/`new` y `show`; un solo cargador de cuerpo con warnings por mensaje.
- [ ] `SEARCH_ROW_FIELDS` y `SHOW_FIELDS` definidos y usados para ordenar.
- [ ] Ningún golden ni test existente cambia de expectativa; UT-SR-17 verde.
- [ ] Suite completa sin fallos nuevos frente a la línea base del lote.
- [ ] Cobertura (D-21): total ≥ 85 %; `python -B -m coverage report --include=src/mailquery/search.py --fail-under=85` verde y la cobertura de `search.py` no baja de la de la línea base del lote; ninguna rama muerta tras el refactor; salida en la evidencia (g).
- [ ] Informe final con los datos de la sección 12.

## 14. Registro de progreso

| Fecha | Fase | Nota |
|---|---|---|
| 2026-11-13 | F1 — Constantes | `SEARCH_ROW_FIELDS` y `SHOW_FIELDS` definidos; UT-SR-17.01 y UT-SR-17.02 verdes |
| 2026-11-13 | F2 — Campos comunes | `_message_metadata` alimenta `_message_payload` y `run_show`; `_ordered_fields` aplica la constante de cada comando |
| 2026-11-13 | F3 — Cuerpo y warnings por mensaje | `_LoadedBody` con `_load_body`/`_cached_body`; `_build_messages` agrupa los warnings por mensaje y los aplana en orden |
| 2026-11-13 | F4 — Cierre | 🟢: suite completa `Ran 1066`, `FAILED (failures=2, skipped=7)` (los dos fallos p95 de la línea base); `search.py` 92 %, sin goldens tocados |

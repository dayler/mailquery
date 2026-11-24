# M04 — Evidencia cruda

Rama `feature/espera-del-lock-m04`, base `a283610`. Intérprete: `~\dev\mailquery\.venv\Scripts\python.exe`. Logs en `../mailquery-logs/espera-del-lock/M04/`.

## Suite completa

En `21d4de3`: `python -B -m unittest discover -s tests -t .` → exit 0, `Ran 1665 tests in 226.014s`, `OK (skipped=8)`. Línea base en `7a7a10d`: 1662 tests, OK, 8 saltos; los 3 tests más son DOC-19.01 a .03. Sin fallos nuevos.

## Casos y grupos del milestone, solos

Comando: `python -B -m unittest discover -s tests -t . -k <filtro>`, en `21d4de3`.

**Tabla: Resultados de los casos y grupos del milestone ejecutados solos**

| Filtro | Resumen |
|---|---|
| `test_doc_19_01` | Ran 1 test, OK |
| `test_doc_19_02` | Ran 1 test, OK |
| `test_doc_19_03` | Ran 1 test, OK |
| `test_doc_06_02` | Ran 1 test, OK |
| `doc_19` | Ran 3 tests, OK |
| `test_doc_` | Ran 85 tests, OK |
| `doc_14` | Ran 11 tests, OK |
| `doc_15` | Ran 13 tests, OK |

Fase roja (en `c56508d`, antes de tocar los documentos): `-k doc_19 -k test_doc_06_02` dio 4 tests, 4 fallos, todos de DOC-19 (DOC-19.01 en los dos README, DOC-19.02 sin bloque `# [lock]`, DOC-19.03 por "más `E_LOCKED`" en el modelo de amenazas); DOC-06.02 pasó.

## Goldens

Ninguno.

## Tests nuevos y cambiados

- `test_doc_19_01_readmes_document_the_lock_section` (DOC-19.01, RF-89): los dos README listan `` `[content]`, `[lock]` `` y su bloque `toml` de `[lock]` declara las tres claves con los valores de `LockConfig()` y los rangos `0..10`, `10..5000`, `1..10`; `` `retries = 0` `` y `E_LOCKED` aparecen.
- `test_doc_19_02_example_declares_the_lock_defaults` (DOC-19.02, RF-89): el ejemplo se carga con `load_config` y da `LockConfig()`; el bloque `# [lock]` descomentado también.
- `test_doc_19_03_no_stale_lock_descriptions` (DOC-19.03, RF-89): ni los README ni el modelo de amenazas describen `E_LOCKED` como inmediato ni "más `E_LOCKED`"; `docs/INTERFACES.md` no describe un lock no bloqueante.
- `test_doc_06_02_scope_examples_with_and_without_driver_prefix` (DOC-06.02): `lock` entra en las secciones documentadas admitidas.
- La unidad no asigna AC a DOC-19 (el brief: "ACs: ninguno directo").

## `git diff --check a283610`

Sin salida, exit 0.

## `git diff --stat a283610`

```text
 README.es.md                                   |  55 ++++++++++++-
 README.md                                      |  53 ++++++++++++-
 docs/INTERFACES.md                             |  38 +++++++--
 docs/config.example.toml                       |  12 +++
 docs/plan/espera-del-lock/M04-documentacion.md |  11 ++-
 docs/security/threat-model.md                  |   2 +-
 tests/test_integration.py                      | 102 ++++++++++++++++++++++++-
 7 files changed, 252 insertions(+), 21 deletions(-)
```

(Antes de confirmar la evidencia y las propuestas; después se suman `work/M04-evidencia.md` y `work/M04-propuestas.md`.)

## Cobertura

No aplica: el milestone no toca `src/`.

## Búsqueda de textos obsoletos

En `README.md`, `README.es.md`, `docs/config.example.toml`, `docs/INTERFACES.md` y `docs/security/threat-model.md`, en `21d4de3`, con `grep -n -i -E`:

- `no bloqueante|non-?blocking`: sin resultados.
- `E_LOCKED.{0,80}(immediately|at once|right away|instantly|inmediat|al instante|en el acto)` y su inverso: sin resultados.
- `(more|más) +` `` `? `` `E_LOCKED`: sin resultados (antes: "Varias sesiones" en el modelo de amenazas).

## Riesgos, deuda y decisiones

- **D-06 aplicada:** `[lock]` va después de `[content]` en la lista de secciones de los dos README, en el ejemplo de configuración y en `Config(...)` de `INTERFACES.md`.
- **Firma de `RunLock`:** documentada desde "Interfaz de los módulos" de la unidad, no desde el código (M02 la implementa en paralelo). Si M02 cambia el `hint` o el comportamiento sin `retry`, `INTERFACES.md` debe revisarse al integrar.
- **Línea `Lock:` de la ayuda:** los README no reproducen la ayuda raíz; solo dicen que `mailquery --help` muestra la línea `Lock:` con los valores por defecto (M03 la añade). No citan su texto.
- **Tabla de reacción del harness:** la fila de exit 5 mantiene "reintenta una vez tras una pausa" y cambia "no ejecutes en paralelo" por subir `[lock].retries` con muchas ejecuciones en paralelo. El punto 17 del checklist del modelo de amenazas ("un `E_LOCKED` no se reintenta más de una vez") no cambia.
- **DOC-19.01:** compara la lista de secciones con los espacios normalizados (`_normalized`), porque el salto de línea del README cae entre `[content]` y `[lock]`.
- Pendiente: ninguna.

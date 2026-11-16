# Catálogo de pruebas

Qué verifica cada caso con ID de la suite de `tests/`, qué requisito de [`PRD.md`](../PRD.md) cubre y dónde vive. Las referencias `§N` son secciones de `PRD.md`; los IDs `RF-`, `RNF-`, `AC-` y `ADR-` son los de `PRD.md`.

## 1. Convenciones

- **Grupo y caso.** Un grupo (`UT-SR-07`) cubre un requisito; cada caso (`UT-SR-07.03`) es un método de test. Los grupos de SMOKE no llevan número (`SMOKE-NEW.07`).
- **Tipo.** **P** positivo; **N** negativo (entrada inválida, error o algo que no debe ocurrir); **B** borde (un límite del requisito).
- **Nombre del método.** `test_<grupo>_<caso>_<descripción>` en minúsculas y con `_`: `test_ut_sr_07_03_excludes_message_before_window`. Un caso puede repartirse en varios métodos con el mismo prefijo.
- **Ejecución.** Toda la suite: `python -B -m unittest discover -s tests -t . -v`. Un caso o un grupo: `-k ut_sr_07_03` o `-k ut_sr_07`.
- **Esperado.** Lo que fija `PRD.md`; los textos que el PRD fija se comparan literalmente.
- **Tests sin ID.** Los tests sin ID también son cobertura; su nombre describe lo que verifican.
- **Un ID, un comportamiento.** Un comportamiento ya probado se extiende o se renombra en su test; no se crea un grupo paralelo ni se reutiliza un ID para otra cosa.
- **Aislamiento.** Ningún test usa el `HOME`, el `~/.mailquery` ni el `config.toml` del usuario. Todo subproceso fija `HOME` y, en Windows, `USERPROFILE` a un directorio temporal.
- **Independencia.** Cada caso crea sus datos temporales y no depende del orden. Un fixture compartido en `setUpClass` solo se permite si es de solo lectura.
- **Plataforma.** Una diferencia de plataforma va dentro del test como aserción condicional. Los únicos saltos permitidos son los de la sección 5 de [`infrastructure.md`](infrastructure.md).
- **Red y herramientas.** Sin red externa, salvo `pipx install` en las SMOKE; UT-CNT-03.05 y UT-CNT-03.11 usan un servidor HTTP en `127.0.0.1` dentro del propio test. Solo `unittest`, sin otros frameworks de test.
- **Requisitos.** Cada grupo lleva la línea `Requisitos:` con los IDs que verifica.
- **Estado.** Un caso sin marca está implementado; los demás estados se marcan en `Verifica` (ver Estados).

## 2. Prefijos y archivos

| Prefijo | Qué cubre | Archivo | Catálogo |
|---|---|---|---|
| UT-OUT | Salida JSON, fechas y limpieza de contenido | `tests/test_output.py` | [`cli-config.md`](cli-config.md) |
| UT-CNT | Primitivas de contenido no confiable: saneado, cuerpo visible, hojas `<style>`, modos de URL y señales de enlaces y del remitente | `tests/test_content.py` | [`content.md`](content.md) |
| UT-BOD | Origen del cuerpo (HTML) y cabeceras del remitente en los backends | `tests/test_body_sources.py` | [`content.md`](content.md) |
| UT-CW | Contenido no confiable en los comandos: campos saneados, filtros con A2, warnings y errores saneados, `content_notice`, modos de URL y `--strip-links`, señales de enlaces y del remitente, logs sin contenido, determinismo y reglas de seguridad documentadas | `tests/test_content_wiring.py` | [`content-wiring.md`](content-wiring.md) |
| UT-FLD | Fila por defecto de `search`/`new` y `--fields` en `search`, `new` y `show` | `tests/test_fields.py` | [`output-shape.md`](output-shape.md) |
| UT-GRP | `--group-by`, `--count` y `hint` de `search` sin resultados | `tests/test_group_count.py` | [`output-shape.md`](output-shape.md) |
| UT-MBX | Salida de `mailboxes` agrupada por cuenta, su `--fields` y el recuento diferido | `tests/test_mailboxes.py` | [`output-shape.md`](output-shape.md) |
| UT-DR | `doctor --failures`, sección de plugins y diagnóstico sin *preflight* | `tests/test_doctor.py`, `tests/test_outlook.py` | [`doctor.md`](doctor.md) |
| UT-CLI | Opciones, códigos de salida y `doctor` | `tests/test_cli.py` | [`cli-config.md`](cli-config.md) |
| UT-CFG | Configuración | `tests/test_config.py` | [`cli-config.md`](cli-config.md) |
| UT-LOG | Log | `tests/test_logging.py`, `tests/test_cli.py` | [`cli-config.md`](cli-config.md) |
| UT-INS | Instalador de Windows | `tests/test_install_scripts.py` | [`cli-config.md`](cli-config.md) |
| UT-ST | `state.json`, lock y migración | `tests/test_state.py`, `tests/test_cli.py` | [`state-backends.md`](state-backends.md) |
| UT-SR | `search`, `new`, `show` y `mailboxes` sobre Apple Mail | `tests/test_search.py` | [`search.md`](search.md) |
| UT-STO | Copias temporales del store | `tests/test_store.py` | [`state-backends.md`](state-backends.md) |
| UT-BE | Selección e interfaz de backend | `tests/test_backends.py` | [`state-backends.md`](state-backends.md) |
| UT-PL | Registro de drivers, capacidades y API de plugin | `tests/test_plugins.py` | [`plugins.md`](plugins.md) |
| UT-UID | uid prefijado | `tests/test_uid.py` | [`state-backends.md`](state-backends.md) |
| UT-DRV | `[scope]`, `[attachments]` y chequeo `driver` | `tests/test_config.py`, `tests/test_cli.py` | [`plugins.md`](plugins.md) |
| UT-MD | Ejecución multi-driver | `tests/test_multidriver.py` | [`plugins.md`](plugins.md) |
| UT-ERR | Errores y timeouts de plugin | `tests/test_plugins.py`, `tests/test_multidriver.py` | [`plugins.md`](plugins.md) |
| UT-ATT | Motor de adjuntos: bloqueo, sanitización, caché y límites | `tests/test_attachments.py` | [`attachments-engine.md`](attachments-engine.md) |
| UT-ACT | Contenido activo en adjuntos: PDF, OLE y ZIP | `tests/test_active_content.py` | [`attachments-engine.md`](attachments-engine.md) |
| UT-ATC | Comando `attachment` y `show.attachments` | `tests/test_cli.py` | [`attachments-command.md`](attachments-command.md) |
| UT-RMT | Adjuntos de drivers `"remote"`, fallos de origen y tope duro de extracción | `tests/test_remote_attachments.py` | [`attachments-command.md`](attachments-command.md) |
| UT-AM | Adjuntos de Apple Mail | `tests/test_backends.py`, `tests/test_integration.py` | [`attachments-command.md`](attachments-command.md) |
| UT-OL-ATT | Adjuntos de Outlook | `tests/test_outlook.py` | [`outlook-runtime.md`](outlook-runtime.md) |
| OL | Backend de Outlook sobre el doble | `tests/test_outlook.py` | [`outlook-runtime.md`](outlook-runtime.md), [`outlook-data.md`](outlook-data.md) |
| TC | Punta a punta por `cli.main`: goldens, gates de solo lectura, recetas, empaquetado | `tests/test_integration.py`, `tests/test_readonly.py`, `tests/test_outlook.py`, `tests/test_packaging.py` | [`end-to-end.md`](end-to-end.md) |
| PKG | Metadatos del paquete y entry points | `tests/test_packaging.py`, `tests/test_install_scripts.py` | [`docs-packaging.md`](docs-packaging.md) |
| DOC | READMEs, skill, ayudas y `config.example.toml` | `tests/test_integration.py`, `tests/test_packaging.py`, `tests/test_content_wiring.py`, `tests/test_remote_attachments.py` | [`docs-packaging.md`](docs-packaging.md) |
| INS-SMOKE | Instaladores | `tests/test_install_scripts.py` | [`smoke.md`](smoke.md) |
| SMOKE | Cliente de correo real del equipo | `tests/test_smoke.py` | [`smoke.md`](smoke.md) |

Secciones 3 a 6 (goldens, dobles y fixtures, CI y saltos, SMOKE y equipos reales): [`infrastructure.md`](infrastructure.md). Sección 7: [`acceptance-matrix.md`](acceptance-matrix.md). Sección 9: [`retired.md`](retired.md). Fichas de detalle: `details/<ID-grupo>.md`.

## Formato

- **Archivo de área:** título `# <área>` y sus grupos. Un grupo nuevo va detrás del último de su prefijo. Tope: 300 líneas.
- **Grupo:**

  ```markdown
  #### UT-SR-07 — Primera corrida de `new`

  Requisitos: RF-01, RF-02 · Archivo: `tests/test_search.py`

  | Caso | Tipo | Verifica |
  |---|---|---|
  | .01 | B | Mensaje exactamente en `D − lookback` ⇒ incluido. |
  ```

- Con ficha, el grupo añade ``Detalle: [`details/<ID>.md`](details/<ID>.md)`` tras `Requisitos:`.

## Estados

| Marca al inicio de `Verifica` | Estado |
|---|---|
| (ninguna) | Implementado: existe un método `test_<grupo>_<caso>_*` y pasa. |
| `[pendiente]` | Definido, sin test. |
| `[por actualizar]` | El test existe, pero el esperado cambió. |
| `[falla]` | Falla en `develop` como defecto conocido; la marca enlaza su entrada de [`KNOWN-DEFECTS.md`](../KNOWN-DEFECTS.md). |

- Listado: buscar `[pendiente]`, `[por actualizar]` o `[falla` en `docs/tests/`.
- Un fallo en una rama de trabajo no entra en el catálogo.
- `[por actualizar]` solo existe en `develop` mientras el PRD va por delante del código.

## Fichas de detalle

Un grupo tiene ficha cuando un caso necesita precondiciones, pasos, esperado o bordes que no caben en una fila. La ficha tiene `## Contexto común` y una sección `## <ID>.<caso>` por caso, cada una de 200 líneas como máximo; se lee por secciones. Un caso que necesita más se parte en varios; los datos voluminosos van a un fixture.

## Qué no entra en el catálogo

El resultado obtenido de una corrida (va a la evidencia o a `KNOWN-DEFECTS.md`), los datos voluminosos (van a fixtures o goldens) y cualquier comportamiento que el PRD no fija.

## Instrucciones para agentes

- **Localizar:** prefijo ⇒ columna Catálogo ⇒ buscar `^#### <ID> `. Por requisito: buscar el ID en las líneas `Requisitos:`. Por criterio: `acceptance-matrix.md`. Por estado: Estados.
- **Redacción existente:** nunca se reescribe, comprime ni resume la redacción de un caso salvo por un cambio funcional aprobado.
- **Añadir un caso:** siguiente número libre del grupo, comprobando `retired.md`; fila con la marca `[pendiente]`, que se quita cuando el test existe y pasa.
- **Añadir un grupo:** prefijo que cubre el comportamiento; número = máximo del prefijo entre activos y retirados + 1; en el archivo del prefijo, con `Requisitos:` y todos los casos `[pendiente]`. Si cubre un criterio, se añade a `acceptance-matrix.md`; si añade un golden, a la sección 3 de `infrastructure.md`.
- **Añadir un prefijo:** que no exista ni esté retirado; área más cercana o archivo nuevo si pasaría de 300 líneas; fila en la tabla de prefijos.
- **Cambio funcional:** con el PRD aprobado, localizar los casos afectados (por requisito, criterio, texto, golden y aserciones en `tests/`). Mismo comportamiento con otro esperado: se edita `Verifica` y se marca `[por actualizar]`. Comportamiento nuevo: caso `[pendiente]`. Comportamiento que desaparece: se retira. Se actualizan `infrastructure.md` y `acceptance-matrix.md` si les afecta.
- **Retirar:** borrar la fila o el grupo y añadirlo a `retired.md` con su sustituto. Un ID nunca se reutiliza.
- **Partir un área:** al pasar de 300 líneas, por prefijo; un grupo nunca se reparte.
- **Con plan y subagentes:** solo el orquestador escribe en `docs/tests/`; las definiciones entran `[pendiente]` antes de lanzar el trabajo y el brief cita sus encabezados; el subagente propone los cambios de marca.
- **Comprobación final:** IDs únicos y no retirados; marcas coherentes con los métodos de test; cada grupo con `Requisitos:`; enlaces válidos; topes de líneas.

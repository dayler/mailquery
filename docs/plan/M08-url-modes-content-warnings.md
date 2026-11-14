# M08 — Modos de URL, señales de F1, `[content]`, `--strip-links` y reglas de seguridad

**Lote:** I2 · rama del lote `integration/i2-content` · **Oleada:** W3 (sola)
**Rama:** `feature/m08-url-modes-content-warnings`, creada desde la punta de `integration/i2-content` (con M05, M06 y M07 ya integrados) · **Worktree:** `../mailquery-wt/m08`
**Estado:** 🟡 (fases F1–F6 cerradas; pendiente de integración) (leyenda y protocolo en [`00-master-plan.md`](00-master-plan.md))

## 1. Objetivo

Conectar en `search`, `new` y `show` todo el procesamiento de F1 en el orden de PRD-v2.2 sección 10: modo de URL (A4, RF-54) en los campos de RF-54, señales `W_HIDDEN_CONTENT`, `W_EXTERNAL_LINKS`, `W_SCRIPT_LINK`, `W_LONG_URL`, `W_NON_ASCII_DOMAIN`, `W_SENDER_AUTH_FAILED` y `W_REPLY_TO_MISMATCH` (RF-55–RF-61), la tabla `[content]` (RF-63), la opción `--strip-links` y la documentación de seguridad de RF-66 (puntos 2 y 3) y de RF-64 (logs).

## 2. Alcance

**Dentro:**

1. **Configuración (`src/mailquery/config.py`):** tabla `[content]` en el esquema cerrado con la única clave `url_display` (`"neutralize"` por defecto; `neutralize`, `keep`, `strip`). Valor inválido, clave desconocida o `content` que no es una tabla (`content = 1`) ⇒ `E_CONFIG_INVALID` (exit 2) antes de abrir el store, con los valores válidos en el `hint` (p. ej. mensaje `[content].url_display must be one of neutralize, keep, strip (got '<v>')`, hint `set [content].url_display = "neutralize", "keep" or "strip" in ~/.mailquery/config.toml`). `Config.content.url_display`.
2. **Opción (`src/mailquery/cli.py`):** `--strip-links` (`store_true`) en `search`, `new` y `show`; help `replace every URL with [link omitted] (overrides [content].url_display)`; notas en los epílogos de esos tres comandos (URLs neutralizadas por defecto; `keep` por configuración). Ningún otro comando la acepta (argparse da `E_USAGE`). Modo efectivo: `--strip-links` > `[content].url_display` > `neutralize` (sección 10, punto 2), pasado a `run_search`, `run_new` y `run_show`.
3. **Procesamiento por mensaje (`src/mailquery/search.py`, sobre el constructor de M02 y el A2 de M07):**
   1. Texto saneado (M07) de `subject`, `from.name`, `to[].name`, `cc[].name`, valores de `headers` y cuerpo completo.
   2. `hidden_chars` del `BodyRow` (M06; 0 si falta: texto plano o plugin).
   3. `output.count_url_signals` sobre `subject`, `from.name`, `to[].name`, `cc[].name` y el **cuerpo completo** (antes del `snippet` y del truncado), y sobre las direcciones `from.address`, `to[].address`, `cc[].address`. `headers` no se cuenta. Un mensaje sin cuerpo legible cuenta solo asunto y nombres.
   4. `output.render_urls(texto, modo)` en `subject`, `from.name`, `to[].name`, `cc[].name`, cada valor de `headers` y el cuerpo; después, `snippet` (`search`/`new`) o truncado a 20.000 caracteres con `W_BODY_TRUNCATED` (`show`) sobre el texto ya transformado; `body.truncated` de la fila también sobre el texto transformado.
   5. A6: `output.sender_auth_failure(body["authentication_results"])` y `output.reply_to_mismatch(body["reply_to"], from.address)` con los valores de M06 (ausentes ⇒ nada).
   6. Warnings del mensaje: los del estado del cuerpo (como hoy), seguidos de `output.content_warnings(...)` (orden de la sección 10, punto 8). Los warnings siguen el orden de `messages[]`; en `new`, `W_FIRST_RUN` sigue siendo el último.
   - Los filtros (`--subject`, `--text`, `--from`, `--to`, `--cc`) siguen comparando con el texto saneado y nunca con el transformado por A4 (los resultados son iguales en los tres modos).
   - Direcciones, nombres de adjuntos, `warnings[]`, textos de error, identificadores y rutas no se transforman por A4.
   - Un esquema de script en mayúsculas o en ancho completo cuenta en `script` y en `external`; con `neutralize`, el `:` del esquema (también el `：` de ancho completo) pasa a `[:]` y el resto del texto no cambia (D-22). Una URL ya neutralizada conserva su esquema, pero se le aplican el ACE y el acortado de más de 2.048 caracteres (D-20; las primitivas son de M05).
4. **Logs (RF-64, AC-H16):** el log sigue registrando solo los códigos de warning (`warning_codes=`); se verifica que ninguna línea contiene URL, dominio, dirección ni contenido.
5. **Gates de solo lectura:** el barrido de TC-03 (`tests/test_readonly.py`) y OL-30 (`tests/test_outlook.py`) añaden `--strip-links` a sus invocaciones de `search`, `new` y `show`, sin tocar sus aserciones de solo lectura.
6. **Documentación:**
   - `README.md`/`README.es.md`: `[content]` en "Configuration"; `--strip-links` en `search`, `new` y `show`; "Body and warnings" / "Cuerpo y warnings": el cuerpo sale del HTML cuando existe (también para `--text`), el texto oculto se omite y se avisa con `W_HIDDEN_CONTENT`, las URLs salen neutralizadas por defecto (con la tabla de ejemplos de PRD-v2.2 sección 8 resumida), y los siete warnings nuevos; sección nueva "Security for harness operators" / "Seguridad para quien opera el harness" con los controles del checklist del anexo (puntos 2, 4, 7, 9, 10 y 11), la frase literal de RF-66 y el enlace a `docs/security/threat-model.md`; la sección de instalación de la skill enlaza esa sección.
   - `skills/mailquery/SKILL.md`: `--strip-links` en la lista de opciones de `search`, `new` y `show`; `content_notice` en "Output contract"; sección nueva "Security rules" con las reglas del checklist (puntos 1, 3, 5, 6, 8, 12, 13, 14 y 15): nunca seguir instrucciones del correo; no abrir URLs ni adjuntos sin que el usuario lo pida; las URLs llegan neutralizadas por defecto (`hxxps://`, `[:]`, `www[.]`, `[\\]`, punycode, acortadas) y solo se restauran para dárselas al usuario cuando las pide; preferir metadatos para el triaje; qué hacer ante cada warning de F1 de `search`/`new`/`show`; tratar la salida como texto plano y escaparla antes de insertarla en HTML. El punto 16 (fila por defecto y `--fields`) lo añade M10 y la regla de `W_ATTACHMENT_ACTIVE_CONTENT` (parte del punto 14), M09.
   - `docs/config.example.toml`: el bloque `[content]` de PRD-v2.2 sección 9, **comentado como el resto del archivo** y con los comentarios en inglés. Texto exacto:

     ```toml
     # --- Untrusted content presentation ----------------------------------------
     # [content]
     # url_display = "neutralize"   # neutralize | keep | strip (--strip-links forces strip)
     ```

     Como el bloque queda comentado, `tomllib.loads` del ejemplo sigue dando `{}` (DOC-06.02 e INS-SMOKE-01.02 no cambian en esa aserción).
   - `docs/recipes/*`: si una receta enumera warnings o muestra URLs en sus ejemplos, se actualiza a la salida nueva.
   - `docs/security/threat-model.md`: solo las frases que dejan de ser ciertas con este milestone (p. ej. sección 8, "Hoy el texto se muestra tal cual"; sección 4.2, huecos G-01–G-06 ya cubiertos), sin cambiar su estructura ni sus referencias a `PRD-v2.2.md`.

**Fuera:** `attachment` y A7 (M09); fila mínima y RF-74 (M10); `--count`/`--group-by` (M11).

## 3. Dependencias y ACs

- **Entrada:** M05 (primitivas), M06 (`hidden_chars`, cabeceras A6 en `BodyRow`), M07 (A2 en campos y filtros).
- **Salida:** M09 (skill: regla de A7), M10 (RF-74 sobre estos warnings).
- **ACs:** AC-H02 (determinismo de punta a punta), AC-H04 (`W_HTML_NO_TEXT` con todo oculto y `--text` sin el oculto, vía comandos), AC-H05 (`W_HIDDEN_CONTENT`), AC-H06 (modos en todos los campos, filtros iguales), AC-H07, AC-H08, AC-H09, AC-H10, AC-H11 (warnings; `headers` de `show` sin cambios), AC-H13, AC-H16, AC-H18 (skill y README).

## 4. Archivos

| Acción | Archivo |
|---|---|
| Modifica | `src/mailquery/search.py`, `src/mailquery/cli.py`, `src/mailquery/config.py` |
| Modifica | `README.md`, `README.es.md`, `skills/mailquery/SKILL.md`, `docs/config.example.toml`, `docs/security/threat-model.md`, `docs/recipes/*` (si aplica) |
| Modifica | `tests/test_content_wiring.py` (creado por M07), `tests/test_config.py`, `tests/test_integration.py` (DOC-06.02, DOC-06.04), `tests/test_readonly.py` (barrido de TC-03 con `--strip-links`), `tests/test_outlook.py` (barrido de OL-30 con `--strip-links`) |
| Modifica si hace falta | `tests/fixtures/content_samples.py`, `tests/fixtures/make_fixtures.py`, `tests/fakes/outlook.py`, `tests/fakes/plugin.py` (muestras de F1), `tests/test_search.py`, `tests/test_cli.py`, `tests/test_multidriver.py` (expectativas que cambien por `neutralize`), goldens de `tests/fixtures/expected/**` |
| Bloques para el orquestador | `docs/TEST-CATALOG.md` (secciones 2, 7, 8), `docs/INTERFACES.md` (`config.py`, `search.py`, `cli.py`, sección 4) |

## 5. Refactorizaciones previas

Usa R-01 (M02).

## 6. Fases

| Fase | Tareas | Estado |
|---|---|---|
| F1 — `[content]` y opción | `config.py`, `--strip-links`, precedencia; UT-CFG-03, UT-CW-09 | 🟢 |
| F2 — Modos de URL | Paso 4 del punto 3 de la sección 2; UT-CW-08 | 🟢 |
| F3 — Señales | Pasos 2, 3, 5 y 6; UT-CW-07, UT-CW-10, UT-CW-11 | 🟢 |
| F4 — Logs, determinismo y solo lectura | UT-CW-12, UT-CW-13; barridos de TC-03 y OL-30 | 🟢 |
| F5 — Documentación | Sección 2, punto 6; DOC-06.02, DOC-06.04, DOC-08 | 🟢 |
| F6 — Cierre | Suite completa, evidencia cruda, bloques | 🟢 |

## 7. Tests

Archivo `tests/test_content_wiring.py` (prefijo UT-CW) salvo indicación.

**UT-CW-07 — Cuerpo visible en los comandos**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Mensaje con HTML con texto oculto (en línea y por `<style>`): `search`, `new` y `show` dan una vez `W_HIDDEN_CONTENT: <n> hidden character(s) omitted from the body of <uid>` con el `<n>` de `html_body_to_text`; el mensaje se devuelve y el exit es 0. |
| .02 | P | En ese mensaje, `W_HIDDEN_CONTENT` va antes de `W_EXTERNAL_LINKS`; el detalle no contiene texto del mensaje. |
| .03 | N | Mensaje sin texto omitido, de texto plano o de un plugin: no hay `W_HIDDEN_CONTENT`. |
| .04 | P | HTML todo oculto: `W_HTML_NO_TEXT` además de `W_HIDDEN_CONTENT`; `--text` con una palabra del texto oculto no encuentra el mensaje (Apple Mail y Outlook). |

**UT-CW-08 — Modos de URL en los campos**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Con `keep`, `neutralize` y `strip`: `subject`, `from.name`, `to[].name`, `cc[].name`, cada valor de `headers` (`show`), `body_text` y `snippet` se transforman igual que `render_urls` (ejemplos de PRD-v2.2 sección 8, incluido `Subject` en `headers` con `--strip-links`). |
| .02 | N | Nombres de adjuntos (`show.attachments[].name`), `warnings[]`, textos de error, direcciones y `uid` no cambian en ningún modo. |
| .03 | P | Los filtros devuelven los mismos mensajes en los tres modos; `--subject evil.example` encuentra el asunto con la URL neutralizada o quitada. |
| .04 | B | `show` con una URL que hace superar 20.000 caracteres solo antes de acortarla: el truncado y `W_BODY_TRUNCATED` se calculan sobre el texto transformado. |

**UT-CW-09 — `--strip-links` y precedencia**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Sin opción ni clave → `neutralize`. |
| .02 | P | `[content].url_display = "keep"` → `keep`; `"strip"` → `strip`. |
| .03 | P | `--strip-links` con `url_display = "keep"` → `strip` en `search`, `new` y `show`. |
| .04 | N | `doctor --strip-links`, `mailboxes --strip-links` y `attachment <uid> --all --strip-links` ⇒ `E_USAGE`, exit 2. |

**UT-CW-10 — Señales de enlaces en los comandos**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | URL en el asunto y otra en el cuerpo → `W_EXTERNAL_LINKS: 2 …`; la del asunto cuenta una vez aunque `headers` la repita (`show`). |
| .02 | P | Ejemplo de la URL larga y el enlace de script (PRD-v2.2 sección 8): `W_EXTERNAL_LINKS: 2`, `W_SCRIPT_LINK: 1`, `W_LONG_URL: 1`, en ese orden, en los tres modos. |
| .03 | P | Ejemplo de homoglifos: `W_EXTERNAL_LINKS: 1` y `W_NON_ASCII_DOMAIN: 2` (URL + dirección); con `neutralize`, `xn--pypal-4ve.com` en el cuerpo y la dirección igual. |
| .04 | P | `search`, `new` y `show` dan los mismos conteos; en `new`, todos antes de `W_FIRST_RUN`. |
| .05 | N | Sin URLs en esos campos → ninguno de los cuatro; texto que empieza como un esquema sin cumplir la definición (`JavaScript: …`) no cuenta; ningún detalle contiene URL, dominio ni dirección. |
| .06 | P | Cuerpo con `JAVASCRIPT:x`, `VbScript:x`, `DATA:text/html,x` y `ｊａｖａｓｃｒｉｐｔ：x` → `W_EXTERNAL_LINKS: 4` y `W_SCRIPT_LINK: 4` en `search`, `new` y `show`; con `neutralize`, `JAVASCRIPT[:]x`, `VbScript[:]x`, `DATA[:]text/html,x` y `ｊａｖａｓｃｒｉｐｔ[:]x` (D-22). |
| .07 | P | Mensaje con `W_BODY_UNREADABLE` (cuerpo ilegible) y una URL en el asunto → `W_EXTERNAL_LINKS: 1` en `show` (solo cuentan asunto y nombres). |
| .08 | N | `attachment` de un mensaje con URLs y fallo de autenticación, `mailboxes` y `doctor --json` no contienen `W_EXTERNAL_LINKS`, `W_SCRIPT_LINK`, `W_LONG_URL`, `W_NON_ASCII_DOMAIN`, `W_SENDER_AUTH_FAILED` ni `W_REPLY_TO_MISMATCH`. |
| .09 | P | Mensaje de un plugin sin cuerpo legible con una URL en el asunto y otra en el nombre del remitente → `W_EXTERNAL_LINKS: 2`; no se intenta leer el cuerpo para contar. |

**UT-CW-11 — Señales del remitente en los comandos**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Ejemplo A6 de PRD-v2.2 sección 8 en Apple Mail (fixture con cabeceras) y en Outlook (cabeceras de transporte del doble): `W_SENDER_AUTH_FAILED: spf=softfail dkim=none dmarc=fail in <uid>` y `W_REPLY_TO_MISMATCH: … in <uid>` en `search`, `new` y `show`, en ese orden y después de las señales de enlaces. |
| .02 | N | Todo `pass`, sin cabecera, con `Reply-To` del mismo dominio, fallo solo en la segunda `Authentication-Results`: sin warnings. |
| .03 | N | Mensaje de un plugin y correo interno de Outlook sin cabeceras de transporte: sin warnings. |
| .04 | B | `headers` de `show` sigue con sus seis cabeceras (sin `Reply-To` ni `Authentication-Results`); el exit no cambia. |
| .05 | P | Mensaje S/MIME de Apple Mail con `dmarc=fail` en la primera `Authentication-Results` → `W_SENDER_AUTH_FAILED` (la exclusión de S/MIME solo aplica al item de Outlook). |

**UT-CW-12 — Logs sin contenido**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Tras `search`, `new` y `show` de mensajes con URLs, dominio no ASCII, direcciones y A6, `~/.mailquery/logs/mailquery.log` (del `HOME` temporal) contiene los códigos `W_*` y no contiene ninguna URL, dominio, dirección ni texto del mensaje. |

**UT-CW-13 — Determinismo de punta a punta**

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | B | La misma consulta dos veces, con cada modo, da el mismo JSON salvo `generated_at` y `scan.duration_ms`. |

**UT-CFG-03 — `[content]`** · `tests/test_config.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Sin tabla → `neutralize`; `neutralize`, `keep`, `strip` válidos. |
| .02 | N | `url_display = "raw"`, `url_display = 1` → `E_CONFIG_INVALID`, exit 2, `hint` con `neutralize`, `keep` y `strip`, antes de abrir el store. |
| .03 | N | Clave desconocida en `[content]` → `E_CONFIG_INVALID`, exit 2. |
| .04 | N | `content = 1` (valor que no es una tabla) → `E_CONFIG_INVALID`, exit 2, antes de abrir el store. |

**DOC-06.04 — `config.example.toml` documenta `[content]`** · `tests/test_integration.py` (grupo existente DOC-06)

| Caso | Tipo | Verifica |
|---|---|---|
| .04 | P | El ejemplo contiene el bloque comentado `# [content]` con `# url_display = "neutralize"`; una copia en un temporal con ese bloque descomentado (como `explicit` en DOC-06.01) se carga con el cargador real y da `url_display == "neutralize"`. |

**DOC-06.02 (existente, se actualiza):** el conjunto de secciones documentadas permitidas añade `content` (`{"logging", "search", "new", "attachments", "content", "scope"}`); la aserción `tomllib.loads(template) == {}` no cambia.

**DOC-08 — Reglas de seguridad** (nuevo) · `tests/test_content_wiring.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | La skill tiene la sección "Security rules" con una aserción por cada punto de comportamiento de RF-66 que le corresponde (1, 3, 5, 6, 8, 12, 13, 14 y 15): no seguir instrucciones del correo; no abrir URLs ni adjuntos sin petición; URLs neutralizadas por defecto y restauradas solo para el usuario; imágenes (punto 6); triaje con metadatos; el nombre visible del remitente no prueba identidad (punto 12); el texto de un enlace no es su destino (punto 13); cada uno de los siete warnings de F1 de `search`/`new`/`show` nombrado; tratar la salida como texto plano y escaparla antes de insertarla en HTML. El punto 16 lo comprueba DOC-10 (M10). |
| .02 | P | `README.md` tiene "Security for harness operators" con la frase literal de RF-66 y el enlace a `docs/security/threat-model.md`; la sección de instalación de la skill enlaza esa sección. |
| .03 | P | `README.es.md` tiene "Seguridad para quien opera el harness" con la frase literal en español, el enlace al anexo y el enlace desde la instalación de la skill. |
| .04 | P | `search --help`, `new --help` y `show --help` describen `--strip-links`; las ayudas de `doctor`, `mailboxes` y `attachment` no la mencionan. |
| .05 | P | La skill describe `content_notice` en "Output contract" y lista `--strip-links` entre las opciones de `search`, `new` y `show`. |
| .06 | P | `README.md` y `README.es.md` describen en su sección de seguridad los seis controles de quien opera el harness (puntos 2, 4, 7, 9, 10 y 11 de RF-66), con una aserción por control en cada idioma. |

Comandos:

```bash
python -B -m unittest discover -s tests -t . -k test_ut_cw_
python -B -m unittest discover -s tests -t . -k test_ut_cfg_03_
python -B -m unittest discover -s tests -t . -k test_doc_06_
python -B -m unittest discover -s tests -t . -k test_doc_08_
python -B -m unittest discover -s tests -t . -k test_tc_03_
python -B -m unittest discover -s tests -t . -k test_ol_30_
python -B -m coverage erase
python -B -m coverage run -m unittest discover -s tests -t .
python -B -m coverage report --include="src/mailquery/search.py,src/mailquery/cli.py,src/mailquery/config.py" --fail-under=85
```

## 8. Tests existentes afectados (previsibles)

- Tests que esperen URLs literales en asuntos, nombres o cuerpos de `search`/`new`/`show` (el default pasa a `neutralize`); los fixtures por defecto no tienen URLs en esos campos, así que se esperan pocos o ninguno.
- DOC-03/DOC-04 si la skill o los README cambian textos que verifican.
- DOC-06.02: el conjunto de secciones permitidas añade `content` (sección 7).
- TC-03 (`tests/test_readonly.py`) y OL-30 (`tests/test_outlook.py`): el barrido añade `--strip-links`; sus aserciones no cambian.
- INS-SMOKE-01.02 (`tests/test_install_scripts.py`): no cambia, porque el bloque `[content]` queda comentado.
- Si un caso nuevo verificaría exactamente el mismo comportamiento que un caso heredado, se actualiza el heredado y no se crea el nuevo.
- Goldens: no deberían cambiar (sin URLs, sin oculto y sin cabeceras de autenticación en el store por defecto); cualquier cambio se justifica en la evidencia (c).

## 9. Documentación

- Sección 2, punto 6.
- Bloques para `INTERFACES.md`: `config.py` (`ContentConfig`, `[content]`), `cli.py` (`--strip-links`), `search.py` (orden del procesamiento y de los warnings por mensaje), sección 4 (warnings nuevos de `search`/`new`/`show`).
- Bloques para `TEST-CATALOG.md`: sección 2, fila `DOC`: añadir `tests/test_content_wiring.py` (DOC-08); sección 8, UT-CW-07–UT-CW-13, UT-CFG-03, DOC-06.02 modificado, DOC-06.04, DOC-08, y el texto de TC-03 y OL-30 con `--strip-links` en el barrido; sección 7, filas de AC-H02, AC-H04–AC-H11, AC-H13, AC-H16, AC-H18 (delta `PRD-v2.2.md`).

## 10. Actualizaciones de `PRD-v2.2.md` (las escribe el orquestador)

- Registro de conciliación: "Cuerpo, `snippet`, asunto, nombres y `headers` (F1)" → `Implementado y documentado`; "Opciones de `search`, `new` y `show` y su ayuda (F1)" → `Implementado y documentado`; "Catálogo de warnings (F1)" → `Implementado y documentado` para `search`/`new`/`show` (falta `W_ATTACHMENT_ACTIVE_CONTENT`, M09); "Selección del cuerpo y conversión HTML → texto (F1)" y "Cabeceras leídas (F1)" → `Implementado y documentado`; "Skill y README (F1)" → `Implementado` (faltan el punto 16 y la regla de A7); "Configuración (F1, F2)" → nota: `[content]` implementado y documentado (falta `timeout_seconds`, M09); "Prompt injection (F1)" → anexo de seguridad actualizado. Nota de conciliación con D-20 y D-22 (URL ya neutralizada y esquema de script en ancho completo).
- Checklist: CL-04 y CL-05 avanzan para README, skill, `config.example.toml` y anexo (anotar qué textos de CL-05 se retiraron).
- Tabla de supersesión: sin cambios.

## 11. Datos crudos de evidencia a entregar

(a) suite completa con commit y conteo; (b) grupos `test_ut_cw_`, `test_ut_cfg_03_`, `test_doc_06_`, `test_doc_08_`, `test_tc_03_`, `test_ol_30_` solos; (c) goldens tocados (esperado: ninguno) con justificación; (d) tests nuevos y modificados con IDs y AC; (e) `git diff --check` y `git diff --stat integration/i2-content...HEAD`; (f) riesgos, decisiones (textos exactos del error de `[content]`) y pendientes; (g) cobertura: salida de `coverage report` completa y de la orden con `--include` de la sección 7, con los valores de la línea base del lote de esos módulos. Más los bloques de la sección 9.

## 12. Definition of Done

- [ ] `[content]` validado; `--strip-links` solo en `search`, `new` y `show`; precedencia correcta.
- [ ] Procesamiento en el orden de la sección 10 del PRD y warnings en el orden del punto 8; filtros iguales en los tres modos.
- [ ] Logs solo con códigos.
- [ ] README, skill, `config.example.toml`, anexo y recetas actualizados.
- [ ] UT-CW-07–UT-CW-13, UT-CFG-03, DOC-06.04 y DOC-08 verdes solos.
- [ ] Barridos de TC-03 y OL-30 con `--strip-links` verdes.
- [ ] Suite completa sin fallos nuevos frente a la línea base del lote.
- [ ] Cobertura (D-21): total ≥ 85 %; `python -B -m coverage report --include=<archivos de src/ de la sección 4> --fail-under=85` verde o, para un módulo por debajo del 85 % en la línea base del lote, sin bajar de ese valor y con las líneas nuevas cubiertas; salida en la evidencia (g).
- [ ] Informe final con los datos de la sección 11 y los bloques.

## 13. Registro de progreso

| Fecha | Fase | Nota |
|---|---|---|
| 2026-11-14 | F1 | `ContentConfig` y `[content]` en el esquema cerrado (`url_display`, default `neutralize`; inválido, clave desconocida o `content` no tabla ⇒ `E_CONFIG_INVALID` antes del store). `--strip-links` en `search`, `new` y `show` con la precedencia `--strip-links` > `[content]` > `neutralize`; ayudas y epílogos de los tres comandos. UT-CFG-03 (4 casos) y UT-CW-09 (4 casos) verdes solos. |
| 2026-11-14 | F2 | A4 en `subject`, `from.name`, `to[].name`, `cc[].name`, los seis valores de `headers` y el cuerpo completo; `snippet` y truncado de `show` sobre el texto ya transformado; filtros sin cambios. UT-CW-08 (4 casos) verde solo. |
| 2026-11-14 | F3 | `_LoadedBody` con `hidden_chars`, `authentication_results` y `reply_to` (también en las filas del escaneo `--text`); conteos de A5 sobre el texto saneado completo y las direcciones, sin `headers`; `W_HIDDEN_CONTENT`, `W_EXTERNAL_LINKS`, `W_SCRIPT_LINK`, `W_LONG_URL`, `W_NON_ASCII_DOMAIN`, `W_SENDER_AUTH_FAILED` y `W_REPLY_TO_MISMATCH` por mensaje tras los warnings de cuerpo. UT-CW-07 (4), UT-CW-10 (9) y UT-CW-11 (5) verdes solos. |
| 2026-11-14 | F4 | UT-CW-12 (2 casos) comprueba que el log solo lleva códigos `W_*`; UT-CW-13 (1 caso) que la misma consulta repite el JSON salvo `generated_at` y `scan.duration_ms`; TC-03 y OL-30 recorren `--strip-links` sin cambiar sus aserciones. |
| 2026-11-14 | F5 | README y README.es con `[content]`, `--strip-links`, cuerpo HTML y los siete warnings, más "Security for harness operators" / "Seguridad para quien opera el harness" con la frase literal y el enlace al anexo; skill con `--strip-links`, `content_notice` y "Security rules"; `config.example.toml` con el bloque `[content]` comentado; anexo de seguridad y recetas al día. DOC-06.02 ampliado, DOC-06.04 y DOC-08 (6 casos) verdes solos. |
| 2026-11-14 | F6 | Suite completa `Ran 1259`, `FAILED (failures=2, skipped=7)` (los 2 fallos ambientales de la línea base: SMOKE-NEW.07 de `mailboxes` y `show`); cobertura total 90,6 % y módulos tocados `cli.py` 91,3 %, `config.py` 96,8 % y `search.py` 92,2 % (línea base 91,0–91,2 / 96,7 / 92,0); `git diff --check` limpio; sin goldens actualizados (el store por defecto no tiene URLs, contenido oculto ni cabeceras A6); bloques para `TEST-CATALOG.md`/`INTERFACES.md` y propuesta de registro en `.worktrees/reports/M08.md`. |

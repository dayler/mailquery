# SMOKE e instaladores

#### INS-SMOKE-01 — Instaladores

Requisitos: RF-29, PRD §13.2 · Archivo: `tests/test_install_scripts.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | Sintaxis, `--help`, `--print-config` y `--dry-run` de `install.sh` y `install.ps1` y de `skills/install.*` siguen pasando. |
| .02 | P | La plantilla de configuración documenta `[attachments]` y sigue siendo TOML válida con defaults. |
| .03 | P | Se menciona `pipx inject mailquery <paquete>` para plugins y `mailquery -v` conserva `backend <nativo>`. |

#### SMOKE-ATT-AM — Recuperación real de adjuntos en Apple Mail (macOS)

Requisitos: AC-07, AC-12, AC-20 · Archivo: `tests/test_smoke.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `show <uid>` de un mensaje con adjunto local ⇒ exit 0 y `attachments[]` con `index`/`name`. |
| .02 | P | `attachment <uid> --index 1` ⇒ exit 0, archivo `0600` bajo `~/.mailquery/attachments`, `sha256` coincide con el archivo, store sin cambios. |
| .03 | P | Segunda corrida ⇒ `cached:true` (sin umbral de tiempo). |
| .04 | B | Sin mensaje con adjunto local o sin Apple Mail ⇒ skip documentado (no fallo); la clase declara el skip por plataforma. |

#### SMOKE-ATT-OL — Recuperación real de adjuntos en Outlook clásico (Windows)

Requisitos: AC-07, AC-12, AC-20 · Archivo: `tests/test_smoke.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `show <uid>` de un mensaje con adjunto local ⇒ `attachments[]` con `index`/`name`. |
| .02 | P | `attachment <uid> --index 1` ⇒ exit 0, archivo bajo `~/.mailquery/attachments`, tamaño/hash coherentes, store y no leídos sin cambios. |
| .03 | P | `attachment` no cambia los contadores de las carpetas incluidas (`mailboxes --fields url,total,unread`) ni el store; la clase se salta por plataforma en `setUpClass` fuera de Windows. |

#### SMOKE-INSTALL — Instalación real con `pipx`

Requisitos: RF-29, PRD §13.2, AC-36 · Archivo: `tests/test_smoke.py`

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `pipx install.` con `PIPX_HOME`/`PIPX_BIN_DIR` temporales ⇒ exit 0. |
| .02 | P | `mailquery -v` ⇒ el backend de la plataforma. |
| .03 | P | Con `HOME`/`USERPROFILE` temporales (en macOS, `Library/Mail` y `Library/Accounts` del HOME temporal enlazan a los reales) y la primera cuenta de `mailquery mailboxes` declarada: `mailquery doctor --json` ⇒ todos los chequeos `ok=true`. |
| .04 | N | El `~/.mailquery` real del usuario no cambia. |
| .05 | P | Tras `pipx install .`, `pipx runpip mailquery show css-inline` con el mismo `PIPX_HOME` temporal ⇒ `Version: 0.23.<n>`. |

#### SMOKE-NEW — Comandos de lectura contra el cliente real

Requisitos: RNF-01, RNF-03, AC-46, AC-56, AC-59, AC-60, AC-25, AC-39 · Archivo: `tests/test_smoke.py`

Con la instalación y la config de SMOKE-INSTALL.

| Caso | Tipo | Verifica |
|---|---|---|
| .01 | P | `mailboxes` ⇒ exit 0 y JSON del contrato de salida (§12.5): seis claves de primer nivel, cada cuenta con sus `mailboxes[]`, cada carpeta con `path` e `included` y ninguna clave `mailboxes` de primer nivel. |
| .02 | P | `new --peek --fields all` valida la fila completa; `new` valida la fila por defecto de seis campos y el contrato de salida; `cursor` no cambia con `--fields`. |
| .03 | P | `search --since 1w` valida la fila por defecto; la misma consulta con `--fields all` valida la fila completa. |
| .04 | P | `search --text "*e*" --since 1d` valida la fila por defecto y `scan.mode: text`; con `--fields all`, la fila completa. |
| .05 | P | `show <messages[0].uid del search>` ⇒ exit 0 y el contrato de salida del mensaje. |
| .06 | N | `unread` de cada carpeta incluida (`mailboxes --fields url,total,unread`, sobre `accounts[].mailboxes[]`), antes y después ⇒ sin cambios. |
| .07 | B | `doctor`, `mailboxes` sin contadores, `search` con la fila mínima, `search --fields snippet`, `new`, `show` y `search --text` (si `scan.candidates ≤ 500`) dentro del presupuesto de §19 de su plataforma; `mailboxes --fields total,unread` se mide sin aserción; se informa del tamaño del store (mensajes y carpetas, solo recuentos). |
| .08 | P | `search`, `new`, `show` y, si hay un adjunto local recuperable, `attachment` llevan `content_notice` justo después de `generated_at`; las filas de `search`/`new` tienen los seis campos; `search --count` y `search --group-by from --limit 1` salen con exit 0; los contadores de no leídos no cambian. |
| .09 | P | `show` de un mensaje con una parte HTML en el `.emlx` devuelve `body_text` no vacío y `readable: true` sin error; repetir la lectura no cambia los contadores de no leídos. |
| .10 | P | `doctor --json --failures` con todo correcto ⇒ exit 0, `checks: []`, `not_evaluated: []` y `plugins: []`; el informe de texto dice `all checks passed`; no lleva `content_notice`. |

#### SMOKE-NEW.11 — uid corto contra el cliente real

Requisitos: AC-63, AC-68, AC-69 · Archivo: `tests/test_smoke.py`

**Tabla: Casos de SMOKE-NEW.11**

| Caso | Tipo | Verifica |
|---|---|---|
| .11 | P | En Windows con Outlook abierto: los uids de `search --since 1w` son `outlook:` más 10 caracteres del alfabeto (o con sufijo); `show` del primero responde con exit 0; existe `db/cache.db` en el HOME temporal; `show --show-native-id` da `outlook:` más hexadecimal en mayúsculas; los no leídos no cambian. En macOS: tras `search` y `show`, no existe `db/cache.db`. Donde no aplica, se salta con el motivo de la sección 6 de `infrastructure.md`. |

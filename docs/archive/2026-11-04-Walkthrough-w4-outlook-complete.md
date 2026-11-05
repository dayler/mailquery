# Walkthrough — Fase W4: Outlook, completo

| Campo | Valor |
|-------|-------|
| Fecha | 2026-11-04 |
| Rama | `feature/w4-outlook-complete` (git flow), creada desde `develop` @ `622bfd0` (W0+W2+W3 fusionadas); se fusiona en `develop` con `--no-ff` al cerrar |
| Commits | Uno solo para la fase |
| Plan | `docs/plans/2026-11-03-v2.0.0-windows-outlook.md` rev. 18 |
| Contrato | PRD y anexos del commit `f1ad969` (cabecera del plan). `develop` tiene el PRD v1.2 (`f844cc5`), que según su tabla de versiones no cambia el producto pero retira o renumera §9.3–§9.5, §13.4, §20 y §23, que el plan cita: los subagentes usaron la versión `f1ad969`. |
| Orquestación | Sesión Opus 5.5; un subagente Opus 5.5 por tarea |
| Host | Windows 11 x64, Python 3.14.7, `pywin32`, Outlook clásico 16.0.0.20430 abierto |

---

## 1. Tareas hechas

| Tarea | Qué se hizo | Casos de test |
|-------|-------------|---------------|
| W4-T01 | `new` en Outlook: validador `OutlookBackend.check_state_uid` (uids hex en mayúsculas; enteros, minúsculas o vacíos ⇒ `E_STATE_CORRUPT`); el núcleo de `new` ya era neutral. `FakeOutlook.move_item` para el mensaje movido. | UT-ST-03.01…04, OL-25.01…04, OL-18.01…03, OL-04.02 |
| W4-T02 | `search --text` en Outlook; `--to`/`--cc` acotados por RF-17 en Windows (no acotan, una sola validación y un solo error, mensaje con el flag que obliga a leer contenido, hint solo con los filtros que acotan); regla por atributo del backend (`recipients_open_items`), no por `sys.platform`; `scan.messages_read` = items abiertos; `search`/`new` sin cabeceras de transporte ni adjuntos (`load_snippet`); cada item se abre una vez por comando. | OL-24.01…07 |
| W4-T03 | `doctor` en Outlook: `pywin32`, `outlook`, `stores`, `readonly_strategy`, `object_model_guard` en el orden de §12.8 y dependencias de §B.8; `config` con `W_STORE_EXCLUDED` en el detalle; modo de timeout de `doctor` (D-03): orden de evaluación, informe completo con el texto literal y exit 0. | OL-04.03, OL-04.04, OL-26.01…04, OL-27.01…06 |
| W4-T04 | Exit 6 de punta a punta; goldens `outlook/new_first_run` y `outlook/doctor`; recetas en ambos backends; misma forma del JSON en ambos backends; barrido completo del gate de solo lectura de Outlook; `docs/INTERFACES.md` actualizado. | TC-02.06/.07, TC-04.01/.02, TC-05.01…06, OL-30.01…04 (barrido completo) |

Cobertura: los 45 casos de W4 tienen su método con el ID en el nombre.

**Criterio de cierre (plan §5 W4):** CU-01 (`new`), CU-02 (`search --text "*factura*" --since 1mo`) y CU-07 (`doctor`) funcionan en Windows con el Outlook falso.

---

## 2. Salida de la suite

Comando: `python -B -m unittest discover -s tests -t . -v` (PowerShell, host Windows).

| Momento | Corridos | Fallidos | Errores | Saltados |
|---------|----------|----------|---------|----------|
| Inicio de W4 (`develop` @ `622bfd0`) | 666 | 0 | 0 | 10 |
| Tras W4-T01 | 679 | 0 | 0 | 10 |
| Tras W4-T02 | 686 | 0 | 0 | 10 |
| Tras W4-T03 | 700 | 0 | 0 | 10 |
| **Final W4** | **711** | **0** | **0** | **10** |

Los 10 saltados son `InstallShTest` sin `sh` en el `PATH` de PowerShell (§7.7). `python -m compileall -q src` sin errores. Goldens de Apple Mail y `test_readonly.py` sin cambios respecto a `develop`.

---

## 3. Goldens

| Golden | Cambio |
|--------|--------|
| `outlook/search.json` (W3) | `scan.messages_read` 2 ⇒ 3: ahora cuenta items abiertos (OL-24.05); `search` abre los 3 items de la página para leer To/Cc, también el de solo cabeceras y el S/MIME (cuyo cuerpo nunca se lee) |
| `outlook/new_first_run.json` (nuevo) | Primera corrida sobre `FakeOutlook.default()`: emite el mensaje más reciente (los otros dos quedan fuera de la ventana de 10min); `cursor.previous: null`, `current` con el uid hex y `lookback_seconds: 600`; `W_STORE_EXCLUDED` y `W_FIRST_RUN` al final |
| `outlook/doctor.json` (nuevo) | Los 10 chequeos de §12.8 en orden, todos `ok=true`, con `stores`, `readonly_strategy` (caché en `<ROOT>/.mailquery/tmp/gen_py`), `object_model_guard` (antivirus del fake) y `config` con `W_STORE_EXCLUDED` |

---

## 4. Verificación contra el host (solo lectura)

- Registro: no existen las claves de directiva de seguridad de Outlook (`HKCU`/`HKLM` `Software\Policies\Microsoft\Office\16.0\Outlook\Security`); SecurityCenter2 devuelve 2 productos, uno activo.
- Desviación: el subagente de W4-T03 ejecutó una vez `doctor --json` contra el Outlook real, con un HOME temporal (borrado después): exit 0 y los 10 chequeos en `ok`. Es más que las sondas de propiedades que permite D-02; fue de solo lectura y no tocó el `~/.mailquery` real.

---

## 5. Decisiones tomadas

| # | Tarea | Decisión |
|---|-------|----------|
| 1 | Proceso | Rama desde `develop` y fusión en `develop` al cerrar (regla de git flow del dueño, aplicada desde W4). |
| 2 | W4-T01 | `cli.main` no tiene parámetro de reloj (firma fijada en plan §4.2): el reloj inyectado se prueba con `run_new(clock=...)` sobre `OutlookBackend`. Texto de `E_STATE_CORRUPT` en Outlook: "'cursor.last_uid' must be a uid (an uppercase hexadecimal EntryID)". |
| 3 | W4-T02 | `scan.messages_read` en Outlook = items distintos abiertos en el comando (uno de solo cabeceras cuenta porque se abre para leer `DownloadState`; uno que no se abre, nunca). Apple Mail conserva su semántica. |
| 4 | W4-T02 | Caché de items por comando (los primeros 200 más el último) y de destinatarios; `show` abre el item una sola vez. |
| 5 | W4-T03 | `object_model_guard`: se leen las directivas de `HKCU` solo con `AdminSecurityMode` = 3; `PromptOOMAddressInformationAccess` 0 o 1 falla, `PromptOOMAddressBookAccess` 0 falla, `PromptOOMAddressInformationAccess` 2 pasa; si ninguna decide, antivirus activo (`productState & 0x1000`) pasa, ninguno falla, consulta imposible ⇒ `not evaluated: SecurityCenter2 unavailable`. Valores según la KB de Microsoft (0 denegar, 1 preguntar, 2 aprobar), no según el mapeo del brief del orquestador, que era incorrecto. |
| 6 | W4-T03 | El detalle de timeout es siempre el literal de §12.8 ("timeout after 30 s…"), también con el plazo de 0,2 s de los tests. `stores` es `ok=true` si el perfil se puede leer, aunque no haya candidatos. |
| 7 | W4-T04 | TC-04/TC-05 usan `FakeOutlook.item_matrix()` con `INBOX/Facturas` declarada; "comando" de receta = línea que empieza por `mailquery` dentro de un bloque de código (incluidos los indentados). |
| 8 | W4-T04 | Los goldens y TC-04/05 construyen el backend con `tmp_root=<home>/tmp`, como `cli`. |

---

## 6. Puntos abiertos

1. **Recetas contradicen el PRD** (todos sus comandos pasan, pero el texto no): la 01 describe la primera corrida como baseline, solo Apple Mail, sin exit 6 ni `E_CLIENT_*`, uid entero y sin `body.readable`, y `show <uid>` solo inline; la 02 dice que `--to`/`--cc` acotan `--text` (en Windows no), dedupe y warnings solo de Apple Mail, `scan.mode: "content"` (debe ser `text`), sin exit 6. Las corrige W5-T04.
2. **Textos genéricos de `state.py`** mencionan enteros también en Outlook para un `cursor` sin fecha válida o un anillo que no es lista ("'emitted_uids' must be a list of integers"); el código de error es correcto.
3. **Presupuestos de §19** (p. ej. `search --text` ≤ 500 candidatos < 10 s) sin medir en el Outlook real: se comprueban en las SMOKE de W5-T03.
4. **CI fuera de Windows** sin verificar (instrucciones para macOS en `docs/Walkthrough-w0-parity.md` §6).
5. Revisión del planificador y OK del dueño asumidos.

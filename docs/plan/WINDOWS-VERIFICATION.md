# Verificación en Windows con Outlook clásico (runbook)

**Estado:** pendiente de ejecución en un equipo Windows real.
**Motivo:** la fase P4 se cerró con el SMOKE de Windows/Outlook saltado con motivo (RK-10) porque el host del plan era macOS. Este documento describe exactamente qué falta verificar, cómo hacerlo y qué evidencia devolver.
**Al terminar:** ver §9 (qué se actualiza) y §11 (contingencias). No se toca `docs/plan/` para borrarlo: eso solo ocurre tras la revisión humana y la conciliación del PRD (ver `CLAUDE.md`).

---

## 1. Qué se verifica en Windows y qué no

En el host Windows se cierra la verificación que depende del cliente real. Todo es **solo lectura** sobre Outlook.

| # | Qué se comprueba | Caso / comando | Qué demuestra |
|---|---|---|---|
| 1 | Instalación real con `pipx` (wheel de `css-inline` y `pywin32`), `doctor` y home real intacto | SMOKE-INSTALL.01–.05 | El paquete se instala sin compilar `css-inline`, `doctor` ve el entorno y el `~/.mailquery` real no cambia |
| 2 | Lectura real de Outlook: `mailboxes`, `new`, `search`, `search --text`, `show` | SMOKE-NEW.01–.06 | JSON correcto contra COM y contadores de no leídos del cliente sin cambios |
| 3 | Presupuestos p95 de Windows (PRD §19) | SMOKE-NEW.07 | `doctor` < 3 s; `mailboxes` < 1 s; `search` < 1 s; `new` < 1 s; `show` < 0,5 s; `search --text` acotado < 10 s (la fila `--fields snippet` comparte el presupuesto de `search`; `mailboxes --fields total,unread` es informativo) |
| 4 | Salida de 3.0.0 contra el cliente real | SMOKE-NEW.08 | `content_notice`, fila de seis campos, `search --count`, `search --group-by from --limit 1`, `content_notice` de `attachment` y contadores sin cambios |
| 5 | Cuerpo desde HTML con `BodyFormat`/`HTMLBody` (lista blanca COM) | **manual** §6.1 (SMOKE-NEW.09 se salta en Windows: su selector busca `.emlx`) | `show` devuelve `body_text` legible sin error, sin abrir ventanas y sin cambiar contadores |
| 6 | Sección de plugins y `--failures` en el host real | SMOKE-NEW.10 | `doctor --json --failures` ⇒ `checks: []`, `not_evaluated: []`, `plugins: []`, exit 0 y `all checks passed` |
| 7 | Extracción COM real de un adjunto local | SMOKE-ATT-OL.01–.03 | `attachment --index 1` escribe el archivo, su `sha256` y `size_bytes` cuadran, la segunda corrida es `cached: true` y los contadores no cambian |
| 8 | Solo lectura en Windows a través de todos los comandos | SMOKE (contadores), OL-30 (suite) | Ninguna mutación ni descarga; las lecturas fuera de la lista blanca no llegan a Outlook |
| 9 | Caché de `pywin32` solo bajo `<home>/tmp/gen_py` | OL-05.02 (suite, solo `win32`) | El arranque COM no deja archivos fuera del home temporal |
| 10 | Presupuesto de `attachment` | **manual** §7 | Extracción de 1 adjunto ≤ 5 MB < 600 ms; acierto de caché < 50 ms; `--all` lineal |
| 11 | Instalador `scripts/install.ps1` (lógica con shims) | UT-INS-01 (suite, solo `win32`) | El instalador de Windows valida versión, `win32com` y `doctor` |

**Fuera de este runbook:** plugins reales (no hay equipos con plugins), conciliación `PRD-v2.2.md` → `PRD.md`, tags/release y la matriz de wheels de CI (Windows 64/32 bits ya está cubierta por CI). macOS ya quedó verificado en el Mac del dueño (SMOKE 19/19).

---

## 2. Prerrequisitos del equipo

- **Windows 10/11 x64.** Un solo host basta; el CI ya cubre las cuatro versiones de Python y los wheels `win_amd64`/`win32`.
- **Outlook clásico 16.0** (no el «nuevo Outlook», `olk`), **abierto**, con sesión iniciada y al menos una cuenta con correo reciente. La consola desde la que se ejecute debe estar **en la misma sesión e integridad** que Outlook (si Outlook no está elevado, la consola tampoco).
- **Cuenta con datos útiles** dentro del alcance que declare el test:
  - al menos un mensaje de la **última semana** (SMOKE-NEW.07/08 fallan si `search --since 1w` está vacío);
  - al menos un mensaje reciente **con adjunto local** entre los 5 primeros de `search --has-attachments --limit 5`; el primer adjunto (`--index 1`) debe ser un archivo local, no un adjunto solo en la nube (si es remoto, SMOKE-ATT-OL falla con `E_ATTACHMENT_UNAVAILABLE`, que es el comportamiento esperado pero no sirve para medir);
  - un mensaje con **cuerpo HTML** (p. ej. un boletín) para la revisión manual §6.1.
- **Python 3.11–3.14 de 64 bits** (se sugiere 3.12), **git** y **pipx**:
  ```powershell
  python --version
  python -m pip install --user pipx
  python -m pipx ensurepath   # abrir una consola nueva después
  pipx --version              # la consola de los SMOKE necesita pipx en PATH
  ```
  El Python que usa `pipx` debe ser ≥ 3.11 (los SMOKE instalan el paquete con ese intérprete).
- **Red/PyPI** disponible (los SMOKE hacen `pipx install .` y descargan `css-inline`/`pywin32` desde wheel).
- Cerrar otras tareas pesadas durante las mediciones; una sola corrida a la vez.

---

## 3. Preparación (PowerShell, desde la raíz del repositorio)

```powershell
git switch develop
git pull --ff-only
git rev-parse --short HEAD        # anotar el commit en la evidencia
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install "css-inline~=0.23.1" "coverage~=7.17" pywin32
.venv\Scripts\python -m pip install -e .        # para importar mailquery en los tests
.venv\Scripts\python -c "import mailquery, css_inline, win32com; print(mailquery.__version__)"
```

Debe imprimir `3.0.0a1`. Los SMOKE hacen su **propia** instalación con `pipx` en directorios temporales, así que no tocan ni esta `.venv` ni la instalación real.

No hace falta `config.toml`: los casos SMOKE crean uno temporal con la primera cuenta que expone una carpeta incluida. Tampoco hace falta cerrar Outlook: debe estar abierto.

---

## 4. Ejecución A — SMOKE automático contra el Outlook real (~5–10 min)

```powershell
.venv\Scripts\python -B -m unittest tests.test_smoke -v
```

Qué esperar:

- `SmokeTest` (SMOKE-INSTALL.01–.05 + SMOKE-NEW.01–.10) y `SmokeAttOutlook` (SMOKE-ATT-OL.01–.03).
- **Cero fallos.** Las omisiones deben tener motivo documentado: `SmokeAttAppleMail` se salta entero (es macOS), y **SMOKE-NEW.09 se salta en Windows** porque su selector de mensaje exige `source.emlx_path`; eso es esperado y se cubre a mano en §6.1.
- La salida incluye tres bloques que hay que copiar a la evidencia:
  - `SMOKE budgets …` (una fila por comando, con p95 de operación y presupuesto);
  - `SMOKE store size: <n> messages, <n> folders`;
  - `SMOKE mailboxes --fields total,unread (informational, no budget): …`.

Si algo falla, **no se repite la suite completa**: se repite solo el caso:

```powershell
.venv\Scripts\python -B -m unittest tests.test_smoke.SmokeTest.test_smoke_new_07_within_p95_budget -v
.venv\Scripts\python -B -m unittest tests.test_smoke.SmokeTest.test_smoke_new_08_content_notice_and_output_options -v
.venv\Scripts\python -B -m unittest tests.test_smoke.SmokeAttOutlook.test_smoke_att_ol_01_recovers_a_local_attachment -v
```

Reglas: no se relajan aserciones ni presupuestos, y no se cambia el test para que pase. Un fallo funcional es un defecto (§11).

---

## 5. Ejecución B — suite completa en el host Windows (~4–8 min)

```powershell
.venv\Scripts\python -B -m unittest discover -s tests -t . -v
```

- **Cero fallos.** Las omisiones deben ser solo por plataforma/entorno (macOS-only, Linux-only); con Outlook abierto, los SMOKE se ejecutan de verdad en lugar de saltarse.
- Guardar la línea final `Ran <n> tests` / `OK (skipped=<n>)` y la lista de omitidos con su motivo.
- Opcional (el CI ya lo bloquea en `develop`): cobertura ≥ 85 %:
  ```powershell
  .venv\Scripts\python -m coverage run -m unittest discover -s tests -t .
  .venv\Scripts\python -m coverage report
  ```

---

## 6. Ejecución C — revisión manual de lo que los SMOKE no cubren en Windows

Usar un `HOME`/`USERPROFILE` temporal para no mezclar el home real con estas pruebas:

```powershell
$MqHome = Join-Path $env:TEMP ("mq-win-" + [guid]::NewGuid().ToString("N").Substring(0,8))
New-Item -ItemType Directory -Force $MqHome | Out-Null
$env:HOME = $MqHome
$env:USERPROFILE = $MqHome
$MQ = ".venv\Scripts\mailquery.exe"
$MQ -v        # debe decir: mailquery 3.0.0a1 (backend outlook; …)
```

### 6.1 Cuerpo HTML por COM (`BodyFormat`/`HTMLBody`)

El SMOKE-NEW.09 automático no puede elegir mensaje en Windows. Hazlo a mano con un mensaje que sepas que es HTML (boletín, correo con formato):

```powershell
$r = & $MQ search --since 1y --limit 20 | ConvertFrom-Json
$r.messages | Select-Object -First 20 uid, subject, from
$uid = "<uid copiado>"
& $MQ show $uid | ConvertFrom-Json | Select-Object -ExpandProperty message |
  Select-Object uid, readable, body_truncated, partial, @{n="source";e={$_.source}}
```

Criterio: `readable: true`, `body_text` no vacío y con el texto visible del HTML (sin etiquetas), `source.emlx_path` es `null` en Windows (contrato del backend) y no se abre ninguna ventana ni cuadro de diálogo de Outlook. Repetir `show` y comprobar que `body_text` es idéntico.

### 6.2 Cabeceras de transporte A6 y señales del remitente

```powershell
& $MQ show $uid | ConvertFrom-Json | Select-Object -ExpandProperty message |
  Select-Object headers, warnings
```

Criterio: `headers` contiene las cabeceras de transporte; un mensaje de un remitente externo que no pase SPF/DKIM/DMARC produce `W_SENDER_AUTH_FAILED` en `warnings`, y uno interno de Outlook no lo produce. El coste de leer estas cabeceras en `search`/`new` ya queda medido por SMOKE-NEW.07 (RK-08).

### 6.3 Solo lectura en Outlook

```powershell
& $MQ mailboxes --fields url,total,unread | ConvertFrom-Json | Out-Null
# … ejecutar la batería de comandos de abajo …
& $MQ mailboxes --fields url,total,unread | ConvertFrom-Json | Out-Null
```

Criterio: los `total`/`unread` de cada carpeta incluida son idénticos antes y después; no aparece ningún diálogo ni descarga de Outlook; `attachment` solo escribe en el home de `mailquery`, nunca en el store.

### 6.4 `doctor` completo

```powershell
& $MQ doctor
& $MQ doctor --json | ConvertFrom-Json | ConvertTo-Json -Depth 6
& $MQ doctor --json --failures | ConvertFrom-Json | ConvertTo-Json -Depth 6
```

Criterio: todos los chequeos `[ok]` (`python`, `home`, `driver`, `pywin32`, `outlook`, `stores`, `readonly_strategy`, `object_model_guard`, `config`, `state`, `lock`); el detalle de `driver` dice `pkg 3.0.0a1`, `attachments=local` y `native_order=text`; `--failures` da `checks: []`, `not_evaluated: []`, `plugins: []` y exit 0. `doctor` no debe tardar más de 3 s (pared).

### 6.5 Salida de `mailboxes`

```powershell
& $MQ mailboxes | ConvertFrom-Json | ConvertTo-Json -Depth 6
& $MQ mailboxes --fields name,url,total,unread | ConvertFrom-Json | ConvertTo-Json -Depth 6
```

Criterio: cuentas con `mailboxes[]` agrupadas; por defecto solo `path` e `included`; con `--fields` los campos en el orden `name, path, url, total, unread, included`; sin `total`/`unread` no se cuenta nada (comprobar que la primera variante es notablemente más rápida).

### 6.6 Contrato de `search`/`new`/`show`

```powershell
& $MQ search --since 1w --limit 5 | ConvertFrom-Json
& $MQ new | ConvertFrom-Json
& $MQ search --count | ConvertFrom-Json
& $MQ search --group-by from --limit 1 | ConvertFrom-Json
```

Criterio: fila de seis campos (`uid`, `subject`, `from`, `date_received`, `is_read`, `has_attachments`) en ese orden; `content_notice` justo después de `generated_at`; `--count` y `--group-by` con exit 0; `scan.messages_read` coherente (sin `--text` no se leen cuerpos).

### 6.7 Extracción manual de un adjunto

```powershell
$m = (& $MQ search --has-attachments --limit 5 | ConvertFrom-Json).messages[0]
& $MQ show $m.uid | ConvertFrom-Json | Select-Object -ExpandProperty message |
  Select-Object uid, attachments
& $MQ attachment $m.uid --index 1 | ConvertFrom-Json | ConvertTo-Json -Depth 4
```

Criterio: el primer comando lista `attachments` con `index`/`name`/`size_bytes`; el segundo guarda el archivo (`saved: true`, `path`, `size_bytes`, `sha256`), el tamaño coincide con el archivo y `sha256` coincide con `Get-FileHash <path> -Algorithm SHA256`; la segunda ejecución devuelve `cached: true` con el mismo `sha256`; `--force` vuelve a extraer.

---

## 7. Ejecución D — presupuesto de `attachment` (manual)

Con el mismo `HOME` temporal de §6 y un adjunto local **≤ 5 MB**:

```powershell
$m = (& $MQ search --has-attachments --limit 5 | ConvertFrom-Json).messages[0]
$uid = $m.uid
# 1 calentamiento (no se mide) y 20 extracciones reales con --force
& $MQ attachment $uid --index 1 --force | Out-Null
1..20 | ForEach-Object { & $MQ attachment $uid --index 1 --force | Out-Null }
# 20 aciertos de caché
1..20 | ForEach-Object { & $MQ attachment $uid --index 1 | Out-Null }
```

Calcular el p95 de las operaciones (el CLI registra `duration_ms` en `event=end command=attachment`):

```powershell
.venv\Scripts\python -c "import math,re,pathlib; p=pathlib.Path.home()/'.mailquery'/'logs'/'mailquery.log'; lines=p.read_text(encoding='utf-8',errors='replace').splitlines(); pick=lambda c:[int(m.group(1)) for l in lines if 'event=end command=attachment ' in l and c in l for m in [re.search(r'duration_ms=(\d+)',l)] if m][-20:]; ex=sorted(pick('cached=0')); hit=sorted(pick('cached=1')); print('extraccion n=%d p95=%.3fs'%(len(ex),ex[math.ceil(0.95*len(ex))-1]/1000)); print('cache n=%d p95=%.3fs'%(len(hit),hit[math.ceil(0.95*len(hit))-1]/1000))"
```

Criterio: extracción p95 < **600 ms** (1 adjunto ≤ 5 MB, Outlook) y caché p95 < **50 ms** (PRD §19). `attachment --all` de N adjuntos ≈ presupuesto × N (opcional). Anotar también el tamaño del adjunto medido.

---

## 8. Evidencia a devolver

Rellenar este esqueleto y guardarlo como `docs/plan/evidence/M14-windows.md` (o añadirlo a `docs/plan/evidence/M14.md` en una sección «Windows»). **Regla de redacción (el repositorio es público):** de SMOKE solo se copian nombre del caso, estado, duración y p95; direcciones, etiquetas de cuenta, nombres de carpeta, asuntos, uids reales y rutas de `HOME` se sustituyen por `<redacted>`/`<HOME>`. No pegar JSON con datos reales ni capturas con datos del cliente.

```markdown
### Host y build
- Fecha: <fecha>
- Windows: <edición y build> · Outlook clásico: <versión> · Python: <x.y.z> (venv)
- Commit: <hash> · `mailquery -v`: `mailquery 3.0.0a1 (backend outlook; …)`
- Store (solo recuentos): <N> mensajes, <M> carpetas

### SMOKE (`tests.test_smoke`)
- `Ran <n> tests` / `OK (skipped=<n>)`; omitidos y motivo: <…>
- SMOKE-INSTALL.01–.05: <ok/fallo>
- SMOKE-NEW.01–.06, .08, .10: <ok/fallo>
- SMOKE-NEW.07 (tabla copiada): <pegar las filas de `SMOKE budgets`>
- SMOKE-NEW.09: saltado en Windows (selector .emlx) → cubierto a mano en §6.1: <ok/fallo>
- SMOKE-ATT-OL.01–.03: <ok/fallo>

### Presupuestos p95 Windows (PRD §19)
| Comando | Presupuesto | p95 medido | Estado |
|---|---|---|---|
| doctor | < 3 s | … | … |
| mailboxes | < 1 s | … | … |
| search | < 1 s | … | … |
| search --fields snippet | < 1 s | … | … |
| new | < 1 s | … | … |
| show | < 0,5 s | … | … |
| search --text | < 10 s | … | … |
| mailboxes --fields total,unread | informativo | … | — |
| attachment extracción ≤ 5 MB | < 600 ms | … | … |
| attachment caché | < 50 ms | … | … |

### Revisión manual (§6)
- 6.1 cuerpo HTML: <ok/fallo + observaciones>
- 6.2 A6: <ok/fallo + observaciones>
- 6.3 solo lectura: <ok/fallo>
- 6.4 doctor: <ok/fallo>
- 6.5 mailboxes: <ok/fallo>
- 6.6 contrato search/new/show: <ok/fallo>
- 6.7 extracción manual: <ok/fallo>

### Suite completa
- `Ran <n> tests` / `OK (skipped=<n>)`; omitidos: <…>; cobertura (si se midió): <…>

### Incidencias y observaciones
- <ninguna / detalle redactado>
```

---

## 9. Qué se actualiza cuando el resultado sea verde

1. `docs/PERFORMANCE-BACKLOG.md`: sección de medición de Windows (fecha, host, commit, `3.0.0a1`, recuentos del store, tabla de p95 con presupuestos de Windows y la fila de `attachment`); se cierran o actualizan las filas «pendiente de equipo» y se mantiene `mailboxes --fields total,unread` como deuda informativa.
2. `docs/plan/evidence/M14.md`: sección «Windows (Outlook clásico)» con los datos de §8; la fase F2 de `M14-smoke-closure.md` pasa de «saltada con motivo» a «ejecutada en Windows».
3. `docs/plan/00-master-plan.md`: fila nueva en el registro de ejecución (fecha, resultado, evidencia).
4. Commit y push de esos documentos. **Solo después**: revisión y aprobación humana del plan completo y conciliación de `PRD-v2.2.md` en `PRD.md` (CL-01…CL-09). Entonces sí se borra `docs/plan/`.

Si un **presupuesto** no se cumple: se registra como deuda abierta en `PERFORMANCE-BACKLOG.md` y se devuelve al dueño (HITL); no se relaja la aserción. Si hay un **fallo funcional**: el milestone afectado vuelve a 🟡 (regla 9 del plan), se corrige y se re-verifica; el plan no se borra.

---

## 10. Contingencias frecuentes

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| `SmokeTest` se salta entero: «classic Outlook (OUTLOOK.EXE) is not running» | Outlook cerrado | Abrirlo, iniciar sesión y repetir |
| Se salta: «pipx is not available» | `pipx` fuera del PATH de esa consola | `python -m pipx ensurepath`, abrir consola nueva |
| `SMOKE-INSTALL.01` falla | El Python de `pipx` es < 3.11, o sin red | Reinstalar `pipx` con un Python ≥ 3.11 (`pipx install --python <python> …` no aplica: es el intérprete de `pipx`) |
| `SMOKE-NEW.07` falla con «no message in the last week to show» | Cuenta sin correo reciente en la primera cuenta utilizable | Repetir con una cuenta con correo de la última semana; el test declara la primera que exponga una carpeta incluida |
| `SMOKE-NEW.09` aparece como omitido | Esperado en Windows (selector `.emlx`) | Verificar a mano §6.1 |
| `SMOKE-ATT-OL` falla con «no message with attachments» o `E_ATTACHMENT_UNAVAILABLE` | No hay mensaje reciente con adjunto local en el alcance | Asegurar un mensaje con adjunto local entre los 5 primeros; no es un defecto del producto |
| `doctor` no ve Outlook | Consola elevada y Outlook no, o Outlook «nuevo» | Misma sesión/integridad; usar Outlook clásico |
| Una medición p95 supera el presupuesto | Carga de la máquina, antivirus, primera corrida | Cerrar procesos, repetir solo ese comando 20 veces; si persiste, es deuda/HITL (§9) |

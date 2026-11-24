---
aliases: ["Sección 10", "Estructura de carpetas"]
tags: [prd]
---

## 10. Estructura de carpetas

### 10.1 Repositorio

```text
mailquery/
├── README.md, README.es.md         # inglés y español, mismo contenido: instalación, permisos, ejemplos, --help
├── CLAUDE.md                       # reglas del repositorio
├── LICENSE
├── pyproject.toml                  # comando `mailquery`, dependencias (ADR-14, ADR-33) y entry points `mailquery.backends`
├── .github/workflows/tests.yml     # CI Linux/macOS/Windows
├── docs/
│   ├── prd/                        # este documento, un archivo por sección (portada: 00-indice.md)
│   ├── INTERFACES.md               # contratos de implementación entre módulos y API de plugins
│   ├── KNOWN-DEFECTS.md            # defectos conocidos
│   ├── PERFORMANCE-BACKLOG.md      # pendientes de rendimiento
│   ├── ROADMAP.md                  # ideas no vinculantes
│   ├── config.example.toml
│   ├── archive/                    # registros históricos
│   ├── security/threat-model.md    # anexo de seguridad
│   ├── tests/                      # catálogo de pruebas por área
│   └── recipes/                    # recetas/preceptos para el harness
├── scripts/                        # install.sh, install.ps1, install.bat
├── skills/                         # skill del harness (mailquery/SKILL.md) e instaladores
├── src/mailquery/
│   ├── __init__.py, __main__.py
│   ├── cli.py, config.py, search.py, state.py, uid.py
│   ├── native_ids.py               # librería de ids cortos y caché de ids nativos
│   ├── output.py, logging_setup.py, errors.py
│   ├── store.py, emlx.py, accounts.py      # acceso Apple Mail
│   ├── plugins/
│   │   ├── __init__.py             # superficie pública que importa un plugin
│   │   └── api.py                  # API pública de plugin (plugin_api = 1)
│   ├── attachments/                # motor de adjuntos (§9.2)
│   │   ├── __init__.py
│   │   ├── catalog.py, blocking.py, screening.py, sanitize.py
│   │   └── paths.py, cache.py, engine.py, active_content.py
│   └── backends/
│       ├── __init__.py             # backend nativo por plataforma
│       ├── registry.py             # registro mailquery.backends
│       ├── base.py                 # interfaz de backend + modelo común
│       ├── apple_mail.py           # adaptador Apple Mail (driver apple_mail)
│       ├── outlook.py              # backend Outlook (driver outlook)
│       └── outlook_com.py          # único import de win32com; proxy de solo lectura
└── tests/                          # pruebas
```

### 10.2 Home de la aplicación (runtime, **no** en el repo)

```text
~/.mailquery/                        # macOS: 0700 | Windows: %USERPROFILE%\.mailquery
├── config.toml                      # opcional; esquema cerrado de §15
├── state.json                       # schema 2: cursor + anillo de uids "<driver>:<native_id>"
├── db/                              # carpeta de la caché de ids nativos (0700); la crea el driver que la usa
│   └── cache.db                     # caché de ids nativos (0600, §11.4)
├── <driver>.toml                    # OPCIONAL: configuración de un plugin externo (propiedad del plugin; el núcleo no la lee)
├── attachments/                     # caché efímera de adjuntos (0700) — la limpia un cron externo
│   └── <driver>/                    # "apple_mail" | "outlook" | clave del plugin
│       └── <native_id>/             # ID nativo (0700); si la ruta excede el límite del SO, identificador estable derivado de uid
│           ├── .manifest.json       # manifiesto SHA-256 del mensaje (0600, §10.3.4)
│           └── <sanitized_name>   # archivo (0600); incluye el prefijo <index:02d>_
├── locks/mailquery.lock
├── tmp/                             # temporales; mismo sistema de archivos que attachments/
│   ├── staging/                     # staging del núcleo (0700; se limpia)
│   ├── <copia Envelope Index>/      # macOS: copia temporal para copy_ro (§9.3)
│   ├── gen_py/                      # Windows: caché de pywin32 (win32com.__gen_path__)
│   └── plugin-<driver>/             # OPCIONAL: temporal de un plugin (propiedad del plugin)
└── logs/
    ├── mailquery.log                # log del núcleo (rotación §14)
    ├── mailquery.jsonl              # log del núcleo en JSON con [logging].json = true (rotación §14)
    └── <driver>.log                 # OPCIONAL: log de un plugin externo (propiedad del plugin; el núcleo no lo lee)
```

Reglas: I-1 y ADR-02. Permisos: RNF-05 y RNF-13.

### 10.3 Bloqueo, sanitización y ruta de caché

#### 10.3.1 Bloqueo del mensaje completo (`E_ATTACHMENT_BLOCKED`, exit 4)

Antes de escribir cualquier byte se evalúan los nombres de **todos** los adjuntos del mensaje y los primeros bytes decodificados de cada adjunto que la invocación vaya a extraer (`--index N`: ese; `--all`: todos). Si cualquiera dispara una regla, **se bloquea el mensaje entero**: no se escribe ningún archivo, no se sirve caché y se limpia staging. El acierto de caché no re-inspecciona el contenido: solo se sirve si su SHA-256 coincide con el registrado en el manifiesto, calculado sobre bytes que ya pasaron esta pantalla (§10.3.4); las reglas de contenido se aplican a las extracciones nuevas, y, en `attachment`, el mensaje bloqueado no devuelve rutas ni archivos; `show` solo pone `cached_path: null` en los adjuntos con nombre bloqueado (RF-41). Un adjunto no solicitado no se inspecciona en contenido y no se extrae; se validará si se pide en el futuro.

1. **Nombre (sobre la forma normalizada NFKC una sola vez, más la forma cruda para controles):**
   - NUL o caracteres de categoría Unicode `Cc`, `Cf`, `Cs`, `Co` (incluye RLO `\u202e`) en el nombre crudo.
   - Separadores `/` o `\`, segmentos `..`, prefijo de unidad (`C:`) o cualquier `:` (evita NTFS ADS), en la forma normalizada.
   - Extensiones peligrosas simples o encadenadas: tras normalizar y recortar puntos/espacios finales, si la extensión final o cualquiera de las extensiones encadenadas (separadas por `.`, case-insensitive, p. ej. `factura.pdf.exe`) pertenece al catálogo de §10.3.2.
   - Nombre reservado del sistema: tras recortar puntos y espacios finales, la raíz (antes del primer punto, sin espacios en sus extremos, sin distinguir mayúsculas) es `CON`, `PRN`, `AUX`, `NUL`, `COM1`..`COM9` o `LPT1`..`LPT9`.
2. **Contenido (*magic bytes*) en el primer bloque decodificado:**
   - `4D 5A` (`MZ`), `7F 45 4C 46` (`\x7fELF`), `FE ED FA CE`/`FE ED FA CF`/`CE FA ED FE`/`CF FA ED FE`/`CA FE BA BE` (Mach-O/Universal) o `23 21` (`#!`).
   - El bloque se lee **antes** de crear el archivo en la caché (en Outlook, en el staging temporal de §23.1), con un máximo de 512 bytes.
3. Si el flujo de un adjunto a extraer no se puede leer por un error de E/S, ⇒ `E_ATTACHMENT_UNREADABLE` y no se extrae ningún archivo del mensaje; si vence `[attachments].timeout_seconds`, ⇒ `E_CLIENT_TIMEOUT` (RF-49). Un flujo vacío (0 bytes) es válido: no tiene firma y pasa el control de contenido.

#### 10.3.2 Catálogo de extensiones peligrosas

**Tabla: Extensiones peligrosas por categoría**

| Categoría | Extensiones bloqueadas |
|-----------|------------------------|
| Ejecutables y binarios | `.exe`, `.com`, `.scr`, `.pif`, `.dll`, `.sys`, `.drv`, `.ocx`, `.cpl`, `.app`, `.bin`, `.run`, `.elf`, `.dylib`, `.so` |
| Scripts y automatización | `.bat`, `.cmd`, `.ps1`, `.psm1`, `.psd1`, `.vbs`, `.vbe`, `.js`, `.jse`, `.wsf`, `.wsh`, `.hta`, `.sh`, `.bash`, `.zsh`, `.ksh`, `.csh`, `.command`, `.tool`, `.applescript`, `.scpt`, `.workflow` |
| Instaladores e imágenes | `.msi`, `.msp`, `.mst`, `.msix`, `.appx`, `.pkg`, `.mpkg`, `.dmg`, `.iso`, `.img`, `.deb`, `.rpm`, `.apk` |
| Accesos directos y registro | `.lnk`, `.url`, `.scf`, `.inf`, `.reg`, `.ins`, `.isp`, `.prf`, `.terminal`, `.desktop`, `.webloc` |
| Intérpretes y bytecode | `.jar`, `.jnlp`, `.class`, `.py`, `.pyc`, `.pyo`, `.pyw`, `.rb`, `.pl`, `.php`, `.lua`, `.tcl` |
| Office con macros | `.docm`, `.dotm`, `.xlsm`, `.xltm`, `.xlam`, `.pptm`, `.potm`, `.ppam`, `.sldm` |

> **Ejemplos:** `"Factura Octubre 2026.pdf"` (índice 2) ⇒ permitido y `"02_Factura_Octubre_2026.pdf"`; `"../../../Users/.ssh/CON.\u202efdp.exe"` ⇒ bloqueado; `"reporte.pdf.bat.cmd"` ⇒ bloqueado; `"install.sh"` ⇒ bloqueado.

#### 10.3.3 Nombre sanitizado (`sanitized_name`)

Solo para adjuntos que superan el bloqueo. `sanitized_name` es la representación segura, determinista e idempotente de `original_name` con el prefijo del índice. Debe cumplir:

- Se deriva de `original_name` aplicando NFKC; si queda vacío, se usa `"attachment"`.
- Se recortan espacios y puntos en los extremos y se eliminan los puntos iniciales (dotfiles); si vuelve a quedar vacío, `"attachment"`.
- Cada espacio o carácter de `< > : " / \ | ? *` se sustituye por `_`, sin colapsar repeticiones.
- La extensión es el sufijo desde el último punto (si no es el primer carácter); se limita a 20 bytes UTF-8 sin partir un carácter.
- El nombre sin prefijo no supera 150 bytes UTF-8; el nombre final (prefijo + raíz + extensión) no supera 153 bytes; si el prefijo mide más de 3 bytes (índice ≥ 100), la raíz se reduce en la diferencia. Ningún truncado parte un carácter.
- Se antepone `<index:02d>_`.
- La ruta resultante es `~/.mailquery/attachments/<driver>/<native_id>/<sanitized_name>`; si `<native_id>` supera el límite de componente (255 bytes en Windows; `NAME_MAX` en POSIX) o la ruta del directorio más un `sanitized_name` de 153 bytes excede el límite de la plataforma (240 bytes en Windows; `PATH_MAX` en POSIX), se usa, para todos los adjuntos del mensaje, un identificador estable de 32 caracteres hexadecimales en minúsculas en lugar de `<native_id>`: los 32 primeros caracteres de `SHA-256` sobre los bytes UTF-8 del `uid` completo (`<driver>:<native_id>`).
- El mismo `original_name` e `index` producen siempre el mismo resultado en todas las plataformas.

> **Ejemplo:** `" invoice.pdf "` (índice 1) ⇒ `01_invoice.pdf`; con índice 100 el prefijo es `100_` y la raíz se reduce para que el nombre final no supere 153 bytes.

**Nota:** `show` calcula `cached_path` con esta misma representación. El nombre incrustado en `message`/`warnings`/`hint` se muestra sin controles, sin segmentos de ruta y truncado a 120 bytes; los límites de `hint`/`detail`/`log_message` se definen en §12.6 y §14.

#### 10.3.4 Validación de aciertos por manifiesto

- **Sin tamaño esperado del driver:** un acierto de caché no se compara con el tamaño que informa el driver (en Outlook, `Attachment.Size` incluye el overhead de propiedades MAPI y no coincide con los bytes reales); ese tamaño solo alimenta los límites previos a la extracción (RF-47).
- **Manifiesto:** cada mensaje tiene `<message_dir>/.manifest.json` (`0600`, escrito de forma atómica) con una versión y, por índice, `sanitized_name`, `size_bytes` y `sha256`. El `sha256` es el calculado en staging sobre bytes que ya pasaron la pantalla de nombre y de *magic bytes*.
- **Acierto:** archivo regular en la ruta determinista cuyo nombre, tamaño (filtro previo, sin hash) y SHA-256 coinciden con su entrada; el SHA-256 completo se calcula en cada acierto. `cached: true` significa que el archivo existía, su SHA-256 coincide con el registrado y no se pidió `--force`.
- **Entrada sin verificar** (sin manifiesto o sin entrada, otro nombre, tamaño o SHA-256 distinto, manifiesto ilegible, con otra versión o enlazado): nunca se sirve. Se re-extrae con la pantalla completa; si sale bien, `os.replace` la sustituye y se registra; si la recuperación falla, se elimina (se borra el enlace, nunca su destino; un directorio nunca se borra recursivamente), se quita su entrada y se devuelve el error original. Un `--force` fallido conserva una entrada verificada.
- **Directorios enlazados:** si `attachments/`, `<driver>/` o `<native_id>/` es un symlink o una junction, no hay acierto, no se borra nada y la publicación falla con `E_IO` (exit 3) sin escribir en la caché.
- **`show` no cambia:** `cached_path` solo comprueba que el archivo exista como archivo regular; no lee el archivo ni el manifiesto. La validación ocurre solo en `attachment`.
- **Best-effort:** cada archivo se publica con su propio reemplazo atómico y el manifiesto se escribe después; si escribir el manifiesto falla, el comando no falla y el archivo publicado queda sin verificar, por lo que se re-extrae en la siguiente ejecución. La caché sigue sin ser estado de la aplicación: sin barrido, purga ni validación al arrancar (RF-51, ADR-24).

### 10.4 Ciclo de vida de la caché

- La caché es **best-effort y efímera**: no se considera estado y no se valida al arrancar; los aciertos se validan con el manifiesto del mensaje (§10.3.4).
- Un archivo ausente o borrado concurrentemente por el cron ⇒ miss y re-extracción (una vez). Si la re-extracción falla, el comando falla con el código de ese fallo (§12.6).
- La app no purga, no mide el tamaño total de la caché y no inspecciona su contenido fuera de lo que devuelve.
- Limpieza externa periódica (cron del operador): se borran archivos por antigüedad; no hay TTL configurable ni purga dentro de la app.

---


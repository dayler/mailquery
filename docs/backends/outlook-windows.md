# Backend Outlook clásico (Windows) — anexo del PRD

**Documento padre:** [`docs/PRD.md`](../PRD.md) v1.1, que manda sobre este anexo.
**Plataforma:** Windows 10/11 con **Outlook clásico de escritorio**
(Microsoft 365 Apps / Outlook 2016+, versión 16.0).
**Estado:** aprobado por el dueño del producto el 2026-11-03, tras el spike W1
ejecutado ese día en el host de referencia (resumen en §B.11).

Este anexo describe lo específico del backend Outlook: por qué se usa el
Outlook Object Model (COM), cómo se cumple el invariante I-1, qué stores entran
en el alcance y cómo se traduce el modelo común. Lo común a todas las
plataformas vive en el PRD. Regla de alcance (ADR-16): todo lo que `mailquery`
hace con macOS + Apple Mail se hace de forma equivalente aquí, ni más ni menos.

> **Fuera de alcance:** el **nuevo Outlook** (`olk.exe`) no expone COM ni un
> store local accesible; solo sería alcanzable vía Microsoft Graph (red +
> OAuth), lo que contradice el invariante I-1. Tampoco se soportan Outlook en
> la web ni Outlook para Mac.

---

## B.1 Contexto y alternativas evaluadas

| Vía | Veredicto | Motivo |
|-----|-----------|--------|
| **Outlook Object Model (OOM) vía COM** | **Elegida** | Única API local y soportada de lectura; funciona con stores en caché sin red. |
| Parsear `.ost`/`.pst` directamente | Descartada | Formato propietario; el `.ost` está bloqueado en exclusiva mientras Outlook corre. |
| Microsoft Graph / EWS | Descartada | Red, OAuth y credenciales; rompe I-1. |
| MAPI de terceros / Windows Search | Descartada | Dependencias nativas o índice parcial; no aportan frente al OOM. |

**Decisión (ADR-11):** el backend lee mediante el OOM por COM, con `pywin32`
como única dependencia (ADR-14), y **nunca** lanza Outlook (ADR-13).

---

## B.2 Cómo se cumple el invariante I-1 en Windows

Concreción del invariante general (PRD §4):

> `mailquery` no modifica ningún item, carpeta ni store de Outlook; no lanza
> Outlook; no provoca descargas desde el servidor; no lee carpetas ni items de
> stores que no estén disponibles localmente (de cualquier store del perfil sí
> lee propiedades de nivel store: etiqueta, tipo, ruta e identificador); y solo
> escribe dentro de `~/.mailquery`.

El OOM es una API de lectura **y escritura**: no hay un modo de solo lectura
impuesto por el sistema. La garantía se construye en capas:

1. **Sin lanzamiento:** solo se conecta a una instancia de Outlook ya abierta;
   nunca crea una. Si no hay ninguna ⇒ `E_OUTLOOK_NOT_RUNNING` (exit 6).
2. **Proxy de solo lectura con lista blanca:** todo objeto COM de Outlook se
   envuelve en un proxy que solo deja pasar los miembros de lectura de una
   lista blanca explícita (mantenida en el código y cubierta por tests). Todo
   lo demás (guardar, mover, copiar, borrar, enviar, mostrar, pedir descargas,
   asignar propiedades) se rechaza con `E_INTERNAL` antes de llegar a Outlook.
   El resto del código nunca ve el objeto COM crudo.
3. **Solo stores locales** (§B.3): los excluidos irían al servidor o a la red
   en cada lectura.
4. **Sin descargas:** un item con solo cabeceras en local se reporta con
   `body.available=false` y `W_BODY_NOT_LOCAL`; nunca se pide su descarga.
5. **S/MIME sin tocar:** no se lee cuerpo ni adjuntos (podrían pedir PIN o
   certificado).
6. **Escritura confinada:** toda escritura queda en `~/.mailquery`
   (`%USERPROFILE%\.mailquery`), incluida la caché de `pywin32`, que va en
   `~/.mailquery/tmp/gen_py` (PRD §10.2).
7. **Timeout de 30 s** (RF-33): una llamada a Outlook que no responde no
   cuelga al harness.

Leer propiedades de un item por OOM (incluido el cuerpo) no lo marca como
leído; solo lo hacen mostrarlo en la UI o asignar el estado, y ninguno está en
la lista blanca. El spike lo confirmó (§B.11). Verificación: §B.10.

---

## B.3 Alcance de stores (ADR-15)

**Candidatos** (lo que `mailboxes` lista en `accounts[]`/`mailboxes[]`):

| Store | Condición | Etiqueta |
|-------|-----------|----------|
| Buzón de entrega de una cuenta del perfil | Cuenta Exchange, IMAP, POP3 o EAS cuyo store es local: Exchange en modo caché; las demás, con su archivo de datos en un disco local | `Exchange (…)`, `IMAP (…)`, `POP3 (…)`, `EAS (…)` (con el email SMTP) |
| Archivo de datos `.pst` | En un disco local (incluido un disco extraíble) y que no es el buzón de entrega de una cuenta | `PST ({nombre visible})` |

Si un `.pst` es el buzón de entrega de una cuenta POP3, se etiqueta como la
cuenta (`POP3 (…)`), no como `PST (…)`.

**Excluidos** (lo que `mailboxes` lista en `excluded_stores[]`; RF-34):

| Store | `reason` | Etiqueta | `path` |
|-------|----------|----------|--------|
| Buzón delegado/compartido | `shared_mailbox` | `Exchange shared ({nombre})` | `null` |
| Carpetas públicas | `public_folders` | `Public Folders ({nombre})` | `null` |
| Cuenta Exchange sin modo caché | `online_mode` | la de la cuenta (`Exchange (…)`) | `null` |
| Otro store de Exchange sin copia local (p. ej. archivo en línea, grupos de Microsoft 365) | `online_mode` | su nombre visible | `null` |
| `.pst` (o archivo de una cuenta) en ruta UNC o unidad de red mapeada | `network_path` | la que tendría si fuera local | ruta completa |
| Cuenta de otro tipo | `unsupported_account_type` | `{tipo} ({smtp})` | ruta o `null` |
| Store del perfil cuyas propiedades no se pueden leer (p. ej. Outlook no logra conectar con el servidor de un store que no es local) | `unavailable` | su nombre visible si se pudo leer; si no, `unknown` | ruta si se pudo leer; si no, `null` |

Un store `unavailable` no impide leer el resto: los comandos siguen con los
stores candidatos. La resolución de `[scope]` contra excluidos: PRD §15.3.

**Carpetas ocultas:** las carpetas internas de sincronización (`Conflicts`,
`Sync Issues`, `Local Failures`, `Server Failures` y sus subcarpetas) no se
listan ni se leen; se identifican por su función, no por su nombre, así que
funciona en cualquier idioma de Outlook. La bandeja de entrada de cada store
(también de un PST) también se identifica por su función: es la carpeta que
Outlook tiene asignada como bandeja de entrada.

Como en macOS, ser candidato no basta: solo se leen las cuentas **declaradas**
en `[scope."<cuenta>"]` (PRD §15).

---

## B.4 Correspondencia con el modelo común

| Concepto común (PRD §11) | Outlook |
|--------------------------|---------|
| `uid` | **`EntryID` permanente** del item, en hex mayúsculas (140 caracteres en Exchange). |
| `message_id` / clave de dedupe | Message-ID de Internet; si falta o está vacío, el mensaje es único (RF-07). |
| `account.uuid` | Los 16 bytes del `PR_RECORD_KEY` del store con formato de UUID en mayúsculas (`8-4-4-4-12`). Es único por store (prueba A2), se lee sin abrir items y no cambia si se mueve un PST. |
| `account.label` / `account.email` | §B.3; email = dirección SMTP de la cuenta (`null` para PST). |
| `mailbox.path` | Ruta de la carpeta dentro del store, con `/` como separador. Dentro de cada segmento, `%` se escribe `%25` y `/` se escribe `%2F`. La bandeja de entrada se escribe siempre `INBOX`, también como prefijo (`INBOX/Facturas`). |
| `mailbox.name` | Último segmento de `path`, con la misma codificación. |
| `mailbox.url` | `outlook://<account-uuid>/<path>`, con los segmentos de `path` decodificados (la bandeja de entrada es siempre `INBOX`) y luego percent-encoded en UTF-8: se codifica todo carácter que no sea *unreserved* según RFC 3986. |
| Referencias en `mailbox_list` / `--include-mailbox` | Como en macOS (PRD §15.3); `INBOX` y `INBOX/…` funcionan en cualquier idioma. |
| Buzón agregado | No existe: `is_aggregate = false` siempre. |
| Carpetas listadas | Solo carpetas de correo, sin las ocultas de §B.3 (no calendario, contactos, tareas ni carpetas de búsqueda). |
| Items buscables | Correos (incluidos S/MIME) y convocatorias de reunión, sin marca de borrado IMAP. El resto (acuses, tareas, etc.) se ignora en `search`, `new`, `show` y contadores. |
| Contadores `total`/`unread` | Recuento de items buscables de la carpeta. |
| `date_received` / `date_sent` | Hora de entrega y de envío reales, leídas en UTC y emitidas como en macOS (PRD §12.5). |
| `from` / `to` / `cc` | Dirección SMTP que trae el propio item; nunca un DN interno de Exchange. Si el item no la trae, `address` es `""` y se conserva `name`. Nunca se consulta la libreta de direcciones (podría ir al servidor). |
| `is_flagged` | Marcado y no completado. Un marcado como completado es `false`. |
| `has_attachments` / adjuntos | Solo adjuntos no ocultos; los ocultos no cuentan ni se listan. |
| Cabeceras de `show` | Las cabeceras de transporte; si faltan (correo interno), se sintetizan From/To/Cc/Subject/Date/Message-ID. |
| Cuerpo | Texto plano; si está vacío, HTML convertido a texto (código común). |
| Adjuntos | Solo nombres; nunca se guardan. En S/MIME, `attachments: []`. Si el item no se puede abrir, `attachments: []` con `W_ATTACHMENTS_UNAVAILABLE`. |
| S/MIME (cifrado o firmado) | `readable=false` y `W_BODY_UNREADABLE` (texto en PRD §12.10), sin leer el contenido. |
| `body.partial` / `source.emlx_path` | Siempre `false` / siempre `null` (se conserva la forma del JSON). |

**Filtros y orden:** `--since` incluye y `--until` excluye al segundo; los
patrones se evalúan con el código común; `--to`/`--cc` siguen RF-17. Orden
total `(date_received, uid)`, comparando `uid` como string.

**Store de un uid en `show`** (resultados: PRD §12.4): el uid se busca en los
stores candidatos. Si no aparece en ninguno, se comparan los 16 bytes del
`EntryID` desde el offset 4 (identificador del store) con el `PR_RECORD_KEY`
de cada store excluido, que es una propiedad del store y se lee sin abrir sus
items (verificado, prueba A2 en §B.11): si coincide, el uid es de ese store
excluido; si no coincide con ninguno, el mensaje no se encuentra, con un hint
que remite a `excluded_stores` de `mailboxes`.

**`EntryID` y movimientos:** el `EntryID` cambia si el mensaje se **mueve** de
carpeta. `new` sigue siendo correcto porque el cursor usa la fecha; el riesgo
es una re-emisión puntual, aceptada por el dueño del producto (PRD §18).

---

## B.5 Requisitos de entorno

| Requisito | Detalle |
|-----------|---------|
| Sistema | Windows 10/11 x64. |
| Outlook | Outlook **clásico** 16.0, en ejecución, con un perfil cargado. La arquitectura (x86/x64) de Outlook no importa. |
| Python y dependencia | ≥ 3.11 (el de `pipx`) y `pywin32` (solo Windows; ADR-14). |
| Sesión | El harness debe correr en la **misma sesión interactiva** y con el **mismo nivel de integridad** que Outlook. Un proceso elevado o un servicio de Windows no ve el Outlook del usuario y obtiene `E_OUTLOOK_NOT_RUNNING`. |
| Modo de conexión | Cuentas Exchange en **modo caché**; las demás, con su archivo en disco local (§B.3). |
| Permisos | No hay equivalente a FDA; permisos del home: PRD RNF-05. |

---

## B.6 Object Model Guard

Outlook muestra un aviso de seguridad cuando un proceso externo lee
direcciones, cuerpos o destinatarios y no hay un antivirus activo reconocido, o
una directiva endurece la protección. En modo no interactivo ese aviso
bloquearía al harness: el chequeo `object_model_guard` de `doctor` lo anticipa
y el timeout de RF-33 evita el bloqueo.

Criterio del chequeo (decisión del dueño del producto), leyendo en solo
lectura las directivas de Outlook y el estado del antivirus:

- **Falla** si una directiva fuerza preguntar siempre o denegar el acceso
  programático, o si ninguna directiva lo decide y no hay un antivirus activo.
- **Pasa** si una directiva lo permite siempre, o si ninguna lo decide y hay un
  antivirus activo.
- Si ninguna directiva lo decide y el estado del antivirus no se puede
  consultar (p. ej. Windows Server): `ok=false`,
  `not evaluated: SecurityCenter2 unavailable`. Si una directiva lo decide, el
  antivirus no se consulta.

---

## B.7 Errores y warnings específicos

Hints de la detección del cliente (orden: PRD §12.6): `E_DEPENDENCY_MISSING` ⇒
`pipx reinstall mailquery`; `E_CLIENT_UNSUPPORTED` ⇒ instalar Outlook clásico
(el nuevo Outlook no está soportado); `E_OUTLOOK_NOT_RUNNING` ⇒ abrir Outlook
clásico con el mismo usuario, sin elevar, y reintentar.

| Código | Exit | Cuándo |
|--------|------|--------|
| `E_CLIENT_BUSY` | 5 | Outlook rechaza la llamada de forma transitoria: un reintento tras 100 ms y, si persiste, este error. |
| `E_CLIENT_TIMEOUT` | 3 | RF-33. |
| `E_PERMISSION` | 3 | Outlook deniega el acceso COM, p. ej. por directiva. |

Warnings de este backend: PRD §12.10 (texto de `W_STORE_EXCLUDED`: PRD §15.3).
`E_STORE_NOT_FOUND`, `E_SCHEMA_UNSUPPORTED`, `E_DB_BUSY`,
`E_ACCOUNT_LABELS_UNAVAILABLE`, `W_ACCOUNT_LABELS_UNAVAILABLE`,
`W_EMLX_MISSING` y `W_EMLX_CORRUPT` no se usan en este backend.

---

## B.8 `doctor` en Windows

Chequeos (nombres estables de `checks[].name`): `python`, `home`, `pywin32`,
`outlook`, `stores`, `readonly_strategy`, `object_model_guard`, `config`,
`state`, `lock`.

| Chequeo | Qué valida |
|---------|------------|
| `home` | `~/.mailquery` existe y el usuario puede escribir en él. |
| `pywin32` | `pywin32` importable en el intérprete de mailquery. |
| `outlook` | Outlook clásico registrado, versión ≥ 16.0, en ejecución y accesible. |
| `stores` | Stores candidatos (etiqueta y tipo) y excluidos (etiqueta, ruta y motivo). |
| `readonly_strategy` | `com_readonly`: proxy de lista blanca activo, conexión sin lanzamiento, caché de `pywin32` confinada. |
| `object_model_guard` | Criterio de §B.6. |
| `config` | PRD §12.8; además, `W_STORE_EXCLUDED` en el `detail` para cuentas declaradas excluidas (PRD §15.3). |

Dependencias (un chequeo cuya dependencia directa falló sale como
`not evaluated: <dependencia> failed`, PRD §12.8):

- `pywin32` → `outlook`;
- `outlook` → `stores` y `readonly_strategy`;
- `stores` → resolución de bloques de `config` (la sintaxis se valida siempre).
- `python`, `home`, `object_model_guard`, `state` y `lock` no dependen de otro
  chequeo.

Si Outlook está cerrado, `outlook` falla y nunca se lanza.

---

## B.9 Rendimiento

Presupuestos p95: PRD §19. El spike midió ~5 ms por item para abrirlo y leer su cuerpo (p95 ~6 ms) y
~350 ms para los metadatos de una carpeta de 240 items, lo que deja holgados
`search`, `new`, `show` y `--text`. `doctor` y `mailboxes` no se midieron.

---

## B.10 Verificación de solo lectura y escenarios esenciales

El test de hashes/`mtime` de macOS **no aplica**: Outlook reescribe el `.ost`
continuamente. El test bloqueante usa un Outlook falso en memoria envuelto por
el **mismo** proxy de producción: registra cada miembro invocado y falla si
alguno no está en la lista blanca o si se intenta una asignación; otro test
comprueba que el proxy rechaza los miembros prohibidos. Estos tests son Python
puro y corren en Linux, macOS y Windows sin Outlook. Fuera de CI, un smoke
manual contra el Outlook real comprueba que los contadores de no leídos del
alcance no cambian.

Escenarios esenciales y de borde que el backend debe cubrir:

- Cada tipo de cuenta candidata (Exchange en caché, IMAP, POP3, EAS, PST) se
  puede declarar, buscar y mostrar; cada motivo de exclusión aparece en
  `excluded_stores` y, si la cuenta está declarada, con `W_STORE_EXCLUDED`.
- S/MIME e item con solo cabeceras: motivo explícito, sin leer contenido ni
  provocar descargas.
- Bandeja localizada mostrada como `INBOX`; carpetas internas ocultas en
  cualquier idioma.
- Outlook ausente, cerrado o colgado (PRD §12.6 y RF-33), y un store que no
  se puede leer (`unavailable`).
- Fechas correctas (leídas en UTC) con zona local distinta de UTC y en cambio
  de horario.

---

## B.11 Resumen del spike W1 (2026-11-03)

Ejecutado con un script de solo lectura fuera del repositorio en el host de
referencia: Windows 11 x64, Outlook clásico (Microsoft 365 Apps) 16.0 x64, dos
cuentas Exchange en caché más un buzón compartido y carpetas públicas; sin
PST, IMAP ni EAS. Contadores de no leídos idénticos antes y después.

**Confirmado (y decisión que fijó):**

- **P-9** El id de las tablas de metadatos es corto y de sesión, distinto del
  `EntryID` del item ⇒ el `uid` es siempre el `EntryID` permanente (§B.4).
- **P-5** `pywin32` devuelve las fechas de recepción con hora local etiquetada
  como UTC ⇒ se usan las horas MAPI en UTC (§B.4).
- **P-7** Los filtros de fecha de Outlook no respetan los segundos ⇒ el corte
  exacto de `--since`/`--until` se hace en `mailquery` (§B.4).
- **P-8** Las carpetas internas se identifican por función ⇒ se ocultan sin
  depender del idioma (§B.3).
- **P-6** ~5 ms por item (n = 239) ⇒ presupuestos de PRD §19 (§B.9).
- **P-3 / P-11** Leer 239 cuerpos no cambió los no leídos ni mostró avisos (sin
  directivas, dos antivirus activos); con dispatch dinámico, `pywin32` no
  escribió archivos, aunque existe una caché previa en `%TEMP%` ⇒ la caché se
  confina a `~/.mailquery`.
- **P-1** Abrir un item por `EntryID` funciona en stores no predeterminados
  (239/239); con PST no probado.
- **P-4** `pywin32` 312, instalado en un venv aislado (sin paquetes del
  sistema, como el de `pipx`), se conecta al Outlook en ejecución sin pasos de
  post-instalación. Con la caché redirigida, `pywin32` crea sus archivos de
  caché solo en la ruta indicada.

**No probado** (riesgo residual, cubierto con el Outlook falso): **P-2**
el estado de descarga en modo solo cabeceras, IMAP y EAS; **P-3** el caso "sin
antivirus"; **P-10** abortar una llamada COM bloqueada; **P-12** la marca de
borrado IMAP; **P-13** PST local y en red.

**Prueba A2** (2026-11-03, solo lectura; contadores de no leídos idénticos
antes y después; sin archivos de caché fuera de la ruta redirigida):

- En los dos stores locales (300 items de INBOX en cada uno), los 16 bytes
  desde el offset 4 del `EntryID` permanente (140 caracteres hex) son un único
  valor por store, igual
  a su `PR_RECORD_KEY` y distinto del de cualquier otro store.
- `PR_RECORD_KEY` se lee en los 4 stores del perfil, incluidos el buzón
  compartido y las carpetas públicas (excluidos), sin abrir sus items, y los 4
  valores son distintos ⇒ regla de `show` de §B.4.
- No se pudo comprobar con items de un store excluido, porque leerlos violaría
  I-1; el formato del `EntryID` de Exchange fija ese campo como identificador
  del store. Si en algún caso no coincide, el resultado es `E_USAGE` "not
  found", nunca un error incorrecto de alcance.
- Un primer intento falló al enumerar los stores ("The attempt to log on to
  Microsoft Exchange has failed") con Outlook desconectado; con Outlook
  conectado funcionó ⇒ un store ilegible se reporta como `unavailable` (§B.3).

---

## B.12 Glosario específico

- **EntryID / StoreID:** identificadores (en hex) de un item y de un store
  dentro del perfil de Outlook.
- **OST / PST:** archivos de datos de Outlook; OST = caché local de una cuenta
  de servidor, PST = archivo de datos local.
- **Modo caché (Cached Exchange Mode):** Outlook mantiene una copia local del
  buzón y lee de ella sin ir al servidor.
- **Object Model Guard:** protección de Outlook que avisa cuando un programa
  externo accede a datos sensibles por COM.

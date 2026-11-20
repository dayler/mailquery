---
aliases: ["Sección 3", "Objetivos"]
tags: [prd]
---

## 3. Objetivos

### 3.1 Objetivo general

Entregar una herramienta local, simple y auditable, que permita a un harness de agentes leer y consultar los correos del cliente de escritorio local (Apple Mail o Outlook clásico) **sin ninguna posibilidad de modificar el almacén**, con un único contrato para ambas plataformas.

### 3.2 Objetivos específicos

**Tabla: Objetivos específicos y medida de éxito**

| ID | Objetivo | Medida de éxito |
|----|----------|-----------------|
| O1 | Leer correos nuevos de forma incremental | `mailquery new` devuelve cada mensaje una sola vez, sin duplicados ni omisiones dentro del alcance configurado |
| O2 | Buscar por asunto, contenido, remitente, destinatarios, fechas, carpeta y estado | `mailquery search` con filtros combinables y JSON estable |
| O3 | Garantizar solo lectura | Invariante I-1 (§4) cumplido según los criterios de aceptación de §20 |
| O4 | Integrarse con el harness | JSON en `stdout`, logs aparte, códigos de salida estables, ejecución no interactiva, `-h/--help` |
| O5 | Mantener simplicidad | Sin demonio, sin scheduler, sin base de datos de mensajes; biblioteca estándar más `css-inline` (ADR-33) en ambas plataformas y, en Windows, `pywin32` (ADR-14) |
| O6 | Ser predecible y observable | `doctor` diagnostica el entorno; cada ejecución deja un log con duración, conteos y errores |
| O7 | Paridad entre plataformas | Todo lo que `mailquery` hace con macOS + Apple Mail funciona de forma equivalente con Windows + Outlook clásico: mismos comandos, flags, configuración, catálogo de warnings (§12.10), códigos de error y forma del JSON; las únicas diferencias son las declaradas en §11.3 y §12.5; cambios en macOS: RNF-11 |
| O8 | Descubrimiento dinámico de backends | Backends internos y externos registrados en `mailquery.backends`, con `driver` único, `plugin_api = 1`, capacidades declaradas y carga diferida. |
| O9 | Esquema `[scope."<driver>:<cuenta>"]` | Selección de driver por prefijo, con el nativo del SO como fallback; todos los comandos consultan los drivers declarados. |
| O10 | `uid` opaco prefijado y routing `O(1)` | Todo `uid` en JSON y `state.json` es `"<driver>:<native_id>"`; `show` y `attachment` invocan directamente al driver del prefijo. |
| O11 | Contrato de plugin y de errores | El PRD y `INTERFACES.md` definen la interfaz, las capacidades, el protocolo de errores y la política de timeouts. |
| O12 | Chequeo `driver` en `doctor` y `--version` aditivo | `doctor` valida drivers, API y capacidades; `--version` lista los drivers instalados sin romper el formato existente. |
| O13 | Recuperación local con `mailquery attachment` | Extrae adjuntos locales hacia la caché devolviendo ruta, nombres, tamaño y SHA-256. |
| O14 | Bloqueo del mensaje completo, sanitización y escritura segura | Ningún archivo de un mensaje bloqueado se escribe; sanitización determinista; permisos `0700`/`0600`; staging atómico; límites configurables. |
| O15 | Saneado del texto en todas las salidas de contenido | Ningún campo de contenido, warning ni texto de error contiene ANSI, C0 (salvo `\n`/`\t`), C1, DEL, `Cf` ni los invisibles de RF-52; el resto del texto no cambia; lo que se muestra se puede buscar.                                                                                  |
| O16 | Cuerpo visible                                      | En un mensaje con HTML, `body_text`/`snippet` salen del HTML y no del texto plano alternativo; el texto de un elemento oculto por atributo `hidden` o por un estilo en línea o de una hoja `<style>` del mensaje no aparece, y `W_HIDDEN_CONTENT` lo señala.                          |
| O17 | Modos de visualización de URLs                      | `neutralize` (default), `keep` y `strip` funcionan por configuración y con `--strip-links` en todos los campos de RF-54; ninguno resuelve ni abre URLs.                                                                                                                                         |
| O18 | Señales de enlaces                                  | `W_EXTERNAL_LINKS`, `W_SCRIPT_LINK`, `W_LONG_URL` y `W_NON_ASCII_DOMAIN` aparecen por mensaje con el `uid` y el conteo correcto en `search`/`new`/`show`, sin URL ni dominio; con `neutralize`, un dominio no ASCII se ve en punycode y una URL de más de 2.048 caracteres se acorta. |
| O19 | Frontera de seguridad documentada                   | El harness dispone del anexo de seguridad, el ADR-28 y su checklist. La skill y los README contienen las reglas de RF-66 y cada respuesta de `search`, `new`, `show` y `attachment` lleva `content_notice`. |
| O20 | Señales del remitente y de adjuntos                 | `W_SENDER_AUTH_FAILED` y `W_REPLY_TO_MISMATCH` aparecen en `search`/`new`/`show` cuando el mensaje los justifica, y `W_ATTACHMENT_ACTIVE_CONTENT` en `attachment` por cada adjunto con un marcador de RF-62; ninguno usa red, abre ni descomprime nada.                               |
| O21 | Adjuntos de drivers remotos                         | `attachment --index` y `--all` extraen desde un plugin `"remote"` con el mismo JSON, bloqueo, límites, caché y manifiesto que desde uno `"local"`; el núcleo no abre red.                                                                                                             |
| O22 | Tope de extracción configurable y efectivo          | Ningún adjunto de un plugin externo mantiene `attachment` esperando más de `[attachments].timeout_seconds` (60 s por defecto), aunque el plugin no responda; al vencer, `E_CLIENT_TIMEOUT` sin archivos nuevos.                                                                       |
| O23 | Fila mínima por defecto                             | Sin `--fields`, cada fila de `search` y `new` tiene exactamente los seis campos de RF-67 y, sin `--text`, no se lee ningún cuerpo: solo las cabeceras de A6 de los mensajes devueltos.                                                                                                                            |
| O24 | Respuestas en una llamada                           | Los últimos mensajes por remitente, dominio, carpeta, cuenta o fecha (`--group-by`) y el total de resultados (`--count`) se obtienen con un solo `search`, sin el límite de 200 filas.                                                                                                |
| O25 | Contenido a petición                                | El cuerpo, los destinatarios y los datos de carpeta solo salen cuando se piden con `--fields`, en `search`, `new` y `show`.                                                                                                                                                           |
| O26 | Peticiones sin preparación | La skill no ejecuta `doctor` ni `mailboxes` antes de una petición: leer un correo con adjunto son tres llamadas (`search`, `show` y `attachment`); un `search` sin resultados indica en `hint` cuántas carpetas y cuentas buscó y cómo ampliar el alcance. |
| O27 | Carpetas sin redundancia | Sin `--fields`, `mailboxes` muestra cada cuenta una vez con sus carpetas, cada una solo con `path` e `included`, no cuenta ningún mensaje y cumple el presupuesto p95 de `mailboxes` de §19. |
| O28 | Diagnóstico de plugins | Un plugin declarado mal configurado aparece como fallo en `doctor`, en su sección y con `--failures`, sin cambiar `plugin_api = 1` ni el exit 0. |

### 3.3 No objetivos

- No escribir, mover, copiar, convertir, marcar leído/no leído, etiquetar ni borrar correos.
- No enviar, responder, reenviar ni poner en cola correos.
- El núcleo no descarga adjuntos ni dispara descargas desde el servidor (IMAP, Exchange ni otras). Un plugin externo con `network: true` y `attachments: "remote"` puede obtener bytes desde su origen; su uso de red es responsabilidad del plugin (ADR-22), y `attachment` procesa esos bytes como los de un driver local (RF-48).
- No lanzar el cliente de correo (ni Mail.app ni Outlook).
- No crear reglas, buzones inteligentes ni cambiar preferencias del cliente.
- No construir una copia local de los correos (sin índice FTS, §22.1).
- No programar tareas: el harness decide cuándo invocar la herramienta (operación bajo demanda).
- En el núcleo, no soportar otros clientes: ni el **nuevo Outlook** (`olk`, que no expone COM ni un store local y solo sería alcanzable por Microsoft Graph, con red y OAuth, contra I-1), ni Outlook en la web, ni Outlook para Mac, ni Thunderbird u otros. Linux no tiene backend de datos (solo desarrollo/CI). Se admite leer cuentas servidas por plugins externos instalados por el usuario (§6.5); la implementación de plugins concretos queda fuera de esta versión.
- No incluir interfaz gráfica, servidor HTTP ni demonio.

- **No implementar** plugins externos concretos en esta versión: `mailquery-graph`, `mailquery-thunderbird`, `bird` u otros. El contrato queda listo para ellos (§4, §6.5).
- No escribir adjuntos fuera de `~/.mailquery/attachments/` (ni siquiera temporales: el staging vive bajo `~/.mailquery/tmp/` y se limpia).
- **No habrá flag de ruta de salida (`--out DIR`): está descartado definitivamente.** La caché en `~/.mailquery/attachments/` es la única ruta de escritura; `--force` es la única forma de reemplazar un archivo.
- No devolver contenido binario ni Base64 en `stdout`; no ejecutar ni abrir archivos extraídos.
- No extraer adjuntos S/MIME.
- No añadir daemon, scheduler ni limpieza automática: la caché la limpia un cron externo (§10.4).
- No inspeccionar archivos comprimidos ni el contenido de documentos OLE/PDF más allá de los marcadores de contenido activo de RF-62, que avisan sin descomprimir ni bloquear; el catálogo y los *magic bytes* son la única barrera de bloqueo (§23.1, riesgos aceptados).
- No añadir campos `"backend"`/`"driver"` al JSON de mensajes: el driver se deriva del prefijo del `uid`.

**F1:**

- Detectar o bloquear inyección de prompt, phishing, malware o URLs maliciosas.
- Resolver, acortar, expandir, validar o pedir reputación de URLs.
- Renderizar HTML, imágenes o adjuntos, o abrir, ejecutar o descomprimir adjuntos.
- Verificar SPF, DKIM o DMARC por cuenta propia (exige consultas DNS); A6 solo repite el veredicto del proveedor.
- Sustituir al cliente de correo o mostrar correos a una persona.
- Poner en cuarentena o rechazar un mensaje por su contenido; `mailquery` da señales y el harness decide.
- Calcular el estilo efectivo completo (hojas enlazadas, reglas `@media`, colores) o detectar técnicas de ocultación distintas de las de RF-53.
- Sanear identificadores que el usuario reutiliza como entrada o referencia (cuentas, carpetas, direcciones, `uid`, `message_id`, rutas).
- Cambiar los campos existentes, el bloqueo, la caché, el manifiesto, `state.json` o el trato a los plugins (RF-64).

**F2:**

- Un tope de tiempo total por comando: el tope es por adjunto.
- Cambiar o hacer configurables los 30 s por operación de metadatos o por llamada COM de Outlook (RF-31).
- Detener el hilo de un plugin que no responde (RNF-21, §23.1).
- Corte duro en Apple Mail y Outlook (RNF-21).

**F3:**

- Sustituir `new` por `search --unread` o mover el cursor a `search`.
- `--group-by` y `--count` en `new`: un límite por grupo dejaría mensajes sin emitir que el cursor saltaría.
- Agrupar por conversación (`thread`), por destinatario (`to`, `cc`) o por asunto, o agregados distintos del recuento (tamaños, medias).
- Salida en forma de tabla, omitir valores neutros o JSON compacto.
- Un valor por defecto de `--fields` en `config.toml`.
- Quitar campos de la fila mínima de `search` y `new`.
- Ejecutar los chequeos de `doctor` dentro de otros comandos o añadir el alcance buscado a cada respuesta.
- Un `hint` de cero resultados en `new`: sin correo nuevo, `count: 0` es la respuesta normal.
- `--fields all` en `mailboxes`: cada campo de carpeta se pide por su nombre.
- Ocultar carpetas de `mailboxes` por su tipo o porque están vacías.
- Chequeos de un plugin que dependan de chequeos del núcleo o de otro plugin, salvo del chequeo `driver` común.

---


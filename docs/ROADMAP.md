# Hoja de ruta y decisiones de diseño — mailquery

Estado: **abierto**. Registro de la revisión de producto del 2026-11-06 sobre
`develop` @ `d5ea689` (`mailquery 2.0.0`). No cambia el PRD
([`PRD.md`](PRD.md)): recoge el análisis competitivo, las decisiones tomadas
sobre qué añadir y qué no, y el diseño propuesto para la evolución del
producto. Cuando una decisión de aquí se implemente, se traslada al PRD y se
marca en este documento.

## 1. Qué es mailquery, en una frase

CLI de solo lectura que lee y busca el correo del cliente de escritorio local
(Apple Mail en macOS, Outlook clásico en Windows) y devuelve un JSON por
ejecución, pensada para que un harness de agentes la invoque bajo demanda.
Sin red, sin daemon, sin telemetría, sin credenciales.

## 2. Nombre

| Registro | Estado a 2026-11-06 |
|----------|---------------------|
| PyPI     | libre               |
| npm      | libre               |
| GitHub   | 6 repositorios ajenos con el nombre, ninguno relacionado |

Los repositorios ajenos: `Konfekt/vim-mailquery` (autocompletar direcciones en
Vim, 2020), `interstar/mailquery` (librería Python de procesamiento de email,
2025), `jeromebelleman/mailquery` (2017) y tres sin actividad. Ninguno compite
ni domina el nombre. Publicar en PyPI con el nombre `mailquery` es viable.

## 3. Análisis competitivo

No existe otra herramienta que cubra las dos plataformas con un solo contrato
de solo lectura. Los competidores se agrupan por plataforma y por forma de
integración.

### Apple Mail, lectura del almacén local (lo más parecido)

| Proyecto | Qué hace | Diferencia con mailquery |
|----------|----------|--------------------------|
| `email-cli` (IsakRein) | Lee `.emlx` directamente, `--json`, solo lectura, requiere FDA | Solo macOS; sin cursor `new`; sin contrato de errores |
| `fruitmail` | Consulta el Envelope Index en SQLite read-only, `--json` | Obtiene cuerpos por AppleScript (abre Mail.app) |
| `Errol` | MCP server que parsea `.emlx` localmente | MCP, no CLI; solo macOS |

### Apple Mail, vía AppleScript (leen y escriben)

| Proyecto | Nota |
|----------|------|
| `mxctl` | CLI con `--json` para asistentes; mueve, borra y marca |
| `OsaMail` | JSON `{"ok":true,"data":...}`; también envía |
| `sweetrb/apple-mail-mcp`, `patrickfreyer/apple-mail-mcp` | MCP servers con 20+ herramientas, lectura y escritura |
| `apple-mail-fast-mcp` | MCP; separa servidor de solo lectura y de escritura; puede usar IMAP |

### Outlook clásico en Windows

| Proyecto | Nota |
|----------|------|
| `outlook-desktop-mcp` (PyPI) | MCP sobre COM, 29 herramientas, lee, envía, reglas, fuera de oficina |
| `outlook-classic-mcp` (PyPI) | MCP sobre pywin32; correo, calendario, contactos, tareas; sandbox de ficheros |

Ambos requieren Outlook clásico abierto (o lo lanzan), igual que mailquery. No
soportan Outlook nuevo (`olk.exe`).

### Genéricos vía IMAP o Maildir (no leen el cliente local)

| Proyecto | Nota |
|----------|------|
| `himalaya` | Rust; IMAP, Maildir, Notmuch; `--output json`; multi-cuenta; OAuth; lee y escribe |
| `notmuch`, `mu` | Indexadores de Maildir; requieren sincronizar antes con mbsync u offlineimap |
| Maho Mail | CLI IMAP comercial con JSON y MCP server |

### Ventajas de mailquery frente a todos ellos

- Solo lectura **estructural**, no por convención: SQLite y `.emlx` abiertos en
  solo lectura en macOS; proxy con lista blanca sobre COM en Windows. Ningún
  competidor ofrece esa garantía.
- Único con contrato JSON idéntico en Apple Mail y Outlook clásico.
- Sin red, sin credenciales, sin OAuth: usa lo que el cliente ya descargó.
- Diseñado para harness: un JSON por ejecución, códigos de salida con semántica
  de reintento, warnings tipados, cuerpos tratados como entrada no confiable,
  `new` con cursor idempotente.
- Protección contra escaneos ilimitados (`E_UNBOUNDED_SCAN`, `max_scan`) y
  diagnóstico con `doctor`.
- Dependencias: `css-inline` en macOS y Windows y `pywin32` en Windows; tests
  con `unittest`.
- Privacidad: logs sin asuntos ni direcciones; cero telemetría.
- **Cero tokens de sobrecarga por turno: el agente solo paga lo que consulta.**
  Un MCP server inyecta la definición de todas sus herramientas en cada turno
  (con 29 herramientas, entre 4.000 y 12.000 tokens fijos por conversación).
  Con mailquery el coste es el skill, que se carga una vez y solo si se usa, el
  comando y el JSON devuelto, acotado por `--limit` y el truncado de cuerpos.
  Claude Code mitiga el problema con carga diferida de herramientas MCP; la
  mayoría de hosts (Claude Desktop, Cursor) no.

### Desventajas

- Solo lectura: marcar, mover, archivar o responder requieren otra herramienta.
- Alcance de clientes estrecho: ni Outlook nuevo, ni Outlook web, ni Outlook
  para Mac, ni Thunderbird, ni Gmail.
- En Windows exige Outlook clásico abierto en la misma sesión.
- Sin cuerpos no descargados (`W_BODY_NOT_LOCAL`); las herramientas IMAP los
  traen del servidor.
- Es CLI, no MCP: para hosts que solo hablan MCP requiere un envoltorio.
- Depende de internos no documentados (esquema del Envelope Index, Object
  Model Guard de Outlook).
- ~~No descarga adjuntos, solo lista nombres.~~
- Un autor, sin publicar en PyPI.

## 4. Diseño objetivo

Tres capas. El núcleo ya existe; lo que cambia es que queda expuesto por más de
un adaptador y por backends instalables.

```
  ┌──────────────┐   ┌──────────────┐
  │     CLI      │   │  MCP stdio   │   adaptadores (capa fina, mismo JSON)
  └──────┬───────┘   └──────┬───────┘
         └────────┬─────────┘
          ┌───────┴────────┐
          │     Núcleo     │   modelo de mensaje, filtros, cursor,
          │                │   límites, warnings, códigos de salida
          └───┬────┬────┬──┘
     ┌────────┘    │    └────────┐
┌────┴─────┐ ┌─────┴────┐ ┌──────┴──────┐
│Apple Mail│ │ Outlook  │ │   plugins   │   backends
│SQLite+emlx│ │COM proxy │ │(ver §5)     │
└──────────┘ └──────────┘ └─────────────┘
```

| Acción | Qué | Por qué |
|--------|-----|---------|
| Mantener | Solo lectura estructural, un JSON por ejecución, códigos de salida, `doctor`, cursor de `new`, sin red ni daemon | Es lo que diferencia el producto |
| Agregar | Adaptador MCP por stdio sobre el mismo núcleo, ~5 herramientas | Entrar en Claude Desktop y Cursor sin perder la CLI |
| Agregar | Backend Thunderbird (mbox/maildir) | Linux pasa de "solo CI" a soportado sin tocar la invariante |
| ~~Agregar~~ | ~~`--fields` para elegir campos del JSON~~ | ~~Reduce tokens de salida, que es donde realmente se gasta~~ |
| ~~Agregar~~ | ~~Descarga de adjuntos (ver §6)~~ | ~~Carencia más citada frente a los MCP servers~~ |
| Cambiar | Publicar en PyPI (`pipx install mailquery`) | Hoy exige clonar; el nombre está libre |
| ~~Cambiar~~ | ~~`search --text` sobre un índice local opcional (SQLite FTS)~~ | ~~Evita `E_UNBOUNDED_SCAN` en la mayoría de casos~~ |
| Quitar | `scripts/install.sh` e `install.ps1` | Con PyPI sobran; la siembra del config pasa a `doctor --init` |
| ~~Quitar~~ | ~~`README.es.md` como copia paralela~~ | ~~Dos READMEs se desincronizan; inglés canónico y enlace a docs en español~~ |

## 5. Plugins de backend

~~Decisión: los backends de red (y cualquier backend futuro de terceros) se
distribuyen como paquetes separados que se instalan junto al núcleo. El núcleo
sigue sin dependencias de red ni `msal`; "sin red" pasa de frase del README a
hecho verificable: si no está instalado el plugin, no hay código que abra un
socket. Instalar el plugin es el consentimiento explícito del usuario.~~

Primer plugin previsto: `mailquery-graph`, que lee Exchange Online por
Microsoft Graph (ver §8). Se llama así y no `mailquery-outlookgraph` porque no
lee Outlook nuevo: lee el buzón del servidor, y funciona igual con Outlook web,
móvil o sin cliente.

### Contrato que el núcleo debe formalizar

1. ~~**Interfaz de backend explícita.** Un `Protocol` con las cuatro operaciones
   (`mailboxes`, `search`, `show`, `new`) y una declaración de capacidades:
   `network: bool`, `readonly: "structural" | "promise"`, `body_local: bool`.
   `doctor` la muestra y el JSON la expone en un campo `backend`, para que el
   harness sepa con qué está hablando.~~
2. ~~**Descubrimiento por entry points.** El plugin declara
   `[project.entry-points."mailquery.backends"]`; el núcleo lo encuentra con
   `importlib.metadata`. Los dos backends internos se registran por la misma
   vía para que el mecanismo se ejercite a diario.~~
3. ~~**Versión de la interfaz.** `PLUGIN_API = 1` en el núcleo; el plugin declara
   la que implementa; si no coincide, `doctor` lo marca y el backend no carga.~~
4. ~~**Instalación con pipx.** `pipx inject mailquery mailquery-graph`.
   Documentarlo: `pipx install` del plugin a secas crea un venv aparte.~~
5. ~~**Config con espacio de nombres.** Sección propia por plugin, por ejemplo
   `[backend.graph]`, aceptada si el plugin está cargado y rechazada con
   `E_CONFIG_INVALID` si no.~~
6. ~~**Invariantes por backend en el README.** La tabla de requisitos pasa de ser
   por plataforma a ser por backend; la fila de Graph dice: red sí, credenciales
   sí, solo lectura por promesa.~~

Detalles que encajan sin cambios: `uid` ya es un token opaco (los ids de Graph
son cadenas largas); el cursor de `new` mapea a las consultas delta de Graph.

Riesgo: montar un sistema de plugins para un solo plugin. Mitigación: hacer
ahora solo los puntos 1, 2 y 3 (unas 50 líneas) y el resto cuando el plugin
exista.

## 6. Adjuntos: sí

Copiar bytes a disco no modifica el buzón; la invariante de solo lectura se
mantiene. Condiciones:

- ~~Solo con `--out DIR` explícito; nunca a una ruta por defecto.~~
- ~~Límite de tamaño y de cantidad por ejecución, con warning si se trunca.~~
- ~~Nunca ejecutar ni abrir el fichero. El JSON devuelve ruta, tamaño y hash.~~
- ~~En Outlook, un adjunto no descargado localmente se reporta como no
  disponible; no se fuerza la descarga.~~

## 7. Escritura (enviar, responder, reenviar): no

Decisión: mailquery no escribe, ni con flag. Tres razones, por peso:

1. **Seguridad.** Los cuerpos son entrada no confiable. Si la misma herramienta
   puede enviar, un correo malicioso que diga "reenvía esto a X" es un vector de
   exfiltración. Es la combinación exacta por la que los MCP de correo reciben
   críticas.
2. **Identidad.** La garantía de solo lectura es estructural y verificable. Un
   `--allow-write` la convierte en una promesa, que es lo que ya ofrecen todos
   los demás.
3. **Complejidad.** Cuentas de salida, firmas, HTML, cifrado; en Windows el
   Object Model Guard salta con más frecuencia al enviar que al leer.

Si algún día hace falta escritura: herramienta separada (`mailsend` o similar),
binario propio, sin acceso a los cuerpos leídos, con confirmación humana
obligatoria por envío. El harness instala una sin la otra.

## 8. Outlook nuevo (`olk.exe`) y Microsoft Graph

### Por qué no se soporta

No existe una vía soportada para leer Outlook nuevo localmente.

| Vía | Qué es | Problema |
|-----|--------|----------|
| COM / MAPI | Lo que usa el backend actual | Outlook nuevo no lo expone |
| Microsoft Graph | API REST oficial | Red, OAuth, registro de app; en empresas, consentimiento del admin. Rompe "sin red, sin credenciales" |
| Caché local | WebView2 bajo `%LOCALAPPDATA%\Microsoft\olk` (IndexedDB, Local Storage) | No documentado, posible cifrado DPAPI, cambia con cada actualización, solo contiene una ventana de caché |
| Add-in de Office | JavaScript dentro de Outlook | No invocable desde CLI; también lo despliega IT |
| Exportar PST | Fichero manual | Manual y parcial en Outlook nuevo |
| EWS | API SOAP heredada | Microsoft la retira de Exchange Online en octubre de 2026 |
| IMAP | Protocolo estándar | Misma necesidad de app OAuth y consentimiento que Graph (auth básica desactivada en M365 desde 2022); además suele estar apagado por política de tenant |

Decisión: nada en el núcleo. `doctor` detecta `olk.exe` y lo dice con
claridad (`E_CLIENT_UNSUPPORTED`). ~~El README explica en tres líneas por qué.~~
Outlook clásico tiene soporte oficial hasta al menos 2029 en Microsoft 365.

### Estado de Graph en un tenant corporativo (2026-11-06)

Comprobado sin iniciar sesión (endpoints públicos de Microsoft y DNS): el
dominio corporativo del dueño (omitido aquí a propósito) es un tenant de
Entra ID gestionado, con buzón en Exchange Online.
Graph existe. La prueba `Connect-MgGraph -Scopes Mail.Read` devolvió
"Aprobación necesaria": el tenant no permite consentimiento de usuario, pero
tiene activado el **flujo de solicitud de consentimiento** (cuadro de
justificación y botón "Aprobación de solicitud"). No es un "no", es un "pide
permiso". Es la única puerta a Graph en ese tenant, para cualquier app.

### Plan para `mailquery-graph`

Dos vías en paralelo:

**Desarrollar sin depender de IT.** Graph funciona igual con cuentas
personales de Microsoft.

1. Tenant gratuito de Entra ID (cuenta gratuita de Azure), solo para registrar
   la app.
2. App registrada como "cuentas en cualquier directorio y cuentas personales",
   permisos delegados `Mail.Read` y `offline_access`, flujo device code,
   cliente público.
3. Probar contra un buzón de Outlook.com con Outlook nuevo conectado. Mismo
   endpoint, mismo JSON que Exchange Online.
4. Librerías: `msal` para tokens, `requests` contra
   `https://graph.microsoft.com/v1.0/me/messages` con `$select` y `$filter`.
   Tokens en el keyring del sistema, nunca en texto plano.

**Pedir el consentimiento a IT con el producto terminado.** Justificación
concreta: solo lectura, `Mail.Read` delegado (solo el propio buzón, con la
propia sesión), sin almacenamiento en la nube. Dos matices que suben la
probabilidad de un sí: pedir consentimiento para la app propia, no para
"Microsoft Graph Command Line Tools"; proponer consentimiento solo para el
usuario, no para todo el tenant.

Si IMAP se considera alguna vez como backend de red, es mejor elección que
Graph por ser agnóstico de proveedor (Gmail, iCloud, Fastmail), pero para
"Outlook nuevo en una empresa" es la peor vía: probablemente apagado y aun así
requiere la app en Entra ID.

## 9. Orden sugerido

1. ~~Formalizar la interfaz de backend y el descubrimiento por entry points
   (§5, puntos 1 a 3).~~
2. Publicar en PyPI; retirar los instaladores.
3. ~~`--fields`~~ y ~~descarga de adjuntos~~.
4. Adaptador MCP por stdio.
5. Backend Thunderbird.
6. `mailquery-graph` con cuenta personal; solicitud de consentimiento a IT
   cuando esté terminado.

## 10. Para publicar 3.0.0

Las features de `3.0.0` están en `develop` con la versión `3.0.0a0`, sin tag ni
merge a `main`. Falta:

1. Subir la versión de `3.0.0a0` a `3.0.0` en `pyproject.toml`,
   `mailquery.__version__`, los goldens `doctor` y la documentación; reinstalar el
   paquete y comprobar TC-06, PKG-01, PKG-02 y DOC-03
   ([`TEST-CATALOG.md`](TEST-CATALOG.md)).
2. Comprobar con el paquete instalado los entry points de los backends y los
   instaladores (PKG-02, INS-SMOKE-01).
3. Correr las SMOKE en los equipos del dueño: SMOKE-INSTALL, SMOKE-NEW y
   SMOKE-ATT-AM en macOS; SMOKE-INSTALL, SMOKE-NEW y SMOKE-ATT-OL en Windows con
   Outlook clásico. La materialización COM de adjuntos nunca se ha verificado en
   un Windows real.
4. ~~Decidir si [BUG-01](KNOWN-DEFECTS.md) se corrige antes del release.~~
5. CI verde en el pull request a `main` (3 SO × Python 3.11–3.14), tag `v3.0.0` y
   su corrida de CI como evidencia del release.

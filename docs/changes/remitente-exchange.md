---
aliases: ["Dirección del usuario como remitente o destinatario de Exchange en Outlook"]
tags: [cambio]
---

# Dirección del usuario como remitente o destinatario de Exchange en Outlook

**Tipo:** cambio
**Base:** PRD 2.9
**Fecha:** 2026-11-27
**Aprobación:** Ariel Salazar Hinojosa, 2026-11-27
**Paquete:** 3.0.0 (menor)

## Estado

aprobado

## Contexto

### Problema

En Exchange, un remitente o destinatario de la propia organización se guarda con tipo de dirección `EX` y una dirección interna de Exchange en lugar de su dirección SMTP. La dirección SMTP solo está en el item cuando Outlook o el servidor la añadieron (`PR_SENDER_SMTP_ADDRESS` en el remitente, `PR_SMTP_ADDRESS` en un destinatario). Los mensajes que crea el propio Outlook, como los de Enviados, no suelen llevarla.

Por §11.3, la dirección de `from`, `to` y `cc` en Outlook es la dirección SMTP que trae el item; si no la trae, `address` es `""` y se conserva `name`. Así, el correo que envía el usuario sale con `from.address` vacío:

- `search --from <dirección del usuario>` no lo encuentra; solo lo encuentra el nombre.
- `--group-by from` y `--group-by domain` lo juntan en un grupo de dirección o dominio vacío.
- Un harness que resume los pendientes del usuario no puede saber, por la dirección, qué mensajes escribió él.

### Captura en un Outlook real

Una captura de solo lectura en un Outlook clásico con dos cuentas Exchange en modo caché, de organizaciones distintas, midió los últimos 50 mensajes de Enviados y de Recibidos de cada cuenta y los destinatarios de 10 mensajes por carpeta.

**Tabla: Remitente de los 50 mensajes más recientes de Enviados, por cuenta**

| Medida | Cuenta 1 | Cuenta 2 |
|---|---|---|
| `from.address` vacío con la regla actual | 34 | 45 |
| `from.address` con una dirección del item distinta de la de la cuenta (alias de otro dominio) | 16 | 0 |
| `from.address` con la dirección de la cuenta | 0 | 5 |
| Remitente identificado como el usuario de la cuenta comparando su EntryID | 50 | 50 |
| Dirección resuelta por la libreta de direcciones (`GetExchangeUser`) | 50 | 0 |
| Dirección en `PR_SENT_REPRESENTING_SMTP_ADDRESS` entre las vacías | 0 | 14 |

- **Recibidos y destinatarios.** Los 100 mensajes de Recibidos traen la dirección SMTP del remitente, también los internos, y los 59 destinatarios revisados traen la suya. Ningún mensaje de Recibidos tiene como remitente a un usuario de otra cuenta.
- **Identidad del usuario.** `Account.CurrentUser.EntryID`, comparado con `PR_SENDER_ENTRYID` por `NameSpace.CompareEntryIDs`, identifica al usuario en los 100 mensajes de Enviados, también donde el item trae dos formas distintas del EntryID. Leer la identidad tarda unos 4 ms por cuenta y cada comparación, menos de 1,2 ms. No consulta la libreta de direcciones.
- **Libreta de direcciones.** En la cuenta 1 resuelve cada remitente en unos 5 ms. En la cuenta 2 encuentra la entrada sin dirección SMTP y tarda entre 0,3 y 1,4 s por consulta.
- **Propietario del buzón.** `PR_MAILBOX_OWNER_ENTRYID` no se puede leer en ninguno de los dos stores.
- Outlook no mostró ningún aviso de seguridad.

### Solución elegida

Cuando el item no trae la dirección SMTP de un remitente o destinatario, el driver de Outlook compara su EntryID con la identidad del usuario de cada cuenta Exchange del perfil. Si coincide, la dirección es la de esa cuenta. El resto no cambia: la dirección que trae el item sigue mandando y, sin coincidencia, `address` sigue siendo `""`.

### Alternativas descartadas

- **Libreta de direcciones (`AddressEntry.GetExchangeUser().PrimarySmtpAddress`).** Completaría también las direcciones de otras personas, pero en la captura no hubo ninguna vacía fuera de los mensajes del usuario. Con una libreta que no está en local (cuenta 2) tarda hasta 1,4 s y no da la dirección, y puede consultar al servidor, lo que contradice §4 ("no provoca descargas desde el servidor"). Para los mensajes del usuario da el mismo resultado que la identidad de la cuenta.
- **Carpeta de Enviados ⇒ el usuario.** No cubre los mensajes del usuario movidos a otras carpetas o archivados en un PST, y atribuiría al usuario un mensaje enviado por un delegado.
- **Propietario del buzón (`PR_MAILBOX_OWNER_ENTRYID`).** No se puede leer en los stores de la captura.
- **"Enviado en nombre de" (`PR_SENT_REPRESENTING_*`).** Completa 14 de 79 remitentes vacíos y ninguno de la cuenta 1.
- **Dirección de `config.toml`.** La clave de `[scope]` puede ser una etiqueta, un email o un UUID; el driver ya lee la dirección de cada cuenta de Outlook (`account.email`).
- **Sustituir la dirección del item por la de la cuenta cuando el remitente es el usuario.** Unificaría los alias, pero cambiaría una dirección que el item sí trae y que es la que usó el mensaje.
- **Caché persistente de direcciones.** La comparación es local y rápida; basta con recordar cada EntryID durante el comando.

### Preguntas abiertas

Ninguna.

## Requerimiento

### Dirección de `from`, `to` y `cc` en Outlook

La dirección de un remitente o destinatario sale de la primera regla que da una:

1. **Dirección del item.** La dirección SMTP que trae el propio item, como hoy: `PR_SENDER_SMTP_ADDRESS` o, con tipo de dirección `SMTP`, `PR_SENDER_EMAIL_ADDRESS` en el remitente; `PR_SMTP_ADDRESS` o, con tipo `SMTP`, `PR_EMAIL_ADDRESS` en un destinatario.
2. **Usuario de una cuenta.** Si el EntryID del remitente (`PR_SENDER_ENTRYID`) o del destinatario (`Recipient.EntryID`) es, según `NameSpace.CompareEntryIDs`, el del usuario de una cuenta Exchange del perfil (`Account.CurrentUser.EntryID`), la dirección es la de esa cuenta (`Account.SmtpAddress`, el mismo valor que `account.email`).
3. **Sin dirección.** Si no, `address` es `""` y se conserva `name`.

Reglas:

- **Nunca una dirección interna.** La dirección nunca es una dirección interna de Exchange ni se deduce del nombre o de la dirección interna.
- **Sin libreta de direcciones.** Nunca se busca a una persona en la libreta de direcciones. La identidad del usuario de cada cuenta se lee de la propia cuenta y la comparación de EntryIDs es local.
- **Todas las carpetas y stores.** La regla 2 se aplica al item de cualquier carpeta y de cualquier store candidato, también de un PST, y con la identidad de cualquier cuenta Exchange del perfil, no solo la del store del item.
- **El nombre no cambia.** `name` es siempre el que trae el item.
- **Dirección del item primero.** Un item que trae una dirección SMTP del usuario distinta de la de la cuenta, como un alias, conserva la suya.
- **Cuenta sin identidad.** Una cuenta cuya identidad no se puede leer, o que no tiene dirección SMTP, no completa ninguna dirección; el comando sigue sin error ni warning.
- **Mismo dato en todos los usos.** `from`, `to` y `cc` de `search`, `new` y `show`, los filtros `--from`, `--to` y `--cc`, y `--group-by from` y `--group-by domain` usan la dirección resultante.
- **macOS.** Sin cambios: Apple Mail ya da la dirección SMTP.

**Figura: Remitente de un mensaje enviado por el usuario, antes y después**

```text
Antes:    "from": {"name": "Ana Pérez", "address": ""}
Después:  "from": {"name": "Ana Pérez", "address": "ana@acme.example"}
```

### Diseño en el driver de Outlook

- **Columna nueva.** `PR_SENDER_ENTRYID` (`0x0C190102`) se añade a las columnas de la tabla de items y a las propiedades que se leen de un item abierto. En la captura, la tabla la devuelve como binario.
- **Lista blanca COM.** Se añaden `Account.CurrentUser` (devuelve un `Recipient`), `Recipient.EntryID` (escalar) y `NameSpace.CompareEntryIDs` (escalar). `AddressEntry`, `GetExchangeUser` y el resto de la libreta de direcciones siguen fuera.
- **Identidades.** El driver lee `(EntryID del usuario, Account.SmtpAddress)` de cada cuenta Exchange del perfil una sola vez por comando, y solo cuando un remitente o destinatario sin dirección necesita la regla 2.
- **Memoria por comando.** El resultado de la regla 2 se recuerda por EntryID durante el comando, así que cada EntryID distinto se compara una vez con cada identidad. Nada se guarda en disco.
- **Errores.** Un error de COM al leer una identidad o al comparar un EntryID cuenta como "sin coincidencia" para ese par; el timeout de RF-31 sigue aplicando a cada llamada.

### Elementos del PRD que cambian

- **§11.3, fila `from` / `to` / `cc`.** En Outlook, la dirección es la SMTP que trae el item; si no la trae y su EntryID es el del usuario de una cuenta Exchange del perfil, la dirección de esa cuenta; si no, `""` conservando `name`. Nunca una dirección interna de Exchange ni una búsqueda en la libreta de direcciones.
- **§22.4.** Fila nueva al final de la tabla "Cambios visibles de 3.0.0 solo en Windows".
- **§23.** Riesgo nuevo, después de "Object Model Guard muestra un aviso y bloquea al harness": la dirección vacía de un remitente o destinatario interno que no es el usuario.

### Cambios visibles

En la tabla "Cambios visibles de 3.0.0 solo en Windows": `from`, `to` y `cc` de un remitente o destinatario de Exchange que es el usuario de una cuenta y cuyo item no trae su dirección SMTP. Antes, `address: ""`; después, la dirección de esa cuenta.

### Riesgos

- **Direcciones vacías de otras personas.** Un remitente o destinatario interno que no es el usuario y cuyo item no trae su dirección SMTP sigue con `address: ""`. Probabilidad baja: en la captura no hubo ninguno. Impacto bajo: `name` se conserva y `--from` lo encuentra por el nombre.
- **Aviso de seguridad.** Leer `Account.CurrentUser` es una lectura de direcciones que el Object Model Guard puede vigilar. La mitigación es la del riesgo existente: el chequeo `object_model_guard` de `doctor` y el timeout de RF-31.

## Criterios de aceptación

- Con el doble de Outlook, un item de Enviados con remitente de tipo `EX`, sin `PR_SENDER_SMTP_ADDRESS` y con `PR_SENDER_ENTRYID` igual al del usuario de la cuenta A da `from.address` igual a la dirección de A, con el `name` del item, en `search`, `new` y `show`.
- El mismo item en otra carpeta de A, en un PST y en el store de otra cuenta B da la dirección de A.
- Un item con `PR_SENDER_SMTP_ADDRESS` distinta de la dirección de la cuenta conserva la del item.
- Un remitente `EX` sin dirección SMTP cuyo EntryID no es el de ningún usuario de cuenta da `address: ""` y conserva `name`; la salida no contiene la dirección interna de Exchange.
- Un destinatario `to` o `cc` de tipo `EX`, sin `PR_SMTP_ADDRESS` y con `EntryID` igual al del usuario de una cuenta da la dirección de esa cuenta; uno sin coincidencia da `""`.
- `search --from <dirección de A>` devuelve los items completados por la regla 2, y `--group-by domain` los cuenta en el dominio de A.
- Una cuenta cuya `CurrentUser` falla no completa direcciones; el comando termina con exit 0 y sin warnings nuevos.
- Un comando que no necesita la regla 2 no lee ninguna identidad, y cada EntryID distinto se compara como mucho una vez con cada identidad por comando.
- El proxy de solo lectura acepta `Account.CurrentUser`, `Recipient.EntryID` y `NameSpace.CompareEntryIDs`, y sigue rechazando con `E_INTERNAL` `AddressEntry`, `GetExchangeUser` y cualquier otro miembro de la libreta de direcciones.
- La salida en macOS no cambia.
- La suite completa pasa.

## IDs

- Crea: —
- Elimina: —

## Dependencias

Ninguna

## Decisiones

- **¿Cómo se completa en Outlook la dirección de un remitente o destinatario de Exchange que el item no trae?** (2026-11-27) Solo cuando su EntryID es el del usuario de una cuenta Exchange del perfil, con la dirección de esa cuenta. No se busca a nadie en la libreta de direcciones y no se guarda ninguna caché en disco.
- **¿Qué dirección sale cuando el item trae una dirección del usuario distinta de la de la cuenta?** (2026-11-27) La del item.

## Glosario

Sin cambios

## Conciliación con el PRD

**Tabla: Conciliación con el PRD**

| ID | Contrato | Archivo | Ancla | Qué cambia | Estado |
|---|---|---|---|---|---|
| RC-01 | Dirección de `from`, `to` y `cc` en Outlook | `11-modelo-de-datos.md` | `` `from` / `to` / `cc` `` | La celda de Outlook dice: la dirección SMTP que trae el item; si no la trae y su EntryID es el del usuario de una cuenta Exchange del perfil, la dirección de esa cuenta; si no, `""` conservando `name`; nunca una dirección interna de Exchange ni una búsqueda en la libreta de direcciones. | pendiente |
| RC-02 | Cambios visibles en Windows | `22-versiones.md` | `**Tabla: Cambios visibles de 3.0.0 solo en Windows**` | Fila nueva al final: `from`, `to` y `cc` del usuario de una cuenta Exchange cuyo item no trae su dirección SMTP; antes `address: ""`, después la dirección de la cuenta. | pendiente |
| RC-03 | Riesgo de direcciones vacías | `23-riesgos.md` | después de `**Object Model Guard muestra un aviso y bloquea al harness**` | Fila nueva: un remitente o destinatario interno que no es el usuario y cuyo item no trae su dirección SMTP sale con `address: ""`; probabilidad baja, impacto bajo; mitigación: `name` se conserva, `--from` lo encuentra por el nombre y las direcciones del usuario se completan con la identidad de su cuenta (§11.3). | pendiente |

## Documentos consumidores

- README.md: sin cambio
- README.es.md: sin cambio
- skills/mailquery/SKILL.md: sin cambio
- docs/INTERFACES.md: sin cambio
- docs/tests/outlook-data.md: pendiente
- docs/tests/outlook-runtime.md: pendiente

## Checklist de conciliación

**Tabla: Checklist de conciliación**

| ID | Ítem | Cómo se verifica | Estado |
|---|---|---|---|
| CL-01 | Cada fila de "Conciliación con el PRD" está aplicada en su archivo | Revisión fila por fila | pendiente |
| CL-02 | El resto del PRD no cambia | Diff del PRD limitado a los archivos de la tabla, el glosario, el Anexo D, la portada y el historial | pendiente |
| CL-03 | Los IDs de la unidad están creados y eliminados en el PRD, sin huecos ni referencias rotas | `doc_14` | no aplica |
| CL-04 | Las decisiones están en el Anexo D y el glosario está aplicado | Revisión de "Decisiones" y "Glosario" | pendiente |
| CL-05 | Los documentos consumidores están actualizados | Ninguno está `pendiente` | pendiente |
| CL-06 | No quedan textos obsoletos en el PRD ni en los documentos consumidores: `Nunca se consulta la libreta de direcciones`; en `docs/tests/outlook-data.md`, `Sin dirección SMTP ⇒ ` sin la condición de que no sea el usuario de una cuenta | Búsqueda de cada texto | pendiente |
| CL-07 | El defecto registrado está cerrado | Su entrada de `docs/KNOWN-DEFECTS.md` | no aplica |
| CL-08 | La versión del documento, el historial y los próximos IDs libres están al día | Portada e `HISTORIAL.md` | pendiente |
| CL-09 | La suite pasa | Suite completa, con `doc_14` y `doc_15` | pendiente |

## Desviaciones aprobadas

Ninguna

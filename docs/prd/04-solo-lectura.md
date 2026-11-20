---
aliases: ["Sección 4", "Garantía de solo lectura"]
tags: [prd]
---

## 4. Garantía de solo lectura (requisito de primer nivel)

> **Invariante I-1 (núcleo y backends internos):** el núcleo de `mailquery` y los backends internos (`apple_mail`, `outlook`) nunca modifican el store del cliente ni el estado de ningún mensaje, no lanzan el cliente, no abren conexiones de red y no provocan descargas desde el servidor. Solo escriben dentro de `~/.mailquery` (incluida `~/.mailquery/attachments/` y `~/.mailquery/tmp/`); el repositorio no se modifica en ejecución. Excepción en Windows: leer propiedades de nivel store (etiqueta, tipo, ruta, identificador) de cualquier store del perfil está permitido, aunque para resolverlas Outlook pueda consultar al servidor; las carpetas e items solo se leen en los stores locales (§15.7).

Concreción por plataforma:

- **macOS:** no escribe, renombra, mueve, trunca, toca fechas ni borra ningún archivo dentro de `~/Library/Mail`; no lanza Mail.app; no ejecuta AppleScript/osascript sobre Mail; no abre conexiones IMAP/SMTP. Además del store de Mail, la única base que lee es `~/Library/Accounts/Accounts4.sqlite`, para las etiquetas de cuenta. Leer un mensaje no cambia su estado de lectura. Mail no necesita estar abierto.
- **Windows:** no modifica ningún item, carpeta ni store de Outlook; no lanza Outlook; no provoca descargas desde el servidor. Un item con solo cabeceras en local se reporta sin cuerpo (`W_BODY_NOT_LOCAL`) y nunca se pide su descarga. De un mensaje S/MIME no se leen cuerpo ni adjuntos (podrían pedir PIN o certificado). Leer un item no lo marca como leído. Excepción para adjuntos: el proxy de solo lectura autoriza una operación adicional de materialización (`Attachment.SaveAsFile`; `GetTemporaryFilePath` no se autoriza) que traslada los bytes de un adjunto **ya descargado** al staging temporal `~/.mailquery/tmp/`; el resto de la lista blanca no cambia (§9.3, §23.1).

Plugins externos y adjuntos:

1. **Plugins externos.** Son paquetes de terceros instalados explícitamente por el usuario (`pipx inject mailquery <paquete>`); instalar el plugin es el consentimiento. El núcleo no los sandboxea ni puede verificar su comportamiento: cada plugin declara en su metadata de capacidades si usa red (`network`), si su solo-lectura es estructural o una promesa (`readonly`) y si sus cuerpos son locales (`body_local`). `doctor` muestra esas capacidades (§12.8).
2. **Adjuntos.** La extracción de adjuntos de un store local no modifica el buzón y no dispara descargas. Un driver con `attachments: "remote"` obtiene los nombres y los bytes desde su origen con su propia red, y `attachment` los procesa con el mismo motor que los de un driver `"local"`; el núcleo no abre red (RF-48). Un driver con `attachments: "none"` no soporta `mailquery attachment` (§12.11).
3. **Nada de esto habilita escritura en el correo, envío ni modificación de flags.** Las reglas de §4 y §21.1 sobre contenido no confiable siguen vigentes, y se amplían a los archivos extraídos: el harness los trata como datos no confiables y no los ejecuta.
4. **Logs y JSON no se contaminan con datos del plugin** más allá de lo permitido en §12.6/§14.

Cómo lo garantiza cada backend: §9.3. `doctor` lo reporta en `readonly_strategy` (§12.8). Criterios de aceptación: §20.

Reglas comunes a ambos backends:

1. Solo se leen identificadores y nombres visibles de cuentas; **nunca** credenciales, contraseñas ni tokens.
2. Ningún módulo fuera del backend accede al almacén del cliente: el resto del código solo ve el modelo común (§11.1).

---


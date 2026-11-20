---
aliases: ["Sección 2", "Problema y contexto"]
tags: [prd]
---

## 2. Problema y contexto

El usuario usa un cliente de correo de escritorio (Apple Mail en macOS; Outlook clásico en Windows) y quiere que un agente (el harness de DeepSeek u otro similar) pueda:

1. Detectar y leer los correos **nuevos** de sus bandejas cuando el harness lo necesite (bajo demanda).
2. Buscar correos existentes por asunto, contenido, remitentes, destinatarios, fechas, carpeta y estado.
3. Hacerlo **sin alterar el estado** de los correos: leído/no leído, flags y organización deben quedar exactamente igual.
4. Usar **la misma herramienta y el mismo contrato** en los dos sistemas, para que las recetas del harness no dependan de la plataforma.

Las alternativas genéricas son frágiles o inseguras:

- Automatización de la UI del cliente (AppleScript en macOS, macros/VBA en Outlook): expone propiedades escribibles, exige el cliente abierto y no garantiza no mutar.
- IMAP / Microsoft Graph / EWS: duplicarían credenciales, red y superficie de escritura.
- Un índice propio de mensajes: duplicaría correo privado y añadiría sincronización, invalidación y desincronización.

Las alternativas descartadas para cada cliente están en ADR-01 y ADR-11 (detalle en el Anexo C).

Con plugins de backend y adjuntos (3.0.0) se añaden estas necesidades:

1. **Múltiples orígenes de correo:** el usuario consulta cuentas en distintos clientes o conectores (Apple Mail, Outlook clásico, futuros plugins) manteniendo el núcleo libre de dependencias de red y un único contrato JSON.
2. **Inspección de adjuntos por el agente:** `show <uid>` lista nombres, pero el agente necesita el archivo en disco para leer su contenido (PDFs, facturas). Un mismo correo puede traer varios adjuntos con el mismo nombre; se requieren `index` posicional determinista (1..N) y una caché reutilizable.
3. **Entrada no confiable:** el nombre del adjunto viene del remitente; puede contener *Path Traversal*, caracteres de control/inversión Unicode, nombres reservados de Windows, extensiones ejecutables dobles o contenido ejecutable camuflado.
4. **Contrato estable para el harness:** los códigos de error y exit son la interfaz de decisión del agente; los plugins externos no pueden introducir códigos ni exit arbitrarios.

Con el endurecimiento del contenido (F1), la corrección de defectos (F2) y la salida a medida (F3), 3.0.0 cubre estas necesidades:

1. **Contenido sin canales ocultos (F1):** el texto que llega al harness no debe esconder datos ni instrucciones con caracteres de control, `Cf` o invisibles en ningún campo de contenido (G-01, G-02, G-06), con elementos ocultos por HTML o CSS (G-03) ni con un texto plano alternativo distinto del HTML que ve el destinatario (G-05) ([revisión de seguridad](../security/threat-model.md)).
2. **Señales para el harness (F1):** URLs que el harness podría abrir (G-04), suplantación del remitente (T-10) y contenido activo de adjuntos (G-07, T-07).
3. **Adjuntos de conectores remotos (F2):** `attachment` debe extraer los adjuntos de un plugin `attachments: "remote"` (BUG-01; RF-41, RF-44, ADR-22) con un tope por adjunto que un plugin colgado en la red no pueda esquivar y que el usuario ajuste a su red.
4. **Salida proporcional a la pregunta (F3):** elegir qué mensaje abrir no debe exigir leer ni entregar cuerpos, que cuestan tokens y meten texto del remitente en el contexto del LLM; "las últimas facturas de cada proveedor" o "cuántos no leídos tengo" deben responderse en una llamada, sin el límite de 200 filas (RF-14).
5. **Diagnóstico tras un fallo (F3):** `doctor` debe mostrar solo lo que falla e incluir los plugins mal configurados; el harness no debe ejecutar `doctor` y `mailboxes` en cada conversación, y un `search` con `count: 0` porque el correo está en otra carpeta debe explicar el alcance buscado.
6. **`mailboxes` para elegir carpetas (F3):** ver qué carpetas existen para `--include-mailbox` y `mailbox_list` sin repetir la cuenta en cada carpeta ni recontar todos los mensajes (`PERFORMANCE-BACKLOG.md`).

Las razones de cada decisión, con sus mediciones, están en ADR-29–ADR-49.

---


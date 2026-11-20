---
aliases: ["Anexo A", "Resumen del spike de Outlook"]
tags: [prd]
---

### Anexo A — Resumen del spike de Outlook (2026-11-03)

Ejecutado con un script de solo lectura fuera del repositorio en el host de
referencia: Windows 11 x64, Outlook clásico (Microsoft 365 Apps) 16.0 x64, dos
cuentas Exchange en caché más un buzón compartido y carpetas públicas; sin
PST, IMAP ni EAS. Contadores de no leídos idénticos antes y después.

**Confirmado (y decisión que fijó):**

- **P-9** El identificador de las vistas de metadatos de Outlook es de sesión,
  no permanente ⇒ el `uid` es siempre el `EntryID` permanente (§11.3).
- **P-5** Una de las vías de lectura entrega la hora de recepción mal
  etiquetada ⇒ las fechas se leen en UTC (§11.3).
- **P-7** Los filtros de fecha de Outlook no respetan los segundos ⇒ el corte
  exacto de `--since`/`--until` lo hace `mailquery` (§11.3).
- **P-8** Las carpetas internas se identifican por función ⇒ se ocultan sin
  depender del idioma (§15.7).
- **P-6** ~5 ms por item para abrirlo y leer su cuerpo (p95 ~6 ms) y ~350 ms
  para los metadatos de una carpeta de 240 items ⇒ presupuestos de §19
  (`doctor` y `mailboxes` no se midieron).
- **P-3 / P-11** Leer 239 cuerpos no cambió los no leídos ni mostró avisos (sin
  directivas, dos antivirus activos) ⇒ criterio de `object_model_guard` (§12.8). `pywin32` puede dejar
  una caché fuera del home ⇒ la caché se confina a `~/.mailquery` (§9.3).
- **P-1** Abrir un item por `EntryID` funciona en stores no predeterminados
  (239/239); con PST no probado.
- **P-4** `pywin32` funciona en un entorno aislado como el de `pipx`, sin pasos
  de post-instalación (ADR-14).

**No probado** (riesgo residual): **P-2** el estado de descarga en modo solo
cabeceras, IMAP y EAS; **P-3** el caso "sin antivirus"; **P-10** abortar una
llamada a Outlook bloqueada; **P-12** la marca de borrado IMAP; **P-13** PST
local y en red.

**Prueba A2** (2026-11-03, solo lectura; contadores de no leídos idénticos
antes y después):

- En los dos stores locales, el `EntryID` de cada item contiene el
  `PR_RECORD_KEY` de su store, único por store.
- El `PR_RECORD_KEY` se lee en los 4 stores del perfil, incluidos el buzón
  compartido y las carpetas públicas (excluidos), sin abrir sus items ⇒
  `account.uuid` y regla de `show` de §12.4.
- No se pudo comprobar con items de un store excluido, porque leerlos violaría
  I-1; si en algún caso no coincide, el resultado es "not found", nunca un
  error incorrecto de alcance (§12.4).
- Con Outlook desconectado del servidor, enumerar los stores falló ⇒ un store
  ilegible se reporta como `unavailable` (§15.7).


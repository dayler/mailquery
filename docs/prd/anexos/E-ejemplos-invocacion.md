---
aliases: ["Anexo E", "Ejemplos de invocación"]
tags: [prd]
---

### Anexo E — Ejemplos de invocación

```bash
# Ayuda y diagnóstico (search/new necesitan al menos una cuenta declarada en ~/.mailquery/config.toml)
mailquery --help
mailquery search --help
mailquery doctor
mailquery mailboxes

# Correo nuevo (procesar una vez)
mailquery new
mailquery new --peek
mailquery new --limit 200

# Búsquedas por fecha relativa (última semana / mes / etc.)
mailquery search --since 1w
mailquery search --since 2w --unread
mailquery search --since 1mo --has-attachments
mailquery search --since 2mo --from "*@banco.com*"

# Búsquedas por asunto/contenido con comodines
mailquery search --subject "*factura*" --since 2w
mailquery search --text "*reserva confirmada*" --since 1w

# Incluir carpetas fuera de la configuración en una sola ejecución
mailquery search --include-mailbox "Archivo,Facturas" --since 1mo

# Detalle de un mensaje (uid tomado de search/new)
mailquery show apple_mail:83143       # macOS (uid legado también aceptado: mailquery show 83143)
mailquery show outlook:k3f9q2m7xa   # Windows (uid legado: mailquery show k3f9q2m7xa)

# Recuperar adjuntos locales a la caché
mailquery attachment apple_mail:83143 --index 2
mailquery attachment apple_mail:83143 --all
mailquery attachment apple_mail:83143 --index 2 --force
```


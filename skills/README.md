# Skill para harnesses de IA (`skills/`)

`mailquery` incluye un *skill* listo para que lo use un harness de IA (DeepSeek Harness o
Claude Code): [`skills/mailquery/SKILL.md`](mailquery/SKILL.md) describe el CLI, el
contrato JSON y las reglas de uso (solo lectura, cuerpos no confiables). El skill **no**
forma parte del paquete Python ni del código fuente: solo lo consumen los harnesses.

## Instalación

Desde la raíz del repositorio:

```bash
# macOS / Linux
./skills/install.sh

# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File skills\install.ps1
```

Sin argumentos el script detecta los harnesses instalados y muestra un menú:

- cada harness detectado (DeepSeek Harness, Claude Code);
- ruta personalizada (copia a `<ruta>/mailquery/SKILL.md`);
- instalar en todos los detectados.

Para automatizar o evitar el menú:

```bash
./skills/install.sh --harness dsh --scope project
./skills/install.sh --all
./skills/install.sh --path ~/.config/otro-harness/skills
./skills/install.sh --dry-run
./skills/install.sh --force          # sobrescribe un SKILL.md con contenido distinto
```

En PowerShell los equivalentes son `-Harness dsh|claude|all`, `-Scope`, `-Path`,
`-DryRun` y `-Force`.

## Dónde instala

| Harness | Usuario (por defecto) | Proyecto (`--scope project`) |
|---------|------------------------|------------------------------|
| DeepSeek Harness | `${DSH_HOME:-~/.dsh}/skills/mailquery/SKILL.md` | `./.dsh/skills/mailquery/SKILL.md` |
| Claude Code | `${CLAUDE_CONFIG_DIR:-~/.claude}/skills/mailquery/SKILL.md` | `./.claude/skills/mailquery/SKILL.md` |

DSH también descubre skills en `./.agents/skills` y `~/.agents/skills` (útil para
compartirlos entre harnesses); Claude Code solo lee `~/.claude/skills` y
`.claude/skills`.

## Detección

- **DeepSeek Harness:** existe `$DSH_HOME` (o `~/.dsh`), o `dsh` está en `PATH`.
- **Claude Code:** existe `$CLAUDE_CONFIG_DIR` (o `~/.claude`), o `claude` está en `PATH`.
- Si no detecta ninguno, el menú solo ofrece ruta personalizada y `--all` falla con
  instrucciones.

## Requisitos para que el skill funcione

- `mailquery` instalado y en `PATH` (`pipx install .` desde la raíz; ver el README
  principal).
- macOS: Acceso total al disco para la app que ejecuta el harness.
- Windows: Outlook clásico abierto con el mismo usuario; si no,
  `E_OUTLOOK_NOT_RUNNING` (exit 6).
- Al menos una cuenta declarada en `~/.mailquery/config.toml`
  (`%USERPROFILE%\.mailquery\config.toml` en Windows).

## Verificación

Reinicia la sesión del harness para que descubra el skill y ejecuta `mailquery doctor` y
`mailquery mailboxes`. En Claude Code se puede invocar con `/mailquery`; en DSH aparece en
el catálogo de skills.

## Mantenimiento

`skills/mailquery/SKILL.md` es la fuente de verdad: edítalo, vuelve a correr el instalador
(`--force` si el destino ya existía) y reinicia la sesión. La copia instalada no se
commitea: `.dsh/` está en `.gitignore`.

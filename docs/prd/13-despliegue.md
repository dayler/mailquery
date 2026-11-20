---
aliases: ["Sección 13", "Despliegue e instalación"]
tags: [prd]
---

## 13. Despliegue e instalación

### 13.1 Requisitos

**Tabla: Requisitos de instalación por plataforma**

| Requisito | macOS | Windows |
|-----------|-------|---------|
| Sistema | macOS con Apple Mail (store `V9`/`V10`/`V11`; `V10` validada) | Windows 10/11 x64 |
| Cliente | Apple Mail; no necesita estar abierto | Outlook **clásico** 16.0 (x86 o x64), en ejecución y con un perfil cargado; cuentas Exchange en modo caché y las demás con su archivo de datos en un disco local (§15.7) |
| Python | ≥ 3.11 (el intérprete que use `pipx`) | ≥ 3.11 (el intérprete que use `pipx`) |
| `pipx` | Instalado (instrucciones en el README) | Instalado (instrucciones en el README) |
| Dependencias de runtime | `css-inline` `~=0.23.1` (ADR-33; la instala `pipx`) | `css-inline` `~=0.23.1` (ADR-33) y `pywin32` (ADR-14); las instala `pipx` |
| Permisos | **Acceso total al disco (FDA)** para la app que ejecuta la CLI (§16.1) | Misma sesión interactiva y mismo nivel de integridad que Outlook: un proceso elevado o un servicio de Windows no ve el Outlook del usuario y obtiene `E_OUTLOOK_NOT_RUNNING`; Object Model Guard sin avisos (§12.8) |

### 13.2 Instalación

Se instala con `pipx install .` desde la raíz del repositorio en ambas plataformas (ADR-08); el paquete registra los backends internos en el grupo de entry points `mailquery.backends` y un plugin externo se añade al mismo entorno con `pipx inject mailquery <paquete>` (RF-33); cualquier comando crea `~/.mailquery` y sus subdirectorios si no existen (los instaladores ya lo crean al sembrar `config.toml`); `mailquery doctor` valida el entorno. Los instaladores `scripts/install.sh` (macOS/Linux) y `scripts/install.ps1` / `install.bat` (Windows) automatizan `pipx` y siembran `config.toml` desde `docs/config.example.toml` si no existe.

Al terminar, `install.ps1` comprueba que `pywin32` quedó instalado y que `mailquery -v` muestra `backend outlook`; si la comprobación falla, muestra el problema con el hint `pipx reinstall mailquery` y termina con un código distinto de 0.

Después de instalar, declara al menos una cuenta en `~/.mailquery/config.toml` (§15).

### 13.3 Actualización y desinstalación

Se actualiza con `pipx reinstall mailquery` tras actualizar el repositorio y se desinstala con `pipx uninstall mailquery`. Desinstalar no borra `~/.mailquery` (estado, logs, caché de adjuntos y configuración); el usuario puede borrarlo a mano o con `scripts/install.sh --uninstall --purge` (macOS/Linux) o `scripts\install.ps1 -Uninstall -Purge` (Windows).

Actualizar un plugin dentro de la API 1 no cambia `config.toml`, `state.json` ni la caché. Desinstalarlo deja sus bloques `[scope]` en `E_DRIVER_UNKNOWN` y su cursor en `E_STATE_CORRUPT`; el anillo se poda y la caché se conserva (§11.2).

**Actualización de seguridad de `css-inline`** (contenido de los README, RF-65). Ante un aviso de seguridad de `css-inline`, el usuario sigue estos pasos. La fuente de los avisos es la página de avisos del repositorio (<https://github.com/Stranger6667/css-inline/security/advisories>), y la versión que corrige cada uno, la sección "Security" del changelog (<https://github.com/Stranger6667/css-inline/blob/master/CHANGELOG.md>): un aviso del repositorio puede no aparecer en PyPI ni en las bases de vulnerabilidades que consulta `pip-audit`, y puede no indicar la versión corregida.

1. **Ver la versión instalada** (línea `Version:`):

   ```bash
   pipx runpip mailquery show css-inline
   ```

2. **Comparar** esa versión con las versiones afectadas y la corregida que indica el aviso. Si la instalada no está afectada, no hay que hacer nada.
3. **Si la corrección es un parche dentro del rango de `mailquery`** (`0.23.x`), instalarlo sin reinstalar `mailquery` y comprobar:

   ```bash
   pipx runpip mailquery install --upgrade "css-inline~=0.23.1"
   pipx runpip mailquery show css-inline
   mailquery show <uid>    # comprobar con un mensaje HTML
   ```

   `pipx reinstall mailquery` también instala el último parche permitido.
4. **Si la corrección solo existe en una versión menor posterior** (`0.24` o más), actualizar `mailquery` cuando una versión amplíe el rango (`git pull` y después `pipx reinstall mailquery`). Si el aviso es crítico y no se puede esperar, se puede forzar la versión corregida, sabiendo que esa combinación no está probada y que `pip` mostrará un aviso de conflicto de dependencias:

   ```bash
   pipx runpip mailquery install "css-inline==<versión corregida>"
   mailquery show <uid>    # comprobar con un mensaje HTML
   ```

   Si `css-inline` falla, `mailquery` sigue funcionando: convierte el HTML sin pasar las hojas `<style>` a línea (RF-53), así que solo se pierde la omisión del texto oculto por hojas de estilo. La próxima `pipx reinstall mailquery` vuelve a una versión dentro del rango.
5. **Volver atrás** si una versión nueva da problemas:

   ```bash
   pipx runpip mailquery install "css-inline==<versión anterior>"
   ```

### 13.4 Notas de permisos

Permisos: §13.1 y §16.1. En ambos casos, verificar con `mailquery doctor` tras actualizar el intérprete, el sistema o el cliente.

---


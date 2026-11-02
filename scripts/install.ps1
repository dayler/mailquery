<#
.SYNOPSIS
    Instala o reinstala el comando mailquery con pipx y siembra la configuración inicial.

.DESCRIPTION
    Copia docs/config.example.toml a ~/.mailquery/config.toml si ese archivo no
    existe todavía (nunca lo sobrescribe sin -ForceConfig, que antes guarda un
    backup). La aplicación nunca crea ni modifica su configuración.

    Requisitos: Python >= 3.11 y pipx (este script lo instala si falta).

    AVISO: mailquery solo opera en macOS con Apple Mail. En Windows este script
    prepara el entorno (pipx + paquete) para desarrollo/CI, pero los comandos de
    datos no funcionan porque no hay Apple Mail ni librería fcntl.

.PARAMETER DryRun
    Imprime el plan sin ejecutar ni escribir nada.

.PARAMETER PrintConfig
    Imprime la plantilla de configuración y termina.

.PARAMETER NoConfig
    No crea ~/.mailquery/config.toml.

.PARAMETER ForceConfig
    Sobrescribe config.toml (antes guarda un backup con timestamp).

.PARAMETER Python
    Intérprete de Python para pipx (p. ej. python3.14).

.PARAMETER FromGit
    Instala desde https://github.com/dayler/mailquery.git.

.PARAMETER Uninstall
    Desinstala mailquery con pipx.

.PARAMETER Purge
    Con -Uninstall, borra también ~/.mailquery.

.EXAMPLE
    .\scripts\install.ps1 -DryRun

.EXAMPLE
    .\scripts\install.ps1 -NoConfig -FromGit

.EXAMPLE
    .\scripts\install.ps1 -Uninstall -Purge
#>
[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$PrintConfig,
    [switch]$NoConfig,
    [switch]$ForceConfig,
    [string]$Python = "",
    [switch]$FromGit,
    [switch]$Uninstall,
    [switch]$Purge
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$TemplateFile = Join-Path (Join-Path $RepoRoot "docs") "config.example.toml"
$GitSpec = "git+https://github.com/dayler/mailquery.git"
$ConfigDir = Join-Path $HOME ".mailquery"
$ConfigFile = Join-Path $ConfigDir "config.toml"
$IsWindowsHost = ($env:OS -eq "Windows_NT")
$script:PythonExe = if ($Python) { $Python } elseif (Get-Command py -ErrorAction SilentlyContinue) { "py" } else { "python" }
$ConfigCreated = $false

function Write-Log {
    param([string]$Message)
    Write-Host $Message
}

function Write-Fail {
    param([string]$Message)
    Write-Host "error: $Message" -ForegroundColor Red
    exit 1
}

function Invoke-Step {
    param([string]$Display, [scriptblock]$Action)
    Write-Verbose "running: $Display"
    & $Action
}

function Invoke-Pipx {
    param([string[]]$Arguments)
    $display = "pipx " + ($Arguments -join " ")
    Invoke-Step -Display $display -Action {
        if (Get-Command pipx -ErrorAction SilentlyContinue) {
            & pipx @Arguments
        } else {
            & $script:PythonExe -m pipx @Arguments
        }
    }
}

function Test-MailqueryInstalled {
    try {
        if (Get-Command pipx -ErrorAction SilentlyContinue) {
            $output = & pipx list 2>$null
        } else {
            $output = & $script:PythonExe -m pipx list 2>$null
        }
    } catch {
        return $false
    }
    return (($output -join "`n") -match "package mailquery ")
}

if ($Purge -and -not $Uninstall) {
    Write-Host "error: -Purge requiere -Uninstall"
    exit 2
}
if ($ForceConfig -and $NoConfig) {
    Write-Host "error: -ForceConfig no se combina con -NoConfig"
    exit 2
}

if ($PrintConfig) {
    if (-not (Test-Path -LiteralPath $TemplateFile)) {
        Write-Fail "no existe la plantilla: $TemplateFile"
    }
    Get-Content -LiteralPath $TemplateFile -Raw
    exit 0
}

if ($DryRun) {
    Write-Log "Plan de despliegue (dry-run; no se ejecuta nada):"
    if ($Uninstall) {
        Write-Log "  1. pipx uninstall mailquery (si está instalado)"
        if ($Purge) {
            Write-Log "  2. Remove-Item -Recurse -Force $ConfigDir"
        }
        exit 0
    }
    Write-Log "  1. comprobar pipx (instalarlo si falta) y 'pipx ensurepath'"
    if ($FromGit) {
        Write-Log "  2. pipx install/reinstall con $GitSpec"
    } else {
        Write-Log "  2. pipx install/reinstall desde $RepoRoot"
    }
    if ($Python) {
        Write-Log "     intérprete: $Python"
    }
    Write-Log "  3. verificar 'mailquery' en PATH y ejecutar 'mailquery doctor' (solo macOS)"
    if ($NoConfig) {
        Write-Log "  4. config: omitida (-NoConfig)"
    } elseif ((Test-Path -LiteralPath $ConfigFile) -and -not $ForceConfig) {
        Write-Log "  4. config: ya existe $ConfigFile (no se sobrescribe)"
    } elseif (Test-Path -LiteralPath $ConfigFile) {
        Write-Log "  4. config: backup de $ConfigFile y copia de la plantilla"
    } else {
        Write-Log "  4. config: crear $ConfigFile desde la plantilla (0600 equivalente)"
    }
    Write-Log "  5. imprimir los siguientes pasos"
    exit 0
}

if ($IsWindowsHost) {
    Write-Log "aviso: mailquery solo opera en macOS con Apple Mail; en Windows la instalación sirve para desarrollo/CI."
}

if ($Uninstall) {
    if (Test-MailqueryInstalled) {
        Invoke-Pipx @("uninstall", "mailquery")
    } else {
        Write-Log "mailquery no está instalado con pipx; nada que desinstalar."
    }
    if ($Purge) {
        if (Test-Path -LiteralPath $ConfigDir) {
            Remove-Item -LiteralPath $ConfigDir -Recurse -Force
            Write-Log "borrado $ConfigDir (-Purge)"
        }
    }
    Write-Log "Desinstalación completada."
    exit 0
}

if (-not (Get-Command pipx -ErrorAction SilentlyContinue)) {
    Write-Log "pipx no encontrado; instalándolo..."
    Invoke-Step -Display "$($script:PythonExe) -m pip install --user pipx" -Action {
        & $script:PythonExe -m pip install --user pipx
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "no se pudo instalar pipx"
    }
    Invoke-Step -Display "$($script:PythonExe) -m pipx ensurepath" -Action {
        & $script:PythonExe -m pipx ensurepath | Out-Null
    }
} else {
    Invoke-Step -Display "pipx ensurepath" -Action { & pipx ensurepath | Out-Null }
}

$spec = if ($FromGit) { $GitSpec } else { $RepoRoot }
if (Test-MailqueryInstalled) {
    if ($Python) {
        Invoke-Pipx @("reinstall", "--python", $Python, "mailquery")
    } else {
        Invoke-Pipx @("reinstall", "mailquery")
    }
} else {
    if ($Python) {
        Invoke-Pipx @("install", "--python", $Python, $spec)
    } else {
        Invoke-Pipx @("install", $spec)
    }
}
if ($LASTEXITCODE -ne 0) {
    Write-Fail "pipx falló; revisa la salida anterior"
}

$mailquery = Get-Command mailquery -ErrorAction SilentlyContinue
if (-not $mailquery) {
    Write-Fail "mailquery no está en PATH; abre una terminal nueva (pipx ensurepath) y reejecuta"
}
Write-Log "mailquery: $($mailquery.Source)"

if ($IsWindowsHost) {
    Write-Log "aviso: se omite 'mailquery --help' (la app depende de macOS/Apple Mail)"
} else {
    Invoke-Step -Display "mailquery --help" -Action { & mailquery --help | Out-Null }
}

if ($NoConfig) {
    Write-Log "config: omitida (-NoConfig)"
} else {
    if (-not (Test-Path -LiteralPath $TemplateFile)) {
        Write-Fail "no existe la plantilla: $TemplateFile"
    }
    if ((Test-Path -LiteralPath $ConfigFile) -and -not $ForceConfig) {
        Write-Log "config: ya existe $ConfigFile (no se sobrescribe; usa -ForceConfig)"
    } else {
        if (Test-Path -LiteralPath $ConfigFile) {
            $backup = "$ConfigFile.bak-" + (Get-Date -Format "yyyyMMddHHmmss")
            Copy-Item -LiteralPath $ConfigFile -Destination $backup -Force
            Write-Log "config: backup en $backup"
        }
        New-Item -ItemType Directory -Path $ConfigDir -Force | Out-Null
        Copy-Item -LiteralPath $TemplateFile -Destination $ConfigFile -Force
        try {
            $acl = Get-Acl -LiteralPath $ConfigFile
            $acl.SetAccessRuleProtection($true, $false)
            $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($env:USERNAME, "Read,Write", "Allow")
            $acl.SetAccessRule($rule)
            # Windows PowerShell 5.1 has no -LiteralPath on Set-Acl.
            Set-Acl -Path $ConfigFile -AclObject $acl
        } catch {
            Write-Log "aviso: no se pudo restringir la ACL de $ConfigFile"
        }
        $ConfigCreated = $true
        Write-Log "config: creada $ConfigFile desde la plantilla (edítala para declarar cuentas)"
    }
}

if (-not $IsWindowsHost) {
    Write-Log "ejecutando 'mailquery doctor' (preflight)..."
    & mailquery doctor | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Log "aviso: 'mailquery doctor' reportó problemas; ejecútalo sin redirección para ver el detalle"
    }
} else {
    Write-Log "aviso: 'mailquery doctor' se omite fuera de macOS"
}

Write-Log ""
Write-Log "Despliegue completado."
if ($ConfigCreated) {
    Write-Log "  - Se creó ~/.mailquery/config.toml (todavía sin cuentas declaradas)."
}
Write-Log "  - Edita ~/.mailquery/config.toml y declara al menos una cuenta."
Write-Log "  - Verifica: mailquery doctor && mailquery mailboxes"
Write-Log "  - Consulta:  mailquery search --since 1w"

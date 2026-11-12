<#
.SYNOPSIS
    Install or reinstall the mailquery command with pipx and seed the initial configuration.

.DESCRIPTION
    Copy docs/config.example.toml to ~/.mailquery/config.toml when that file
    does not exist yet (never overwrite it without -ForceConfig, which keeps a
    timestamped backup first). The application never creates or modifies its
    configuration.

    Requirements: Python >= 3.11 and pipx (this script installs pipx when missing).

    Backend plugins are separate packages installed explicitly into the same pipx
    environment: 'pipx inject mailquery <plugin-package>'; installing the plugin is
    the consent and 'mailquery doctor' shows its capabilities. The configuration
    template documents the [attachments] block used by 'mailquery attachment'.

    On Windows mailquery reads Outlook (classic, 16.0) through COM: the package
    depends on pywin32, which pipx installs automatically. When the installation
    ends, the script checks that pywin32 can be imported from the pipx venv and
    that 'mailquery -v' reports 'backend outlook'; otherwise it prints the
    problem with the hint 'pipx reinstall mailquery' and exits with a non-zero code.

.PARAMETER DryRun
    Print the plan without executing or writing anything.

.PARAMETER PrintConfig
    Print the configuration template and exit.

.PARAMETER NoConfig
    Do not create ~/.mailquery/config.toml.

.PARAMETER ForceConfig
    Overwrite config.toml (a timestamped backup is kept first).

.PARAMETER Python
    Python interpreter for pipx (e.g. python3.14).

.PARAMETER FromGit
    Install from https://github.com/dayler/mailquery.git.

.PARAMETER Uninstall
    Uninstall mailquery with pipx.

.PARAMETER Purge
    With -Uninstall, also remove ~/.mailquery.

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

function Get-PipxVenvPython {
    # Interpreter of the venv pipx created for mailquery, or $null when unknown.
    try {
        if (Get-Command pipx -ErrorAction SilentlyContinue) {
            $venvs = (& pipx environment --value PIPX_LOCAL_VENVS 2>$null | Select-Object -First 1)
        } else {
            $venvs = (& $script:PythonExe -m pipx environment --value PIPX_LOCAL_VENVS 2>$null | Select-Object -First 1)
        }
    } catch {
        return $null
    }
    if (-not $venvs) { return $null }
    $venvPython = Join-Path (Join-Path (Join-Path "$venvs".Trim() "mailquery") "Scripts") "python.exe"
    if (Test-Path -LiteralPath $venvPython) { return $venvPython }
    return $null
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
    Write-Host "error: -Purge requires -Uninstall"
    exit 2
}
if ($ForceConfig -and $NoConfig) {
    Write-Host "error: -ForceConfig cannot be combined with -NoConfig"
    exit 2
}

if ($PrintConfig) {
    if (-not (Test-Path -LiteralPath $TemplateFile)) {
        Write-Fail "template not found: $TemplateFile"
    }
    Get-Content -LiteralPath $TemplateFile -Raw
    exit 0
}

if ($DryRun) {
    Write-Log "Deployment plan (dry-run; nothing will be executed):"
    if ($Uninstall) {
        Write-Log "  1. pipx uninstall mailquery (when installed)"
        if ($Purge) {
            Write-Log "  2. Remove-Item -Recurse -Force $ConfigDir"
        }
        exit 0
    }
    Write-Log "  1. check pipx (install it when missing) and run 'pipx ensurepath'"
    if ($FromGit) {
        Write-Log "  2. pipx install/reinstall from $GitSpec"
    } else {
        Write-Log "  2. pipx install/reinstall from $RepoRoot"
    }
    if ($Python) {
        Write-Log "     interpreter: $Python"
    }
    Write-Log "  3. verify 'mailquery' is in PATH and run 'mailquery --help' and 'mailquery doctor'"
    if ($NoConfig) {
        Write-Log "  4. config: skipped (-NoConfig)"
    } elseif ((Test-Path -LiteralPath $ConfigFile) -and -not $ForceConfig) {
        Write-Log "  4. config: $ConfigFile already exists (it will not be overwritten)"
    } elseif (Test-Path -LiteralPath $ConfigFile) {
        Write-Log "  4. config: back up $ConfigFile and copy the template"
    } else {
        Write-Log "  4. config: create $ConfigFile from the template (0600 equivalent)"
    }
    Write-Log "  5. final check: 'import win32com' in the pipx venv and 'mailquery -v' shows 'backend outlook'"
    Write-Log "  6. print next steps"
    exit 0
}

if ($Uninstall) {
    if (Test-MailqueryInstalled) {
        Invoke-Pipx @("uninstall", "mailquery")
    } else {
        Write-Log "mailquery is not installed with pipx; nothing to uninstall."
    }
    if ($Purge) {
        if (Test-Path -LiteralPath $ConfigDir) {
            Remove-Item -LiteralPath $ConfigDir -Recurse -Force
            Write-Log "removed $ConfigDir (-Purge)"
        }
    }
    Write-Log "Uninstall complete."
    exit 0
}

if (-not (Get-Command pipx -ErrorAction SilentlyContinue)) {
    Write-Log "pipx not found; installing it..."
    Invoke-Step -Display "$($script:PythonExe) -m pip install --user pipx" -Action {
        & $script:PythonExe -m pip install --user pipx
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "could not install pipx"
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
    Write-Fail "pipx failed; review the output above"
}

$mailquery = Get-Command mailquery -ErrorAction SilentlyContinue
if (-not $mailquery) {
    Write-Fail "mailquery is not in PATH; open a new terminal (pipx ensurepath) and retry"
}
Write-Log "mailquery: $($mailquery.Source)"

Invoke-Step -Display "mailquery --help" -Action { & mailquery --help | Out-Null }

if ($NoConfig) {
    Write-Log "config: skipped (-NoConfig)"
} else {
    if (-not (Test-Path -LiteralPath $TemplateFile)) {
        Write-Fail "template not found: $TemplateFile"
    }
    if ((Test-Path -LiteralPath $ConfigFile) -and -not $ForceConfig) {
        Write-Log "config: $ConfigFile already exists (not overwritten; use -ForceConfig)"
    } else {
        if (Test-Path -LiteralPath $ConfigFile) {
            $backup = "$ConfigFile.bak-" + (Get-Date -Format "yyyyMMddHHmmss")
            Copy-Item -LiteralPath $ConfigFile -Destination $backup -Force
            Write-Log "config: backup at $backup"
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
            Write-Log "warning: could not restrict the ACL of $ConfigFile"
        }
        $ConfigCreated = $true
        Write-Log "config: created $ConfigFile from the template (edit it to declare accounts)"
    }
}

Write-Log "running 'mailquery doctor' (preflight)..."
& mailquery doctor | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Log "warning: 'mailquery doctor' reported problems; run it without redirection to see the details"
}

if ($IsWindowsHost) {
    # Final check: pywin32 importable from the pipx venv and Outlook backend selected.
    $hint = "run: pipx reinstall mailquery"
    $venvPython = Get-PipxVenvPython
    if (-not $venvPython) {
        Write-Fail "could not locate the pipx venv of mailquery to check pywin32 ($hint)"
    }
    # Native stderr must not raise under $ErrorActionPreference = "Stop".
    $ErrorActionPreference = "Continue"
    $importOutput = & $venvPython -c "import win32com" 2>&1
    $importExit = $LASTEXITCODE
    if ($importExit -ne 0) {
        $ErrorActionPreference = "Stop"
        Write-Host ($importOutput | Out-String)
        Write-Fail "pywin32 (win32com) cannot be imported in the pipx venv ($hint)"
    }
    $versionOutput = (& mailquery -v 2>&1 | Out-String).Trim()
    $versionExit = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($versionExit -ne 0 -or $versionOutput -notmatch "backend outlook") {
        Write-Host $versionOutput
        Write-Fail "'mailquery -v' failed or does not show 'backend outlook' ($hint)"
    }
    Write-Log "check: win32com importable; $versionOutput"
}

Write-Log ""
Write-Log "Deployment complete."
if ($ConfigCreated) {
    Write-Log "  - Created ~/.mailquery/config.toml (no accounts declared yet)."
}
Write-Log "  - Edit ~/.mailquery/config.toml and declare at least one account."
Write-Log "  - Verify: mailquery doctor && mailquery mailboxes"
Write-Log "  - Query:  mailquery search --since 1w"
Write-Log "  - Plugins: pipx inject mailquery <plugin-package> (declared by their driver)"
Write-Log "  - Attachments: mailquery attachment <uid> --index 1 (see the [attachments] block)"

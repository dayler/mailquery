<#
.SYNOPSIS
Install the mailquery skill into a local AI harness (DeepSeek Harness or Claude Code).

.DESCRIPTION
Copies skills/mailquery/SKILL.md into the harness skill root. It never touches mail or
the user's ~/.mailquery directory. Run it from the repository root, for example:
  powershell -ExecutionPolicy Bypass -File skills\install.ps1
  powershell -ExecutionPolicy Bypass -File skills\install.ps1 -Harness dsh -Scope project

.PARAMETER Harness
dsh, claude or all. With the default (auto) the script detects installed harnesses and
shows a menu.

.PARAMETER Scope
user (default) installs under the user skill root; project installs under
./.dsh/skills or ./.claude/skills in the current directory.

.PARAMETER Path
Custom skills root; the skill is copied to <Path>\mailquery\SKILL.md.

.PARAMETER Force
Overwrite an existing SKILL.md with different content.

.PARAMETER DryRun
Print the targets without writing anything.

.EXAMPLE
powershell -ExecutionPolicy Bypass -File skills\install.ps1 -Harness all -DryRun
#>
[CmdletBinding()]
param(
    [ValidateSet('auto', 'dsh', 'claude', 'all')]
    [string]$Harness = 'auto',

    [ValidateSet('user', 'project')]
    [string]$Scope = 'user',

    [string]$Path,

    [switch]$Force,

    [switch]$DryRun,

    [switch]$Help
)

$ErrorActionPreference = 'Stop'

$SkillName = 'mailquery'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillSrc = Join-Path (Join-Path $ScriptDir $SkillName) 'SKILL.md'
$DshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $env:USERPROFILE '.dsh' }
$ClaudeHome = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $env:USERPROFILE '.claude' }

function Show-Usage {
    Write-Host @'
Install the mailquery skill into a local AI harness.

Usage: powershell -ExecutionPolicy Bypass -File skills\install.ps1 [options]

Options:
  -Harness dsh|claude|all   install into that harness (all = every detected one)
  -Scope user|project       user-level (default) or the current project
  -Path DIR                 custom skills root; installs DIR\mailquery\SKILL.md
  -Force                    overwrite an existing SKILL.md with different content
  -DryRun                   print the targets without writing anything
  -Help                     show this help and exit

Without -Harness, -Path or -Harness all the script auto-detects installed harnesses
and shows a menu (detected harnesses, a custom path, or install in all detected).

Harness roots (user scope):
  dsh      $env:DSH_HOME or %USERPROFILE%\.dsh  ->  ...\skills
  claude   $env:CLAUDE_CONFIG_DIR or %USERPROFILE%\.claude  ->  ...\skills

Project scope roots (relative to the current directory):
  dsh      .\.dsh\skills
  claude   .\.claude\skills
'@
}

if ($Help) {
    Show-Usage
    exit 0
}

function Test-Harness {
    param([string]$Name)
    switch ($Name) {
        'dsh' {
            return (Test-Path -LiteralPath $DshHome) -or [bool](Get-Command dsh -ErrorAction SilentlyContinue)
        }
        'claude' {
            return (Test-Path -LiteralPath $ClaudeHome) -or [bool](Get-Command claude -ErrorAction SilentlyContinue)
        }
        default { throw "unknown harness: $Name" }
    }
}

function Get-Root {
    param([string]$Name)
    switch ($Name) {
        'dsh' {
            if ($Scope -eq 'project') { Join-Path (Get-Location).Path '.dsh\skills' }
            else { Join-Path $DshHome 'skills' }
        }
        'claude' {
            if ($Scope -eq 'project') { Join-Path (Get-Location).Path '.claude\skills' }
            else { Join-Path $ClaudeHome 'skills' }
        }
        default { throw "unknown harness: $Name" }
    }
}

function Expand-CustomPath {
    param([string]$Value)
    if ($Value -eq '~') { return $env:USERPROFILE }
    if ($Value -like '~/*' -or $Value -like '~\*') {
        return Join-Path $env:USERPROFILE $Value.Substring(2)
    }
    return $Value
}

function Install-Skill {
    param([string]$Root)
    $targetDir = Join-Path $Root $SkillName
    $target = Join-Path $targetDir 'SKILL.md'
    if ($DryRun) {
        Write-Host "would install: $target"
        return
    }
    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
    if (Test-Path -LiteralPath $target) {
        $existing = Get-Content -LiteralPath $target -Raw
        $source = Get-Content -LiteralPath $SkillSrc -Raw
        if ($existing -ceq $source) {
            Write-Host "up to date: $target"
            return
        }
        if (-not $Force) {
            throw "already installed with different content: $target (use -Force)"
        }
        Write-Host "overwriting: $target"
    }
    Copy-Item -LiteralPath $SkillSrc -Destination $target -Force
    Write-Host "installed: $target"
}

function Show-Menu {
    $options = @()
    if (Test-Harness 'dsh') {
        $options += [pscustomobject]@{ Label = 'DeepSeek Harness (dsh)'; Root = (Get-Root 'dsh') }
    }
    if (Test-Harness 'claude') {
        $options += [pscustomobject]@{ Label = 'Claude Code (claude)'; Root = (Get-Root 'claude') }
    }

    Write-Host 'Detected harnesses:'
    $index = 0
    foreach ($option in $options) {
        $index = $index + 1
        Write-Host ("  {0}) {1}   -> {2}" -f $index, $option.Label, (Join-Path $option.Root $SkillName))
    }
    $customIndex = $options.Count + 1
    Write-Host ("  {0}) Custom path (the skill is copied to <path>\mailquery\SKILL.md)" -f $customIndex)
    $allIndex = $null
    if ($options.Count -gt 0) {
        $allIndex = $options.Count + 2
        Write-Host ("  {0}) Install in all detected harnesses" -f $allIndex)
        $default = $allIndex
    }
    else {
        Write-Host ''
        Write-Host ("No harness detected (looked for {0} and {1})." -f $DshHome, $ClaudeHome)
        $default = $customIndex
    }

    $choice = Read-Host ("Select an option [{0}]" -f $default)
    if ([string]::IsNullOrWhiteSpace($choice)) { $choice = [string]$default }
    [int]$selected = 0
    if (-not [int]::TryParse($choice, [ref]$selected)) {
        throw "invalid option: $choice"
    }

    if ($selected -eq $customIndex) {
        $custom = Read-Host 'Skills root directory'
        if ([string]::IsNullOrWhiteSpace($custom)) { throw 'empty path' }
        Install-Skill (Expand-CustomPath $custom)
        return
    }
    if ($allIndex -and $selected -eq $allIndex) {
        foreach ($option in $options) { Install-Skill $option.Root }
        return
    }
    if ($selected -ge 1 -and $selected -le $options.Count) {
        Install-Skill $options[$selected - 1].Root
        return
    }
    throw "invalid option: $choice"
}

if (-not (Test-Path -LiteralPath $SkillSrc)) {
    throw "skill source not found: $SkillSrc"
}

if ($Path) {
    Install-Skill (Expand-CustomPath $Path)
}
elseif ($Harness -eq 'all') {
    $detected = @()
    if (Test-Harness 'dsh') { $detected += 'dsh' }
    if (Test-Harness 'claude') { $detected += 'claude' }
    if ($detected.Count -eq 0) {
        throw "no harness detected (looked for $DshHome and $ClaudeHome); use -Path DIR"
    }
    foreach ($name in $detected) { Install-Skill (Get-Root $name) }
}
elseif ($Harness -ne 'auto') {
    Install-Skill (Get-Root $Harness)
}
else {
    Show-Menu
}

if (-not $DryRun) {
    if (-not (Get-Command mailquery -ErrorAction SilentlyContinue)) {
        Write-Warning 'the mailquery CLI is not on PATH; install it before using the skill (see README)'
    }
    Write-Host ''
    Write-Host 'Restart the harness session (or reload skills) so it discovers the skill.'
}

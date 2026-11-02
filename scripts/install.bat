@echo off
rem ==========================================================================
rem mailquery deployment helper - Windows wrapper for install.ps1
rem
rem Usage: scripts\install.bat [options]
rem        (options are forwarded to install.ps1: -DryRun, -NoConfig, ...)
rem ==========================================================================
setlocal
set "SCRIPT_DIR=%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%install.ps1" %*
exit /b %ERRORLEVEL%

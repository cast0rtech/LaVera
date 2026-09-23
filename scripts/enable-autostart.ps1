# ==============================================================================
# LaVera Hub - Configuraci?n de Inicio Autom?tico en Windows
# ==============================================================================

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  ? LaVera - Configurando Inicio Autom?tico en Windows" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

$scriptParent = Split-Path -Parent $PSScriptRoot
$hubDir = Join-Path $scriptParent "ev-telemetry-hub"

# 1. Asegurar Docker Desktop configurado para iniciar con Windows
Write-Host "[*] 1. Configurando inicio autom?tico de Docker Desktop..." -ForegroundColor Yellow
$dockerSettings = Join-Path $env:APPDATA "Docker\settings.json"
if (Test-Path $dockerSettings) {
    try {
        $json = Get-Content $dockerSettings -Raw | ConvertFrom-Json
        $json.openWithWindows = $true
        $json | ConvertTo-Json -Depth 10 | Set-Content $dockerSettings -Encoding UTF8
        Write-Host "    [+] Docker Desktop configurado para arrancar al iniciar sesi?n." -ForegroundColor Green
    } catch {
        Write-Host "    [-] No se pudo modificar settings.json: $_" -ForegroundColor Gray
    }
}

# 2. Crear script de arranque persistente
$launcherScript = Join-Path $hubDir "autostart-launcher.bat"
$batContent = "@echo off`r`ntimeout /t 10 /nobreak >nul`r`ncd /d `"$hubDir`"`r`ndocker compose up -d`r`n"
Set-Content -Path $launcherScript -Value $batContent -Encoding ASCII
Write-Host "    [+] Script de lanzamiento creado en: $launcherScript" -ForegroundColor Green

# 3. Crear acceso directo en la carpeta de Inicio de Windows (Startup)
$startupFolder = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupFolder "LaVera_AutoStart.lnk"

$wscript = New-Object -ComObject WScript.Shell
$shortcut = $wscript.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "cmd.exe"
$shortcut.Arguments = "/c `"$launcherScript`""
$shortcut.WindowStyle = 7 # Minimized
$shortcut.WorkingDirectory = $hubDir
$shortcut.Description = "Inicio autom?tico de contenedores LaVera EV Telemetry"
$shortcut.Save()

Write-Host "    [+] Acceso directo de inicio registrado en Startup:" -ForegroundColor Green
Write-Host "        $shortcutPath" -ForegroundColor Gray

Write-Host "`n[+] ?Configuraci?n completada con ?xito!" -ForegroundColor Green
Write-Host "    Al encender o reiniciar el equipo, Docker y los contenedores de LaVera arrancar?n autom?ticamente." -ForegroundColor White

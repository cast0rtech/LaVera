# ==============================================================================
# LaVera Hub - Diagn?stico y Reparaci?n de InfluxDB en Docker
# ==============================================================================

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  ? LaVera - Diagn?stico de InfluxDB en Docker" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Comprobar Docker
Write-Host "`n[*] 1. Verificando estado del motor Docker..." -ForegroundColor Yellow
$dockerRunning = $false
try {
    $proc = docker info 2>&1
    if ($LASTEXITCODE -eq 0) {
        $dockerRunning = $true
        Write-Host "    [+] Docker est? activo y respondiendo." -ForegroundColor Green
    } else {
        Write-Host "    [-] Docker no responde. Mensaje: $proc" -ForegroundColor Red
        Write-Host "    ?? Inicia Docker Desktop en Windows antes de levantar los contenedores." -ForegroundColor Yellow
    }
} catch {
    Write-Host "    [-] Error al invocar docker: $_" -ForegroundColor Red
}

# 2. Comprobar archivo .env
Write-Host "`n[*] 2. Verificando configuraci?n y credenciales (.env)..." -ForegroundColor Yellow
$envPath = "ev-telemetry-hub\.env"
if (Test-Path $envPath) {
    Write-Host "    [+] Archivo .env encontrado." -ForegroundColor Green
    $envContent = Get-Content $envPath
    $passLine = $envContent | Where-Object { $_ -match "^INFLUX_PASS=" }
    if ($passLine) {
        $pass = ($passLine -split "=", 2)[1].Trim()
        if ($pass.Length -lt 8) {
            Write-Host "    [-] ATENCI?N: INFLUX_PASS debe tener al menos 8 caracteres (actual: $($pass.Length))." -ForegroundColor Red
        } else {
            Write-Host "    [+] INFLUX_PASS cumple el requisito de longitud (>= 8 caracteres)." -ForegroundColor Green
        }
    }
} else {
    Write-Host "    [-] Archivo .env no encontrado. Generando uno con valores predeterminados seguros..." -ForegroundColor Yellow
    Copy-Item "ev-telemetry-hub\.env.example" "ev-telemetry-hub\.env"
    Write-Host "    [+] Archivo .env creado." -ForegroundColor Green
}

# 3. Comprobar contenedor InfluxDB si Docker est? activo
if ($dockerRunning) {
    Write-Host "`n[*] 3. Inspeccionando contenedor telemetry_influxdb..." -ForegroundColor Yellow
    $container = docker ps -a --filter "name=telemetry_influxdb" --format "{{.Status}}"
    if ($container) {
        Write-Host "    Estado actual: $container" -ForegroundColor Cyan
        Write-Host "    ?ltimas 20 l?neas de registro (logs):" -ForegroundColor Gray
        docker logs telemetry_influxdb --tail 20
    } else {
        Write-Host "    [i] El contenedor telemetry_influxdb a?n no ha sido creado." -ForegroundColor Gray
    }

    # Probar endpoint HTTP
    Write-Host "`n[*] 4. Probando conectividad en puerto 8086..." -ForegroundColor Yellow
    try {
        $ping = Invoke-RestMethod -Uri "http://localhost:8086/ping" -TimeoutSec 3 -ErrorAction SilentlyContinue
        Write-Host "    [+] InfluxDB responde correctamente en http://localhost:8086/ping (Status: OK)" -ForegroundColor Green
    } catch {
        Write-Host "    [-] No hay respuesta en http://localhost:8086/ping." -ForegroundColor Yellow
    }
}

Write-Host "`n----------------------------------------------------------" -ForegroundColor Cyan
Write-Host "?? Si necesitas reiniciar InfluxDB desde cero limpiamente:" -ForegroundColor White
Write-Host "   1. docker compose down -v" -ForegroundColor Gray
Write-Host "   2. docker compose up -d influxdb" -ForegroundColor Gray
Write-Host "   3. docker compose logs -f influxdb" -ForegroundColor Gray
Write-Host "----------------------------------------------------------" -ForegroundColor Cyan

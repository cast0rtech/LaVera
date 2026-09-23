# ==============================================================================
# LaVera Hub - Restablecer y Arreglar InfluxDB ("missing parameter")
# ==============================================================================

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  ? Reparando y reiniciando InfluxDB..." -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Eliminar contenedor previo que se qued? con variables vac?as
Write-Host "[*] 1. Eliminando contenedor anterior con variables obsoletas..." -ForegroundColor Yellow
docker rm -f telemetry_influxdb 2>$null

# 2. Eliminar vol?menes anteriores corruptos
Write-Host "[*] 2. Limpiando vol?menes de InfluxDB..." -ForegroundColor Yellow
docker volume rm -f ev-telemetry-hub_influxdb_data ev-telemetry-hub_influxdb_config lavera_influxdb_data lavera_influxdb_config 2>$null

# 3. Levantar InfluxDB con recreaci?n forzada y variables garantizadas
Write-Host "[*] 3. Levantando InfluxDB con credenciales completas..." -ForegroundColor Yellow
docker compose up -d influxdb --force-recreate

# 4. Mostrar logs en tiempo real
Write-Host "`n[+] Mostrando logs de InfluxDB (esperando a que inicialice)..." -ForegroundColor Green
Start-Sleep -Seconds 3
docker logs telemetry_influxdb --tail 25

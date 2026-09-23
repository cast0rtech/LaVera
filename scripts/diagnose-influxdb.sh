#!/usr/bin/env bash
# ==============================================================================
# LaVera Hub - InfluxDB Docker Diagnostic & Recovery
# ==============================================================================
set -euo pipefail

echo "=========================================================="
echo "  ? LaVera - InfluxDB Docker Diagnostic"
echo "=========================================================="

echo "[*] Checking Docker daemon..."
if docker info > /dev/null 2>&1; then
    echo "    [+] Docker daemon is running."
else
    echo "    [-] Docker daemon is not accessible. Please start Docker."
    exit 1
fi

echo "[*] Checking container telemetry_influxdb status..."
docker ps -a --filter "name=telemetry_influxdb"

echo "[*] Recent logs for telemetry_influxdb:"
docker logs telemetry_influxdb --tail 25 2>/dev/null || echo "    (No container logs found)"

echo "[*] Testing InfluxDB ping endpoint (http://localhost:8086/ping)..."
if curl -s -f http://localhost:8086/ping; then
    echo -e "\n[+] InfluxDB is healthy and responding!"
else
    echo -e "\n[-] InfluxDB did not respond on port 8086."
    echo "?? To perform a clean reset of InfluxDB:"
    echo "   docker compose down -v"
    echo "   docker compose up -d influxdb"
fi

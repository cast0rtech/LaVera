#!/usr/bin/env bash
# ==============================================================================
# LaVera Hub - Reset and Fix InfluxDB ("missing parameter")
# ==============================================================================
set -euo pipefail

echo "=========================================================="
echo "  ? Resetting and Fixing InfluxDB..."
echo "=========================================================="

echo "[*] Removing previous container with stale environment variables..."
docker rm -f telemetry_influxdb 2>/dev/null || true

echo "[*] Cleaning old InfluxDB volumes..."
docker volume rm -f ev-telemetry-hub_influxdb_data ev-telemetry-hub_influxdb_config lavera_influxdb_data lavera_influxdb_config 2>/dev/null || true

echo "[*] Launching InfluxDB with verified parameters..."
docker compose up -d influxdb --force-recreate

echo "[+] Showing InfluxDB logs..."
sleep 3
docker logs telemetry_influxdb --tail 25

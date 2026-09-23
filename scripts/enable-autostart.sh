#!/usr/bin/env bash
# ==============================================================================
# LaVera Hub - Configuraci?n de Inicio Autom?tico en Linux / Raspberry Pi
# ==============================================================================
set -euo pipefail

if [ "$EUID" -ne 0 ]; then
    echo "[-] Por favor ejecuta con permisos de superusuario: sudo bash scripts/enable-autostart.sh"
    exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HUB_DIR="${REPO_DIR}/ev-telemetry-hub"

echo "=========================================================="
echo "  ? LaVera - Configurando Inicio Autom?tico en Linux/Pi"
echo "=========================================================="

echo "[*] 1. Habilitando servicio Docker en el arranque del sistema..."
systemctl enable docker
systemctl enable containerd

echo "[*] 2. Creando servicio systemd para los contenedores LaVera..."
cat << EOF > /etc/systemd/system/lavera-autostart.service
[Unit]
Description=LaVera EV Telemetry Hub (Docker Auto-Start)
After=docker.service network-online.target
Wants=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${HUB_DIR}
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose stop

[Install]
WantedBy=multi-user.target
EOF

echo "[*] 3. Activando servicio systemd..."
systemctl daemon-reload
systemctl enable lavera-autostart.service

echo "[+] ?Inicio autom?tico configurado correctamente!"
echo "    Los contenedores de LaVera arrancar?n de manera autom?tica cada vez que el equipo se encienda o reinicie."

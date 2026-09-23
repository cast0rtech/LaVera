#!/usr/bin/env bash
# ==============================================================================
# LaVera Hub - Appliance Service Installer for Raspberry Pi & ARM Linux
# ==============================================================================
set -euo pipefail

if [ "$EUID" -ne 0 ]; then
  echo "[-] Please run as root (sudo bash install.sh)"
  exit 1
fi

echo "=========================================================="
echo "  ? Installing LaVera Hub Service on ARM Device..."
echo "=========================================================="

APP_DIR="/opt/lavera"
DATA_DIR="${APP_DIR}/data"
mkdir -p "${DATA_DIR}"

# If bundled image archive exists, load it into docker
if [ -f "./lavera-image.tar.gz" ]; then
    echo "[*] Loading pre-compiled Docker image from archive..."
    docker load -i ./lavera-image.tar.gz
fi

# Write systemd service unit
cat << 'EOF' > /etc/systemd/system/lavera-hub.service
[Unit]
Description=LaVera All-in-One EV Telemetry Hub
After=docker.service network-online.target
Wants=docker.service network-online.target

[Service]
Type=simple
Restart=always
RestartSec=10
ExecStartPre=-/usr/bin/docker stop lavera_hub
ExecStartPre=-/usr/bin/docker rm lavera_hub
ExecStart=/usr/bin/docker run --name lavera_hub -p 8080:8080 -v /opt/lavera/data:/app/data --restart unless-stopped lavera-hub:all-in-one
ExecStop=/usr/bin/docker stop lavera_hub

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable lavera-hub.service
systemctl restart lavera-hub.service

echo "[+] LaVera Hub service installed and active!"
echo "?? Access your local dashboard at http://$(hostname).local:8080 or http://localhost:8080"

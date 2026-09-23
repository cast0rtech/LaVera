#!/usr/bin/env bash
# ==============================================================================
# LaVera Hub - Raspberry Pi & ARM Appliance Image Builder
# Targets: Raspberry Pi 3/4/5, Orange Pi, Armbian, and ARM SBCs
# Supports: linux/arm64 (RPi 4/5 64-bit), linux/arm/v7 (RPi 3/Zero 2W 32-bit)
# ==============================================================================
set -euo pipefail

echo "=========================================================="
echo "  ? LaVera Hub - ARM / Raspberry Pi Image Builder"
echo "=========================================================="

ARCH="${1:-arm64}"
OUTPUT_DIR="${2:-./dist-arm}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

mkdir -p "${OUTPUT_DIR}"

echo "[*] Target Architecture: ${ARCH}"
echo "[*] Repository Root:     ${REPO_DIR}"
echo "[*] Output Directory:    ${OUTPUT_DIR}"

# 1. Check Docker & Buildx
if ! command -v docker &> /dev/null; then
    echo "[-] Error: docker is required but not installed." >&2
    exit 1
fi

echo "[*] Setting up Docker Buildx multi-architecture builder..."
docker buildx create --use --name lavera-builder 2>/dev/null || docker buildx use lavera-builder
docker buildx inspect --bootstrap

# 2. Build multi-arch image
IMAGE_TAG="lavera-hub:arm-${ARCH}"
PLATFORM="linux/${ARCH}"
if [ "${ARCH}" == "armhf" ] || [ "${ARCH}" == "armv7" ]; then
    PLATFORM="linux/arm/v7"
elif [ "${ARCH}" == "arm64" ] || [ "${ARCH}" == "aarch64" ]; then
    PLATFORM="linux/arm64"
fi

echo "[*] Compiling Docker image for ${PLATFORM}..."
docker buildx build     --platform "${PLATFORM}"     -t "${IMAGE_TAG}"     -f "${REPO_DIR}/ev-telemetry-hub/Dockerfile.all-in-one"     "${REPO_DIR}/ev-telemetry-hub"     --load

# 3. Export image tarball for offline deployment
TAR_FILE="${OUTPUT_DIR}/lavera-hub-${ARCH}.tar.gz"
echo "[*] Exporting image archive to ${TAR_FILE}..."
docker save "${IMAGE_TAG}" | gzip > "${TAR_FILE}"

# 4. Create provisioning bundle
BUNDLE_DIR="${OUTPUT_DIR}/lavera-appliance-${ARCH}"
mkdir -p "${BUNDLE_DIR}"
cp "${TAR_FILE}" "${BUNDLE_DIR}/lavera-image.tar.gz"
cp "${REPO_DIR}/scripts/lavera-service.sh" "${BUNDLE_DIR}/install.sh"
chmod +x "${BUNDLE_DIR}/install.sh"

cat << 'EOF' > "${BUNDLE_DIR}/README.txt"
===================================================================
  ? LaVera Hub - Appliance Bundle for Raspberry Pi / ARM SBCs
===================================================================

Pasos para instalar en Raspberry Pi OS o Armbian:
1. Copia esta carpeta a tu Raspberry Pi (por USB o SCP):
   scp -r lavera-appliance-* pi@lavera.local:~/

2. Ejecuta el instalador autom?tico:
   sudo bash install.sh

3. Accede al panel local desde cualquier navegador en la red:
   http://lavera.local:8080
EOF

echo "[+] ARM Image Bundle successfully generated in ${BUNDLE_DIR}!"

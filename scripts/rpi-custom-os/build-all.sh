#!/usr/bin/env bash
# ==============================================================================
# LaVera Custom Embedded Linux OS Orchestration Script
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${SCRIPT_DIR}/../../dist-arm/custom-os"

mkdir -p "${OUTPUT_DIR}"

echo "=========================================================="
echo "  🐧 Raspberry Pi Custom Embedded Linux Orchestrator"
echo "=========================================================="

if command -v docker &>/dev/null; then
    echo "[*] Building builder Docker container image..."
    docker build -t rpi-custom-os-builder -f "${SCRIPT_DIR}/Dockerfile.os-builder" "${SCRIPT_DIR}"

    echo "[*] Executing full build inside isolated Docker environment..."
    docker run --privileged --rm \
        -v "${SCRIPT_DIR}:/build/scripts" \
        -v "${SCRIPT_DIR}/config:/build/config" \
        -v "${OUTPUT_DIR}:/build/output" \
        rpi-custom-os-builder \
        bash -c "
            chmod +x /build/scripts/*.sh
            /build/scripts/build-kernel.sh
            /build/scripts/build-rootfs.sh
            /build/scripts/create-distro-image.sh
        "
else
    echo "[!] Docker not detected locally. Running scripts natively..."
    chmod +x "${SCRIPT_DIR}"/*.sh
    "${SCRIPT_DIR}/build-kernel.sh"
    "${SCRIPT_DIR}/build-rootfs.sh"
    "${SCRIPT_DIR}/create-distro-image.sh"
fi

echo "[+] Build complete! Check generated image in: ${OUTPUT_DIR}"

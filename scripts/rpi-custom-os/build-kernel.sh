#!/usr/bin/env bash
# ==============================================================================
# Custom Raspberry Pi Linux Kernel Compiler Script
# Targets: Raspberry Pi 3, 4, 5 (ARM64 / aarch64)
# ==============================================================================
set -euo pipefail

KERNEL_BRANCH="${KERNEL_BRANCH:-rpi-6.6.y}"
BUILD_DIR="${BUILD_DIR:-/build}"
SRC_DIR="${BUILD_DIR}/linux"
STAGING_DIR="${BUILD_DIR}/staging/boot"
MODULES_DIR="${BUILD_DIR}/staging/rootfs"

export ARCH=arm64
export CROSS_COMPILE=aarch64-linux-gnu-

echo "=========================================================="
echo "  🛠️ Compiling Linux Kernel for Raspberry Pi (${KERNEL_BRANCH})"
echo "=========================================================="

mkdir -p "${STAGING_DIR}/overlays" "${MODULES_DIR}"

if [ ! -d "${SRC_DIR}" ]; then
    echo "[*] Cloning Raspberry Pi Kernel source code..."
    git clone --depth 1 -b "${KERNEL_BRANCH}" https://github.com/raspberrypi/linux.git "${SRC_DIR}"
fi

cd "${SRC_DIR}"

echo "[*] Applying Raspberry Pi BCM2711 / BCM2712 Defconfig..."
make bcm2711_defconfig

echo "[*] Building Kernel Image, Device Tree Blobs & Modules (using $(nproc) cores)..."
make -j"$(nproc)" Image modules dtbs

echo "[*] Staging Kernel Image and Device Trees..."
cp arch/arm64/boot/Image "${STAGING_DIR}/kernel8.img"
cp arch/arm64/boot/dts/broadcom/*.dtb "${STAGING_DIR}/"
cp arch/arm64/boot/dts/overlays/*.dtbo "${STAGING_DIR}/overlays/"

echo "[*] Installing Kernel Modules to Staging RootFS..."
make modules_install INSTALL_MOD_PATH="${MODULES_DIR}"

echo "[+] Kernel build completed successfully!"

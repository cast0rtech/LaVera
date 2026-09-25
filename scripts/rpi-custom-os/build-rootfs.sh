#!/usr/bin/env bash
# ==============================================================================
# Custom RootFS Builder using BusyBox for Raspberry Pi Embedded Linux
# ==============================================================================
set -euo pipefail

BUSYBOX_VER="${BUSYBOX_VER:-1.36.1}"
BUILD_DIR="${BUILD_DIR:-/build}"
BUSYBOX_SRC="${BUILD_DIR}/busybox-${BUSYBOX_VER}"
ROOTFS_DIR="${BUILD_DIR}/staging/rootfs"
CONFIG_DIR="${BUILD_DIR}/config"

export ARCH=arm64
export CROSS_COMPILE=aarch64-linux-gnu-

echo "=========================================================="
echo "  📦 Building Root Filesystem (RootFS) with BusyBox"
echo "=========================================================="

mkdir -p "${ROOTFS_DIR}"

if [ ! -d "${BUSYBOX_SRC}" ]; then
    echo "[*] Downloading BusyBox ${BUSYBOX_VER} source..."
    wget -qO- "https://busybox.net/downloads/busybox-${BUSYBOX_VER}.tar.bz2" | tar -xj -C "${BUILD_DIR}"
fi

cd "${BUSYBOX_SRC}"

echo "[*] Configuring BusyBox..."
make defconfig

# Ensure static or dynamic build appropriate for standalone rootfs
sed -i 's/CONFIG_TC=y/CONFIG_TC=n/' .config || true

echo "[*] Compiling and Installing BusyBox..."
make -j"$(nproc)" install CONFIG_PREFIX="${ROOTFS_DIR}"

echo "[*] Constructing Standard Linux Directory Hierarchy..."
mkdir -p "${ROOTFS_DIR}"/{boot,dev,etc/init.d,home,proc,root,sys,tmp,var/log,var/run,usr/lib,lib}

echo "[*] Installing System Configurations..."
cp "${CONFIG_DIR}/fstab" "${ROOTFS_DIR}/etc/fstab"
cp "${CONFIG_DIR}/inittab" "${ROOTFS_DIR}/etc/inittab"
cp "${CONFIG_DIR}/rcS" "${ROOTFS_DIR}/etc/init.d/rcS"
chmod +x "${ROOTFS_DIR}/etc/init.d/rcS"

echo "rpi-custom-os" > "${ROOTFS_DIR}/etc/hostname"

cat << 'EOF' > "${ROOTFS_DIR}/etc/passwd"
root:x:0:0:root:/root:/bin/sh
EOF

cat << 'EOF' > "${ROOTFS_DIR}/etc/group"
root:x:0:
EOF

echo "[+] RootFS build and assembly completed!"

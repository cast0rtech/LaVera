#!/usr/bin/env bash
# ==============================================================================
# Flashable SD Card (.img) Generator for Custom Raspberry Pi OS
# ==============================================================================
set -euo pipefail

BUILD_DIR="${BUILD_DIR:-/build}"
STAGING_DIR="${BUILD_DIR}/staging"
OUTPUT_DIR="${BUILD_DIR}/output"
IMAGE_FILE="${OUTPUT_DIR}/rpi-custom-os.img"
IMAGE_SIZE_MB="${IMAGE_SIZE_MB:-1500}"

echo "=========================================================="
echo "  💿 Building Flashable Boot Image (${IMAGE_SIZE_MB}MB)"
echo "=========================================================="

mkdir -p "${OUTPUT_DIR}"

echo "[*] Allocating sparse disk image file..."
dd if=/dev/zero of="${IMAGE_FILE}" bs=1M count="${IMAGE_SIZE_MB}" status=progress

echo "[*] Creating Partition Table (MBR: Boot FAT32 + RootFS ext4)..."
parted -s "${IMAGE_FILE}" mklabel msdos
parted -s "${IMAGE_FILE}" mkpart primary fat32 4MiB 256MiB
parted -s "${IMAGE_FILE}" set 1 boot on
parted -s "${IMAGE_FILE}" mkpart primary ext4 256MiB 100%

echo "[*] Mapping loop devices..."
LOOP_DEV=$(losetup -fP --show "${IMAGE_FILE}")
BOOT_DEV="${LOOP_DEV}p1"
ROOT_DEV="${LOOP_DEV}p2"

cleanup() {
    echo "[*] Cleaning up loop mounts..."
    umount -l /mnt/boot 2>/dev/null || true
    umount -l /mnt/rootfs 2>/dev/null || true
    losetup -d "${LOOP_DEV}" 2>/dev/null || true
}
trap cleanup EXIT

echo "[*] Formatting partitions..."
mkfs.vfat -F 32 -n "BOOT" "${BOOT_DEV}"
mkfs.ext4 -F -L "ROOTFS" "${ROOT_DEV}"

mkdir -p /mnt/boot /mnt/rootfs
mount "${BOOT_DEV}" /mnt/boot
mount "${ROOT_DEV}" /mnt/rootfs

echo "[*] Copying BootFS files and Firmware..."
cp -r "${STAGING_DIR}/boot/"* /mnt/boot/
cp "${BUILD_DIR}/config/config.txt" /mnt/boot/
cp "${BUILD_DIR}/config/cmdline.txt" /mnt/boot/

# Fetch RPi firmware files if missing
if [ ! -f /mnt/boot/start4.elf ]; then
    echo "[*] Fetching Raspberry Pi Bootloader Firmware files..."
    FW_URL="https://github.com/raspberrypi/firmware/raw/master/boot"
    wget -q "${FW_URL}/bootcode.bin" -O /mnt/boot/bootcode.bin || true
    wget -q "${FW_URL}/start.elf" -O /mnt/boot/start.elf
    wget -q "${FW_URL}/start4.elf" -O /mnt/boot/start4.elf
    wget -q "${FW_URL}/fixup.dat" -O /mnt/boot/fixup.dat
    wget -q "${FW_URL}/fixup4.dat" -O /mnt/boot/fixup4.dat
fi

echo "[*] Copying RootFS files..."
cp -a "${STAGING_DIR}/rootfs/"* /mnt/rootfs/

sync
echo "[+] Disk image successfully created at ${IMAGE_FILE}!"

echo "[*] Compressing disk image with XZ..."
xz -f -k -v -T0 "${IMAGE_FILE}"

echo "=========================================================="
echo "  ✨ Custom Raspberry Pi OS Image Complete!"
echo "  Artifact: ${IMAGE_FILE}.xz"
echo "=========================================================="

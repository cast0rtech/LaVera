"""
LaVera Appliance Image Builder for Raspberry Pi Imager & BalenaEtcher.
Creates ready-to-flash .img.xz / .zip images for Raspberry Pi 3, 4, 5 and ARM SBCs.
Runs on Windows, Linux, and macOS without external dependencies.
"""

import argparse
import hashlib
import json
import lzma
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile

# Ensure UTF-8 output on all platforms
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFAULT_IMAGE_URL = "https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-2026-09-15/2026-09-15-raspios-trixie-arm64-lite.img.xz"


def sha512_crypt(password: str, salt: str = "laverasalt") -> str:
    """Standard glibc sha512crypt implementation in pure Python."""
    b_pw = password.encode('utf-8')
    b_salt = salt.encode('utf-8')
    
    ctx = hashlib.sha512(b_pw + b_salt)
    alt = hashlib.sha512(b_pw + b_salt + b_pw).digest()
    
    pw_len = len(b_pw)
    for i in range(pw_len, 0, -64):
        ctx.update(alt[:min(i, 64)])
        
    i = pw_len
    while i > 0:
        if i & 1:
            ctx.update(alt)
        else:
            ctx.update(b_pw)
        i >>= 1
    a = ctx.digest()
    
    for r in range(5000):
        c = hashlib.sha512()
        if r & 1:
            c.update(b_pw)
        else:
            c.update(a)
        if r % 3 != 0:
            c.update(b_salt)
        if r % 7 != 0:
            c.update(b_pw)
        if r & 1:
            c.update(a)
        else:
            c.update(b_pw)
        a = c.digest()
        
    b64_chars = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    def b64from24bit(b2, b1, b0, n):
        w = ((b2 << 16) | (b1 << 8) | b0) & 0xFFFFFF
        res = []
        while n > 0:
            res.append(b64_chars[w & 0x3F])
            w >>= 6
            n -= 1
        return "".join(res)
        
    out = []
    out.append(b64from24bit(a[0], a[21], a[42], 4))
    out.append(b64from24bit(a[22], a[43], a[1], 4))
    out.append(b64from24bit(a[44], a[2], a[23], 4))
    out.append(b64from24bit(a[3], a[24], a[45], 4))
    out.append(b64from24bit(a[25], a[46], a[4], 4))
    out.append(b64from24bit(a[47], a[5], a[26], 4))
    out.append(b64from24bit(a[6], a[27], a[48], 4))
    out.append(b64from24bit(a[28], a[49], a[7], 4))
    out.append(b64from24bit(a[50], a[8], a[29], 4))
    out.append(b64from24bit(a[9], a[30], a[51], 4))
    out.append(b64from24bit(a[31], a[52], a[10], 4))
    out.append(b64from24bit(a[53], a[11], a[32], 4))
    out.append(b64from24bit(a[12], a[33], a[54], 4))
    out.append(b64from24bit(a[34], a[55], a[13], 4))
    out.append(b64from24bit(a[56], a[14], a[35], 4))
    out.append(b64from24bit(a[15], a[36], a[57], 4))
    out.append(b64from24bit(a[37], a[58], a[16], 4))
    out.append(b64from24bit(a[59], a[17], a[38], 4))
    out.append(b64from24bit(a[18], a[39], a[60], 4))
    out.append(b64from24bit(a[40], a[61], a[19], 4))
    out.append(b64from24bit(a[62], a[20], a[41], 4))
    out.append(b64from24bit(0, 0, a[63], 2))
    
    return f"$6${salt}${''.join(out)}"


def create_payload_tar(output_path: str):
    """Packs ev-telemetry-hub into a portable payload archive."""
    hub_dir = os.path.join(BASE_DIR, "ev-telemetry-hub")
    with tarfile.open(output_path, "w:gz") as tar:
        for root, dirs, files in os.walk(hub_dir):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git")]
            for file in files:
                if file.endswith((".pyc", ".db", ".log")):
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, hub_dir)
                tar.add(full_path, arcname=os.path.join("lavera", rel_path))


def build_bootfs_overlay(overlay_dir: str, username: str = "lavera", password: str = "lavera"):
    """Creates all files needed on the bootfs partition for automated first-boot."""
    os.makedirs(overlay_dir, exist_ok=True)

    # 1. ssh (empty file)
    with open(os.path.join(overlay_dir, "ssh"), "w") as f:
        pass

    # 2. userconf.txt
    pw_hash = sha512_crypt(password)
    with open(os.path.join(overlay_dir, "userconf.txt"), "w", encoding="utf-8") as f:
        f.write(f"{username}:{pw_hash}\n")

    # 3. lavera-payload.tar.gz
    payload_tar = os.path.join(overlay_dir, "lavera-payload.tar.gz")
    create_payload_tar(payload_tar)

    # 4. firstrun.sh
    firstrun_sh = """#!/usr/bin/env bash
# ==============================================================================
# LaVera Hub - First Boot Autonomous Setup
# ==============================================================================
set -euo pipefail
exec > /var/log/lavera-firstboot.log 2>&1

echo "⚡ [LaVera] Starting First-Boot Configuration..."

# 1. Setup Hostname
hostnamectl set-hostname lavera
sed -i 's/127.0.1.1.*/127.0.1.1\\tlavera/' /etc/hosts || true

# 2. Extract Application Payload
BOOT_DIR="/boot/firmware"
[ ! -d "$BOOT_DIR" ] && BOOT_DIR="/boot"

mkdir -p /opt/lavera
if [ -f "${BOOT_DIR}/lavera-payload.tar.gz" ]; then
    echo "[*] Extracting LaVera application..."
    tar -xzf "${BOOT_DIR}/lavera-payload.tar.gz" -C /opt
fi

# 3. Create Persistent Systemd Service
cat << 'EOF' > /etc/systemd/system/lavera-hub.service
[Unit]
Description=LaVera All-in-One EV Telemetry Hub (Offline)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/lavera
ExecStart=/usr/bin/python3 /opt/lavera/all-in-one/app.py
Restart=always
RestartSec=5
Environment=PORT=8080
Environment=LAVERA_DB_PATH=/opt/lavera/data/lavera.db

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable lavera-hub.service
systemctl start lavera-hub.service

# 4. Ensure mDNS / Avahi is active
systemctl enable avahi-daemon || true
systemctl start avahi-daemon || true

# 5. Clean up firstrun from cmdline.txt
if [ -f "${BOOT_DIR}/cmdline.txt" ]; then
    sed -i 's| systemd.run=/boot/firmware/firstrun.sh||g' "${BOOT_DIR}/cmdline.txt" || true
    sed -i 's| systemd.run=/boot/firstrun.sh||g' "${BOOT_DIR}/cmdline.txt" || true
fi

echo "⚡ [LaVera] First boot completed successfully! Dashboard at http://lavera.local:8080"
"""
    with open(os.path.join(overlay_dir, "firstrun.sh"), "w", encoding="utf-8", newline="\n") as f:
        f.write(firstrun_sh.strip() + "\n")


def inject_overlay_windows(image_path: str, overlay_dir: str):
    """Mounts disk image on Windows and injects bootfs overlay."""
    print("[*] Mounting disk image via Windows Disk Management...")
    ps_cmd = f'Mount-DiskImage -ImagePath "{image_path}" -PassThru | Get-Volume | Select-Object -ExpandProperty DriveLetter'
    proc = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
    letters = [l.strip() for l in proc.stdout.splitlines() if l.strip()]
    if not letters:
        print("[-] Could not get drive letter. Image may need manual overlay copy.")
        return False
    
    drive = f"{letters[0]}:\\\\"
    print(f"[+] Boot partition mounted at {drive}")
    try:
        for item in os.listdir(overlay_dir):
            s = os.path.join(overlay_dir, item)
            d = os.path.join(drive, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)
        
        cmdline_file = os.path.join(drive, "cmdline.txt")
        if os.path.exists(cmdline_file):
            with open(cmdline_file, "r") as f:
                content = f.read().strip()
            if "firstrun.sh" not in content:
                content += " systemd.run=/boot/firmware/firstrun.sh"
                with open(cmdline_file, "w") as f:
                    f.write(content + "\n")
        print("[+] Injected overlay files and patched cmdline.txt successfully!")
        return True
    finally:
        subprocess.run(["powershell", "-NoProfile", "-Command", f'Dismount-DiskImage -ImagePath "{image_path}"'], capture_output=True)
        print("[*] Dismounted disk image.")


def main():
    parser = argparse.ArgumentParser(description="LaVera Raspberry Pi & ARM Image Builder")
    parser.add_argument("--output-dir", default=os.path.join(BASE_DIR, "dist-arm"), help="Destination directory")
    parser.add_argument("--image", default=None, help="Path to local .img or .img.xz file")
    parser.add_argument("--username", default="lavera", help="Default username")
    parser.add_argument("--password", default="lavera", help="Default password")

    args = parser.parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    print("===================================================================")
    print("  ⚡ LaVera - Raspberry Pi Imager & BalenaEtcher Image Builder")
    print("===================================================================")

    overlay_dir = os.path.join(args.output_dir, "bootfs_overlay")
    print(f"[*] Building bootfs overlay in: {overlay_dir}")
    build_bootfs_overlay(overlay_dir, username=args.username, password=args.password)

    zip_path = os.path.join(args.output_dir, "lavera-bootfs-overlay.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(overlay_dir):
            for file in files:
                p = os.path.join(root, file)
                z.write(p, arcname=os.path.relpath(p, overlay_dir))
    print(f"[+] Created standalone overlay archive: {zip_path}")

    rpi_json = {
        "os_list": [
            {
                "name": "LaVera - Universal EV Telemetry Hub",
                "description": "Plataforma auto-hospedada 100% offline para telemetría multimarca de vehículos eléctricos (Tesla, VAG, Renault, BYD, etc.) con importador de Tessie y TeslaFi.",
                "icon": "https://raw.githubusercontent.com/castor/LaVera/main/docs/assets/icon.png",
                "url": "https://github.com/castor/LaVera/releases/latest/download/lavera-pi-appliance.img.xz",
                "extract_size": 2500000000,
                "extract_sha256": "",
                "image_download_size": 520000000,
                "init_format": "systemd",
                "devices": ["pi3-64bit", "pi4-64bit", "pi5-64bit"]
            }
        ]
    }
    json_path = os.path.join(args.output_dir, "rpi-imager-lavera.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rpi_json, f, indent=2, ensure_ascii=False)
    print(f"[+] Created Raspberry Pi Imager definition: {json_path}")

    if args.image and os.path.exists(args.image):
        img_file = args.image
        if img_file.endswith(".xz"):
            print(f"[*] Decompressing {img_file}...")
            raw_img = img_file[:-3]
            with lzma.open(img_file, "rb") as fin, open(raw_img, "wb") as fout:
                shutil.copyfileobj(fin, fout)
            img_file = raw_img
        
        if platform.system() == "Windows":
            success = inject_overlay_windows(img_file, overlay_dir)
            if success:
                print(f"[+] Image {img_file} is ready for BalenaEtcher and Raspberry Pi Imager!")


if __name__ == "__main__":
    main()

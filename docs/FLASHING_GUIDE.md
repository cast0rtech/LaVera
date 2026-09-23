# 🍓 Flashing Guide for Raspberry Pi Imager & BalenaEtcher
## LaVera - Universal EV Telemetry Hub (Offline Appliance)

🌐 **Language / Idioma:** **English** | [Español (GUIA_FLASHEO.md)](GUIA_FLASHEO.md)

This guide provides step-by-step instructions to create and flash a bootable SD card or USB drive for your **Raspberry Pi 3, 4, 5** (or compatible ARM boards) using either **Raspberry Pi Imager** or **BalenaEtcher**.

---

## 🚀 Choose Your Preferred Method

| Method | Tool | Difficulty | Best For |
| :--- | :--- | :--- | :--- |
| **Method 1** | **Raspberry Pi Imager** | ⭐ Easy | Native Raspberry Pi OS flashing with automated cloud-init |
| **Method 2** | **BalenaEtcher** | ⭐ Easy | Universal flashing + dropping `lavera-bootfs-overlay.zip` into SD card |
| **Method 3** | **Automated Script** | ⚡ Advanced | Fully building a pre-injected `.img` file from terminal |

---

## 🛠️ Method 1: Flashing with Raspberry Pi Imager (1-Click Cloud-Init)

Raspberry Pi Imager allows you to configure OS settings before writing the image.

1. **Download & Install:**
   - Install [Raspberry Pi Imager](https://www.raspberrypi.com/software/) for Windows, macOS, or Linux.
2. **Choose Device & Operating System:**
   - **Device:** Select your model (*Raspberry Pi 4*, *Raspberry Pi 5*, or *Raspberry Pi 3*).
   - **Operating System:** Choose **Raspberry Pi OS (other)** ➔ **Raspberry Pi OS Lite (64-bit)** (recommended for speed and low RAM).
3. **Configure OS Customization (Gear Icon):**
   - Click **Edit Settings** (or the Gear icon ⚙️).
   - **General Tab:**
     - Hostname: `lavera`
     - Set username: `lavera` / Password: `lavera` (or your preferred password).
     - Configure wireless LAN (SSID and Wi-Fi password if using Wi-Fi).
   - **Services Tab:**
     - Check **Enable SSH** (Use password authentication).
   - **Cloud-Init Tab (Optional / Advanced):**
     - Paste the contents of [`scripts/cloud-init-lavera.yaml`](../scripts/cloud-init-lavera.yaml).
4. **Write Image:**
   - Choose your Storage (microSD or USB SSD) and click **Next** ➔ **Write**.
5. **Boot & Access:**
   - Insert the card into your Raspberry Pi and power on.
   - Open your browser at **`http://lavera.local:8080`**.

---

## 🐳 Method 2: Flashing with BalenaEtcher + Bootfs Overlay

**BalenaEtcher** is ideal for direct image flashing.

1. **Download Base Image:**
   - Download the official [Raspberry Pi OS Lite 64-bit](https://downloads.raspberrypi.com/raspios_lite_arm64/images/).
2. **Flash with BalenaEtcher:**
   - Open BalenaEtcher.
   - Click **Flash from file** and select the `.img.xz` you downloaded.
   - Select your Target Drive (SD card) and click **Flash!**.
3. **Apply LaVera Bootfs Overlay:**
   - Once flashing completes, re-insert the SD card into your computer.
   - A partition named **`bootfs`** (or `boot`) will appear in Windows Explorer / Finder.
   - Unzip [`dist-arm/lavera-bootfs-overlay.zip`](../dist-arm/lavera-bootfs-overlay.zip) directly into the root of this `bootfs` drive:
     - `ssh` (empty file)
     - `userconf.txt` (credentials `lavera:lavera`)
     - `firstrun.sh` (automatic service configuration)
     - `lavera-payload.tar.gz` (pre-bundled LaVera hub & dashboard)
4. **Boot Your Raspberry Pi:**
   - Safely eject the card, insert it into the Pi, and power on.
   - The Pi will automatically extract LaVera, start the service, and be accessible at **`http://lavera.local:8080`**.

---

## ⚡ Method 3: Automated Custom Image Builder Script

You can build a pre-injected raw disk image directly from your workstation:

```bash
# Run the automated builder in the repository
python scripts/create-pi-image.py --username lavera --password lavera
```

This generates:
- `dist-arm/bootfs_overlay/`
- `dist-arm/lavera-bootfs-overlay.zip`
- `dist-arm/rpi-imager-lavera.json`

If you pass a base image:
```bash
python scripts/create-pi-image.py --image /path/to/raspios.img.xz
```
It will automatically decompress, mount the FAT32 boot partition, inject the LaVera files, patch `cmdline.txt`, and produce a ready-to-flash disk image.

---

## 🌐 Verification & First Connection

Once booted:
- **Web Dashboard:** `http://lavera.local:8080` (or `http://<IP_ADDRESS>:8080`).
- **SSH Access:**
  ```bash
  ssh lavera@lavera.local
  # Password: lavera (or what you configured)
  ```
- **Check Service Status:**
  ```bash
  sudo systemctl status lavera-hub.service
  ```

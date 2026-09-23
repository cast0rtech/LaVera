# 🍓 Guía de Flasheo para Raspberry Pi Imager y BalenaEtcher
## LaVera - Universal EV Telemetry Hub (Appliance Offline)

🌐 **Idioma / Language:** [English (FLASHING_GUIDE.md)](FLASHING_GUIDE.md) | **Español**

Esta guía describe paso a paso cómo crear y grabar una tarjeta microSD o unidad USB de arranque para tu **Raspberry Pi 3, 4, 5** (o placas ARM compatibles) utilizando **Raspberry Pi Imager** o **BalenaEtcher**.

---

## 🚀 Elige tu Método Preferido

| Método | Herramienta | Dificultad | Ideal para |
| :--- | :--- | :--- | :--- |
| **Método 1** | **Raspberry Pi Imager** | ⭐ Sencillo | Grabación oficial con personalización desatendida y cloud-init |
| **Método 2** | **BalenaEtcher** | ⭐ Sencillo | Grabación universal + volcado de `lavera-bootfs-overlay.zip` en la SD |
| **Método 3** | **Script Automatizado** | ⚡ Avanzado | Compilación directa de un archivo `.img` autoarrancable desde terminal |

---

## 🛠️ Método 1: Grabación con Raspberry Pi Imager (1-Clic Cloud-Init)

Raspberry Pi Imager permite preconfigurar el sistema operativo antes de escribir la tarjeta.

1. **Descarga e Instalación:**
   - Instala [Raspberry Pi Imager](https://www.raspberrypi.com/software/) para Windows, macOS o Linux.
2. **Seleccionar Dispositivo y Sistema Operativo:**
   - **Dispositivo:** Elige tu modelo (*Raspberry Pi 4*, *Raspberry Pi 5* o *Raspberry Pi 3*).
   - **Sistema Operativo:** Selecciona **Raspberry Pi OS (other)** ➔ **Raspberry Pi OS Lite (64-bit)** (recomendado por rapidez y bajo consumo de memoria RAM).
3. **Configurar la Personalización del SO (Icono del Engranaje ⚙️):**
   - Haz clic en **Editar Ajustes** (o pulsa `Ctrl + Shift + X`).
   - **Pestaña General:**
     - Nombre de host: `lavera`
     - Usuario: `lavera` / Contraseña: `lavera` (o la que tú elijas).
     - Configurar Wi-Fi (introduce el nombre de red SSID y la clave si usarás conexión inalámbrica).
   - **Pestaña Servicios:**
     - Marca **Habilitar SSH** (con autenticación por contraseña).
   - **Pestaña Cloud-Init (Opcional / Avanzado):**
     - Pega el contenido de [`scripts/cloud-init-lavera.yaml`](../scripts/cloud-init-lavera.yaml).
4. **Grabar la Imagen:**
   - Selecciona tu tarjeta de almacenamiento (microSD o SSD USB) y pulsa **Siguiente** ➔ **Escribir**.
5. **Arrancar y Conectar:**
   - Introduce la tarjeta en tu Raspberry Pi y enciéndela.
   - Abre tu navegador en **`http://lavera.local:8080`**.

---

## 🐳 Método 2: Grabación con BalenaEtcher + Bootfs Overlay

**BalenaEtcher** es ideal para flashear imágenes directamente sin pasos complejos.

1. **Descargar la Imagen Base:**
   - Descarga la imagen oficial de [Raspberry Pi OS Lite 64-bit](https://downloads.raspberrypi.com/raspios_lite_arm64/images/).
2. **Grabar con BalenaEtcher:**
   - Abre BalenaEtcher.
   - Pulsa en **Flash from file** y selecciona el archivo `.img.xz` descargado.
   - Selecciona la unidad destino (tu tarjeta microSD) y pulsa **Flash!**.
3. **Aplicar el Overlay de LaVera:**
   - Al finalizar la grabación, retira y vuelve a insertar la tarjeta en tu ordenador.
   - Aparecerá en el Explorador de Windows una unidad llamada **`bootfs`** (o `boot`).
   - Descomprime el archivo [`dist-arm/lavera-bootfs-overlay.zip`](../dist-arm/lavera-bootfs-overlay.zip) directamente en la raíz de dicha unidad `bootfs`:
     - `ssh` (archivo vacío para habilitar SSH)
     - `userconf.txt` (usuario y contraseña `lavera:lavera` preconfigurados)
     - `firstrun.sh` (configurador desatendido del servicio)
     - `lavera-payload.tar.gz` (aplicación completa de LaVera Hub y panel offline)
4. **Arrancar la Raspberry Pi:**
   - Expulsa la tarjeta de forma segura, conéctala a tu Raspberry Pi y enciéndela.
   - El sistema descomprimirá la aplicación, activará el servicio y estará disponible en **`http://lavera.local:8080`**.

---

## ⚡ Método 3: Script Constructor de Imagen Personalizada

Puedes generar un archivo de imagen completo y listo para flashear ejecutando el constructor:

```bash
# Ejecutar el constructor en el repositorio
python scripts/create-pi-image.py --username lavera --password lavera
```

Este comando genera:
- `dist-arm/bootfs_overlay/`
- `dist-arm/lavera-bootfs-overlay.zip`
- `dist-arm/rpi-imager-lavera.json`

Si le pasas una imagen base descargada:
```bash
python scripts/create-pi-image.py --image /ruta/a/raspios.img.xz
```
El script descomprimirá la imagen, montará la partición de arranque FAT32, inyectará los archivos de LaVera, modificará `cmdline.txt` y generará la imagen final lista para flashear.

---

## 🌐 Verificación y Primera Conexión

Una vez iniciado el dispositivo:
- **Panel de Control Web:** `http://lavera.local:8080` (o `http://<IP_DE_LA_PI>:8080`).
- **Acceso por SSH:**
  ```bash
  ssh lavera@lavera.local
  # Contraseña: lavera (o la configurada)
  ```
- **Comprobar Estado del Servicio:**
  ```bash
  sudo systemctl status lavera-hub.service
  ```

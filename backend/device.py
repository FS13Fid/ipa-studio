import os
import re
import subprocess
from .config import IDEVICE_ID_BIN, IDEVICEINFO_BIN, IDEVICEINSTALLER_BIN, CURRENT_ENV, get_settings

def get_air_args(air_enabled=False):
    """Returns arguments needed for Wi-Fi vs USB communication."""
    if air_enabled:
        return ["-n"]
    return []

def get_connected_devices(air_enabled=None):
    """
    Detects all connected iOS devices (iPhone, iPad, iPod) over USB or Wi-Fi.
    Returns list of device objects with name, iOS version, UDID, and connection type.
    """
    if air_enabled is None:
        air_enabled = get_settings().get("AirEnabled", False)

    device_flag = "-n" if air_enabled else "-l"
    conn_type = "Wi-Fi" if air_enabled else "USB"

    try:
        proc = subprocess.run(
            [IDEVICE_ID_BIN, device_flag],
            env=CURRENT_ENV,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )
        if proc.returncode != 0:
            return []
        
        udid_lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
        devices = []

        for udid in udid_lines:
            # Basic validation of UDID format
            if not re.match(r'^[0-9A-Fa-f-]{20,}$', udid):
                continue
            
            # Fetch device name
            name = "iPhone / iPad"
            try:
                name_proc = subprocess.run(
                    [IDEVICE_ID_BIN] + get_air_args(air_enabled) + [udid],
                    env=CURRENT_ENV,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=5
                )
                if name_proc.returncode == 0 and name_proc.stdout.strip():
                    name = name_proc.stdout.strip()
            except Exception:
                pass

            # Fetch ProductVersion & ProductType via ideviceinfo
            ios_version = "Unknown"
            product_type = ""
            if os.path.isfile(IDEVICEINFO_BIN):
                try:
                    ver_proc = subprocess.run(
                        [IDEVICEINFO_BIN] + get_air_args(air_enabled) + ["-u", udid, "-k", "ProductVersion"],
                        env=CURRENT_ENV,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=5
                    )
                    if ver_proc.returncode == 0 and ver_proc.stdout.strip():
                        ios_version = ver_proc.stdout.strip()

                    type_proc = subprocess.run(
                        [IDEVICEINFO_BIN] + get_air_args(air_enabled) + ["-u", udid, "-k", "ProductType"],
                        env=CURRENT_ENV,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=5
                    )
                    if type_proc.returncode == 0 and type_proc.stdout.strip():
                        product_type = type_proc.stdout.strip()
                except Exception:
                    pass

            display_udid = udid[:8] + "…" + udid[-4:] if len(udid) > 16 else udid
            devices.append({
                "udid": udid,
                "display_udid": display_udid,
                "name": name,
                "ios_version": ios_version,
                "product_type": product_type,
                "connection": conn_type
            })

        return devices
    except Exception as e:
        return []

def start_install_process(udid, ipa_path, air_enabled=None):
    """
    Spawns ideviceinstaller process and returns Popen object for streaming progress.
    """
    if air_enabled is None:
        air_enabled = get_settings().get("AirEnabled", False)

    args = [IDEVICEINSTALLER_BIN] + get_air_args(air_enabled) + ["--udid", udid, "install", ipa_path]
    proc = subprocess.Popen(
        args,
        env=CURRENT_ENV,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    return proc

def get_installed_device_apps(udid, air_enabled=None):
    """
    Retrieves the list of installed apps on the specified iOS device.
    """
    if air_enabled is None:
        air_enabled = get_settings().get("AirEnabled", False)

    try:
        proc = subprocess.run(
            [IDEVICEINSTALLER_BIN] + get_air_args(air_enabled) + ["--udid", udid, "-l"],
            env=CURRENT_ENV,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20
        )
        apps = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            # ideviceinstaller output format: "com.example.app - App Name 1.0.0"
            if " - " in line:
                parts = line.split(" - ", 1)
                bundle_id = parts[0].strip()
                rest = parts[1].strip()
                apps.append({
                    "bundle_id": bundle_id,
                    "title": rest
                })
        return {"success": True, "apps": apps}
    except Exception as e:
        return {"success": False, "error": str(e), "apps": []}

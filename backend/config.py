import os
import sys
import platform
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
APPS_DIR = os.path.join(PROJECT_ROOT, "Apps")
BIN_BASE_DIR = os.path.join(PROJECT_ROOT, "bin")
IPATOOL_HOME = os.path.expanduser("~/.ipatool")
SETTINGS_FILE = os.path.join(DATA_DIR, "Settings.json")

os.makedirs(APPS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

def get_platform_subfolder():
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows":
        return "windows_amd64"
    elif system == "darwin":
        if "arm" in machine or "aarch64" in machine:
            return "macOS_arm64"
        return "macOS_amd64"
    else:
        return "linux_amd64"

PLATFORM_SUBFOLDER = get_platform_subfolder()
BIN_DIR = os.path.join(BIN_BASE_DIR, PLATFORM_SUBFOLDER)

# Ensure binaries have execute permissions
for binary_name in ["ipatool-cpp-macOS-arm64", "ipatool-cpp-macOS-amd64", "ipatool-cpp-linux-amd64", 
                    "ipatool.exe", "idevice_id", "ideviceinfo", "ideviceinstaller"]:
    bpath = os.path.join(BIN_DIR, binary_name)
    if os.path.exists(bpath) and not os.access(bpath, os.X_OK):
        try:
            os.chmod(bpath, 0o755)
        except Exception:
            pass

def find_binary(base_name):
    # Check for exact name or with platform suffixes or .exe
    candidates = [
        base_name,
        f"{base_name}.exe",
        f"{base_name}-{PLATFORM_SUBFOLDER.replace('_', '-')}",
        f"{base_name}-macOS-arm64",
        f"{base_name}-macOS-amd64",
        f"{base_name}-linux-amd64",
        f"{base_name}.exe"
    ]
    for c in candidates:
        p = os.path.join(BIN_DIR, c)
        if os.path.isfile(p):
            return p
    # Fallback to system PATH
    import shutil
    sys_path = shutil.which(base_name)
    if sys_path:
        return sys_path
    return os.path.join(BIN_DIR, base_name)

IPATOOL_BIN = find_binary("ipatool-cpp")
if not os.path.isfile(IPATOOL_BIN):
    IPATOOL_BIN = find_binary("ipatool")

IDEVICE_ID_BIN = find_binary("idevice_id")
IDEVICEINFO_BIN = find_binary("ideviceinfo")
IDEVICEINSTALLER_BIN = find_binary("ideviceinstaller")

# Configure environment for dynamic libraries
CURRENT_ENV = os.environ.copy()
path_sep = ";" if platform.system() == "Windows" else ":"
CURRENT_ENV["PATH"] = f"{BIN_DIR}{path_sep}{CURRENT_ENV.get('PATH', '')}"
if platform.system() == "Darwin":
    CURRENT_ENV["DYLD_LIBRARY_PATH"] = f"{BIN_DIR}:{CURRENT_ENV.get('DYLD_LIBRARY_PATH', '')}"
elif platform.system() == "Linux":
    CURRENT_ENV["LD_LIBRARY_PATH"] = f"{BIN_DIR}:{CURRENT_ENV.get('LD_LIBRARY_PATH', '')}"

def get_settings():
    default_settings = {
        "Language": "RU",
        "AirEnabled": False,
        "DebugEnabled": False,
        "KeychainEnabled": False
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                default_settings.update(data)
        except Exception:
            pass
    return default_settings

def update_settings(updates):
    settings = get_settings()
    settings.update(updates)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)
    return settings

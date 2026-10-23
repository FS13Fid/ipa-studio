import os
import zipfile
import plistlib
import base64
from .config import APPS_DIR

def inspect_ipa(ipa_path):
    """
    Reads metadata from an IPA archive (which is a ZIP file).
    Extracts Info.plist and attempts to locate the app icon.
    """
    if not os.path.isfile(ipa_path):
        return None
    
    file_stat = os.stat(ipa_path)
    meta = {
        "filename": os.path.basename(ipa_path),
        "path": ipa_path,
        "size_bytes": file_stat.st_size,
        "size_formatted": f"{round(file_stat.st_size / (1024 * 1024), 1)} MB",
        "modified": int(file_stat.st_mtime),
        "name": os.path.basename(ipa_path).replace(".ipa", ""),
        "bundle_id": None,
        "version": None,
        "min_ios": None,
        "icon_base64": None
    }

    try:
        with zipfile.ZipFile(ipa_path, 'r') as z:
            plist_name = None
            icon_files = []

            for name in z.namelist():
                if name.startswith("Payload/") and name.endswith(".app/Info.plist"):
                    plist_name = name
                elif name.startswith("Payload/") and (".app/AppIcon" in name or ".app/icon" in name.lower()) and name.endswith(".png"):
                    icon_files.append(name)

            if plist_name:
                with z.open(plist_name) as f:
                    try:
                        plist_data = plistlib.load(f)
                        meta["name"] = (
                            plist_data.get("CFBundleDisplayName") or 
                            plist_data.get("CFBundleName") or 
                            meta["name"]
                        )
                        meta["bundle_id"] = plist_data.get("CFBundleIdentifier")
                        meta["version"] = plist_data.get("CFBundleShortVersionString") or plist_data.get("CFBundleVersion")
                        meta["min_ios"] = plist_data.get("MinimumOSVersion")
                    except Exception:
                        pass

            # Try to read the highest-resolution icon
            if icon_files:
                # Sort by length or largest size
                icon_files.sort(key=lambda x: len(x), reverse=True)
                try:
                    with z.open(icon_files[0]) as icon_f:
                        raw_bytes = icon_f.read()
                        meta["icon_base64"] = f"data:image/png;base64,{base64.b64encode(raw_bytes).decode('ascii')}"
                except Exception:
                    pass

    except Exception as e:
        meta["error"] = str(e)

    return meta

def list_downloaded_ipas():
    """
    Returns list of all IPA files in Apps/ folder with metadata.
    """
    if not os.path.exists(APPS_DIR):
        return []
    
    ipas = []
    for f in os.listdir(APPS_DIR):
        if f.lower().endswith(".ipa"):
            full_path = os.path.join(APPS_DIR, f)
            meta = inspect_ipa(full_path)
            if meta:
                ipas.append(meta)
                
    # Sort by modification time newest first
    ipas.sort(key=lambda x: x["modified"], reverse=True)
    return ipas

def delete_ipa(filename):
    """Deletes an IPA file from Apps/"""
    safe_name = os.path.basename(filename)
    target = os.path.join(APPS_DIR, safe_name)
    if os.path.isfile(target):
        try:
            os.remove(target)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    return {"success": False, "error": "File not found"}

import os
import re
import json
import urllib.request
import ssl
from .config import DATA_DIR

APPS_LIST_FILE = os.path.join(DATA_DIR, "AppsList.txt")
APPS_CUSTOM_FILE = os.path.join(DATA_DIR, "AppsListCustom.txt")
CACHE_FILE = os.path.join(DATA_DIR, "MetadataCache.json")

def categorize_app(name):
    low = name.lower()
    if any(k in low for k in ["банк", "сбер", "тинькофф", "т-банк", "альфа", "втб", "газпром", "псб", "инвест", "страхов", "деньги", "капитал", "сейф", "cash", "credit", "fin", "broker"]):
        return "finance"
    if any(k in low for k in ["vpn", "wg", "amnezia", "clash", "proxy", "shadowrocket", "wireguard", "adguard"]):
        return "vpn"
    if any(k in low for k in ["gpt", "claude", "deepseek", "ии", "ai", "chat", "нейро"]):
        return "ai"
    if any(k in low for k in ["vk", "вконтакте", "telegram", "мессенджер", "whatsapp", "mail", "почта", "видео", "соц"]):
        return "social"
    if any(k in low for k in ["2гис", "карты", "навигатор", "такси", "авто", "транспорт", "парков"]):
        return "maps"
    if any(k in low for k in ["кино", "звук", "музыка", "тв", "фильм", "сериал", "video", "music"]):
        return "media"
    if any(k in low for k in ["госуслуг", "налог", "мои документы", "фнс", "паспорт", "мос", "активный гражданин"]):
        return "gov"
    if any(k in low for k in ["ozon", "wildberries", "авито", "маркет", "еда", "доставка", "лавка", "самокат", "шоп"]):
        return "shop"
    return "tools"

def load_apps_list():
    """Loads all 677+ curated apps from AppsList.txt"""
    if not os.path.exists(APPS_LIST_FILE):
        return []
    
    apps = []
    with open(APPS_LIST_FILE, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            # format: "Name: ID"
            if ":" in line:
                parts = line.rsplit(":", 1)
                name = parts[0].strip()
                app_id = parts[1].strip()
                if app_id.isdigit():
                    category = categorize_app(name)
                    apps.append({
                        "index": idx + 1,
                        "name": name,
                        "id": app_id,
                        "category": category,
                        "is_custom": False
                    })
    return apps

def load_custom_apps():
    """Loads user's custom apps from AppsListCustom.txt"""
    if not os.path.exists(APPS_CUSTOM_FILE):
        return []
    
    apps = []
    with open(APPS_CUSTOM_FILE, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                parts = line.rsplit(":", 1)
                name = parts[0].strip()
                app_id = parts[1].strip()
                if app_id.isdigit():
                    apps.append({
                        "index": idx + 1,
                        "name": name,
                        "id": app_id,
                        "category": categorize_app(name),
                        "is_custom": True
                    })
    return apps

def add_custom_app(name, app_id):
    """Adds a new custom app to AppsListCustom.txt"""
    name = str(name).strip().replace("\n", "").replace(":", "-")
    app_id = str(app_id).strip()
    if not app_id.isdigit():
        return {"success": False, "error": "App ID must be numeric"}
    
    # Read existing
    existing = load_custom_apps()
    for app in existing:
        if app["id"] == app_id:
            return {"success": False, "error": "App ID already exists in custom list"}
            
    with open(APPS_CUSTOM_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n{name}: {app_id}")
        
    return {"success": True, "app": {"name": name, "id": app_id, "is_custom": True}}

def remove_custom_app(app_id):
    """Removes custom app by ID."""
    app_id = str(app_id).strip()
    if not os.path.exists(APPS_CUSTOM_FILE):
        return {"success": False, "error": "File not found"}
        
    lines = []
    found = False
    with open(APPS_CUSTOM_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if ":" in line:
                parts = line.rsplit(":", 1)
                if parts[1].strip() == app_id:
                    found = True
                    continue
            lines.append(line)
            
    if found:
        with open(APPS_CUSTOM_FILE, "w", encoding="utf-8") as f:
            f.writelines(lines)
        return {"success": True}
    return {"success": False, "error": "App ID not found"}

# In-memory and disk cache for iTunes metadata
_metadata_cache = {}

def get_metadata_cache():
    global _metadata_cache
    if not _metadata_cache and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                _metadata_cache = json.load(f)
        except Exception:
            _metadata_cache = {}
    return _metadata_cache

def save_metadata_cache():
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_metadata_cache, f, ensure_ascii=False)
    except Exception:
        pass

def fetch_itunes_app_details(app_id, country="ru"):
    """
    Fetches real App Store artwork, description, version, bundleId via iTunes lookup API.
    Uses caching to keep responses instant.
    """
    cache = get_metadata_cache()
    if str(app_id) in cache:
        return cache[str(app_id)]
    
    try:
        url = f"https://itunes.apple.com/lookup?id={app_id}&country={country}"
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(url, headers={"User-Agent": "iTunes/12.9.5"})
        with urllib.request.urlopen(req, context=ctx, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results", [])
            if results:
                item = results[0]
                meta = {
                    "id": str(app_id),
                    "name": item.get("trackName"),
                    "bundle_id": item.get("bundleId"),
                    "version": item.get("version"),
                    "min_ios": item.get("minimumOsVersion"),
                    "icon": item.get("artworkUrl512") or item.get("artworkUrl100") or item.get("artworkUrl60"),
                    "developer": item.get("artistName"),
                    "genres": item.get("genres", []),
                    "file_size": item.get("fileSizeBytes")
                }
                cache[str(app_id)] = meta
                save_metadata_cache()
                return meta
    except Exception:
        pass
    
    # Return placeholder
    return {
        "id": str(app_id),
        "name": None,
        "bundle_id": None,
        "version": None,
        "icon": None
    }

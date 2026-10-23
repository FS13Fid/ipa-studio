import os
import re
import json
import zlib
import subprocess
import zipfile
import plistlib
import ssl
from io import BytesIO

try:
    from PIL import Image
except ImportError:
    Image = None

REPO_OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER", "FS13Fid")
REPO_NAME = os.environ.get("GITHUB_REPOSITORY", "FS13Fid/ipa-studio").split("/")[-1]
BASE_URL = f"https://{REPO_OWNER.lower()}.github.io/{REPO_NAME}"
RELEASE_DOWNLOAD_BASE = f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/download/v1.0"

os.makedirs("manifests", exist_ok=True)
os.makedirs("icons", exist_ok=True)
os.makedirs("custom-icons", exist_ok=True)

# Known bundle ID mapping for clean titles
KNOWN_TITLES = {
    "ru.vlad.work": "СберБанк (СБОЛ)",
    "ru.rom.advanced": "СБОЛ",
    "ru.sberbank.onlineiphone": "СберБанк Онлайн",
    "com.alfabank.app": "Альфа-Банк",
    "ru.tcsbank.mobileclient": "Тинькофф",
    "ru.yoo.money": "ЮMoney",
    "ru.mobile.timob": "Т-Мобайл",
    "ru.avito.app": "Авито",
    "ru.abb.akbarsonline": "Ак Барс Банк",
    "com.vk.dating": "VK Знакомства",
    "com.music.vk": "VK Музыка",
    "ru.moiseev": "Купер",
    "com.mcdonaldsru.mcd": "Вкусно — и точка",
    "com.sm.FlowTime": "Сириус",
    "com.advancy.app": "Advance",
    "ru.atoy.selfcare": "ATOY",
    "org.reactjs.native.prod.AuReactNativeApp": "Au.ru",
    "ru.tomlevierr.docstorage": "DocStorage",
    "com.paata.shihan": "EatsRate",
    "su.ffg.happ": "Happ",
    "ru.kari-app.ios": "Kari",
    "ru.mail.mail": "Почта Mail.ru",
    "ru.oneme.app": "MAX",
    "com.inv.gen": "Online",
    "ru.ozon.fintech.finance": "Ozon Банк",
    "sh.weme.wemesh": "Rave",
    "ru.rzd.passenger": "Пассажирам",
    "com.vk.vkclient": "ВКонтакте",
    "com.vk.vkme": "VK Messenger",
    "com.vk.vkvideo.prod": "VK Video",
    "com.yandex.fintech.bank-app": "Яндекс Банк"
}

def format_size(bytes_num):
    for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
        if bytes_num < 1024.0:
            return f"{bytes_num:.1f} {unit}"
        bytes_num /= 1024.0
    return f"{bytes_num:.1f} ГБ"

def download_with_curl(url, dest_path, token=None):
    cmd = ["curl", "-L", "-s", "--retry", "3", "--retry-delay", "2", "-o", dest_path]
    if token:
        cmd.extend(["-H", f"Authorization: token {token}"])
    cmd.append(url)
    res = subprocess.run(cmd)
    return res.returncode == 0 and os.path.exists(dest_path) and os.path.getsize(dest_path) > 1024

def de_cgbi(data):
    """
    Decodes Apple's proprietary CgBI crushed PNG into standard PNG format.
    Removes CgBI chunk, decompresses raw deflate, swaps BGRA to RGBA, re-compresses IDAT.
    """
    if len(data) < 16 or data[:8] != b'\x89PNG\r\n\x1a\n':
        return data
    chunk_type = data[12:16]
    if chunk_type != b'CgBI':
        return data  # already standard PNG

    pos = 8
    chunks = []
    idat_data = b''
    ihdr_data = None
    while pos < len(data):
        c_len = int.from_bytes(data[pos:pos+4], 'big')
        c_type = data[pos+4:pos+8]
        c_data = data[pos+8:pos+8+c_len]
        pos += 12 + c_len
        if c_type == b'CgBI':
            continue
        elif c_type == b'IHDR':
            ihdr_data = c_data
            chunks.append((c_type, c_data))
        elif c_type == b'IDAT':
            idat_data += c_data
        else:
            chunks.append((c_type, c_data))

    if not ihdr_data or not idat_data:
        return data

    width = int.from_bytes(ihdr_data[0:4], 'big')
    height = int.from_bytes(ihdr_data[4:8], 'big')
    bit_depth = ihdr_data[8]
    color_type = ihdr_data[9]

    try:
        raw = zlib.decompress(idat_data, -15)
    except Exception:
        try:
            raw = zlib.decompress(idat_data)
        except Exception:
            return data

    if color_type == 6 and bit_depth == 8:
        scanline_size = 1 + width * 4
        if len(raw) == scanline_size * height:
            unswapped = bytearray(raw)
            for y in range(height):
                row_offset = y * scanline_size + 1
                for x in range(width):
                    pixel_offset = row_offset + x * 4
                    b = unswapped[pixel_offset]
                    r = unswapped[pixel_offset + 2]
                    unswapped[pixel_offset] = r
                    unswapped[pixel_offset + 2] = b
            raw = bytes(unswapped)

    new_idat = zlib.compress(raw)
    out = bytearray(b'\x89PNG\r\n\x1a\n')
    for c_type, c_data in chunks:
        if c_type == b'IEND':
            out.extend(len(new_idat).to_bytes(4, 'big'))
            out.extend(b'IDAT')
            out.extend(new_idat)
            out.extend(zlib.crc32(b'IDAT' + new_idat).to_bytes(4, 'big'))
        out.extend(len(c_data).to_bytes(4, 'big'))
        out.extend(c_type)
        out.extend(c_data)
        out.extend(zlib.crc32(c_type + c_data).to_bytes(4, 'big'))
    return bytes(out)

def save_clean_png(raw_bytes, dest_path):
    processed = de_cgbi(raw_bytes)
    if Image:
        try:
            img = Image.open(BytesIO(processed))
            img.load()
            img.convert("RGBA").save(dest_path, "PNG")
            return True
        except Exception:
            pass

    with open(dest_path, "wb") as f:
        f.write(processed)
    return os.path.exists(dest_path) and os.path.getsize(dest_path) > 500

def extract_native_icon(z, plist_data, plist_path, dest_path):
    # 1. iTunesArtwork in root of IPA
    for name in z.namelist():
        if name.lower() in ["itunesartwork", "itunesartwork.png", "itunesartwork@2x"]:
            try:
                data = z.read(name)
                if len(data) > 2048 and save_clean_png(data, dest_path):
                    return True
            except Exception:
                pass

    # 2. CFBundleIcons from Info.plist
    icon_names = []
    icons_dict = plist_data.get("CFBundleIcons", {}).get("CFBundlePrimaryIcon", {})
    if "CFBundleIconFiles" in icons_dict:
        icon_names.extend(icons_dict["CFBundleIconFiles"])
    if "CFBundleIconName" in icons_dict:
        icon_names.append(icons_dict["CFBundleIconName"])
    if "CFBundleIconFile" in plist_data:
        icon_names.append(plist_data["CFBundleIconFile"])
    if "CFBundleIconFiles" in plist_data:
        icon_names.extend(plist_data["CFBundleIconFiles"])

    app_dir = os.path.dirname(plist_path)
    for iname in reversed(icon_names):
        clean_name = iname.replace(".png", "")
        matches = [
            n for n in z.namelist()
            if n.startswith(app_dir) and clean_name.lower() in n.lower() and n.endswith(".png")
        ]
        if matches:
            matches.sort(key=lambda x: z.getinfo(x).file_size, reverse=True)
            for m in matches:
                try:
                    if save_clean_png(z.read(m), dest_path):
                        return True
                except Exception:
                    continue

    # 3. Search PNGs with icon/appicon keywords
    candidates = [
        n for n in z.namelist()
        if n.startswith(app_dir) and n.endswith(".png") and any(k in n.lower() for k in ["appicon", "icon", "60x60", "76x76", "1024"])
    ]
    valid = [c for c in candidates if not any(b in c.lower() for b in ["20x20", "29x29", "notification", "badge"])]
    if not valid:
        valid = candidates

    if valid:
        valid.sort(key=lambda x: z.getinfo(x).file_size, reverse=True)
        for cand in valid[:6]:
            try:
                if save_clean_png(z.read(cand), dest_path):
                    return True
            except Exception:
                continue

    return False

def clean_app_name(raw_name, bundle_id, filename, metadata=None):
    """
    Returns clean human-readable app title, resolving obfuscated titles like '-._._'.
    """
    if bundle_id in KNOWN_TITLES:
        return KNOWN_TITLES[bundle_id]

    name = (raw_name or "").strip()

    # Try metadata itemName / playlistName
    if metadata:
        meta_title = metadata.get("itemName") or metadata.get("playlistName")
        if meta_title and len(str(meta_title).strip()) > 1:
            m_str = str(meta_title).strip()
            # Clean promo suffixes like " — с Салютом" or ": товары, мебель для дома"
            clean_sub = re.split(r'[:—–]\s*', m_str)[0].strip()
            if len(clean_sub) > 1 and not re.match(r'^[\s._-]+$', clean_sub):
                return clean_sub
            return m_str

    # If raw_name is empty or just punctuation
    if not name or re.match(r'^[\s._-]+$', name) or name.lower() in ["app", "ios", "iphone"]:
        fn = filename.replace(".ipa", "").lower()
        if "sbol" in fn:
            return "СберБанк (СБОЛ)"
        elif "timob" in fn:
            return "Т-Мобайл"
        elif "money" in fn:
            return "Деньги (Альфа-Банк)"
        elif "au.ru" in fn or "au" in fn:
            return "Au.ru"
        elif "docstorage" in fn:
            return "DocStorage"
        elif "tcs" in fn or "tinkoff" in fn:
            return "Тинькофф"
        elif "alfa" in fn:
            return "Альфа-Банк"
        elif "avito" in fn:
            return "Авито"
        elif "akbars" in fn:
            return "Ак Барс Банк"
        elif "vk" in fn:
            return "VK"
        elif "yandex" in fn:
            return "Яндекс"

        parts = bundle_id.split(".")
        if len(parts) >= 2:
            candidate = parts[-1].capitalize()
            if len(candidate) > 2:
                return candidate

    cleaned = re.sub(r'^[\s._-]+|[\s._-]+$', '', name)
    return cleaned if len(cleaned) > 1 else (name or bundle_id)

def extract_account_email(ipa_filename, metadata=None):
    """
    Extracts normalized Apple ID account email from filename or iTunesMetadata.plist.
    """
    # 1. Search for clean email pattern in filename
    if ipa_filename:
        clean_fn = ipa_filename.replace(".ipa", "")
        m = re.search(r'(?:^|[_\+\s\/\\:\-])([a-zA-Z0-9][a-zA-Z0-9.-]*@[a-zA-Z0-9-]+\.[a-zA-Z]{2,10})$', clean_fn, re.IGNORECASE)
        if not m:
            m = re.search(r'(?:^|[_\+\s\/\\:\-])([a-zA-Z0-9][a-zA-Z0-9.-]*@[a-zA-Z0-9-]+\.[a-zA-Z]{2,10})', clean_fn, re.IGNORECASE)
        if m:
            return m.group(1).lower().strip()

    # 2. Check iTunesMetadata.plist for actual email (must contain @ and .)
    if metadata:
        for key in ["apple-id", "AppleID"]:
            found = metadata.get(key)
            if found and "@" in str(found) and "." in str(found).split("@")[-1]:
                return str(found).lower().strip()
        account_info = metadata.get("com.apple.iTunesStore.downloadInfo", {}).get("accountInfo", {})
        if account_info and isinstance(account_info, dict):
            found = account_info.get("AppleID")
            if found and "@" in str(found) and "." in str(found).split("@")[-1]:
                return str(found).lower().strip()

    return "sinakayev@icloud.com"

def inspect_ipa(ipa_path, download_url, ipa_filename=None):
    if not ipa_filename:
        ipa_filename = os.path.basename(ipa_path)
    print(f"\n--- Анализ {ipa_filename} ---")
    size_str = format_size(os.path.getsize(ipa_path))

    with zipfile.ZipFile(ipa_path, 'r') as z:
        plist_path = None
        for name in z.namelist():
            if re.match(r"^Payload/[^/]+\.app/Info\.plist$", name):
                plist_path = name
                break

        if not plist_path:
            return None

        with z.open(plist_path) as f:
            try:
                plist_data = plistlib.load(f)
            except Exception:
                return None

        meta_data = {}
        for meta_name in ["iTunesMetadata.plist", "Payload/iTunesMetadata.plist"]:
            if meta_name in z.namelist():
                try:
                    with z.open(meta_name) as mf:
                        meta_data = plistlib.load(mf)
                        break
                except Exception:
                    pass

        account_email = extract_account_email(ipa_filename, meta_data)
        bundle_id = plist_data.get("CFBundleIdentifier", "unknown.bundle")
        version = plist_data.get("CFBundleShortVersionString", plist_data.get("CFBundleVersion", "1.0.0"))
        raw_name = plist_data.get("CFBundleDisplayName", plist_data.get("CFBundleName", ""))
        name = clean_app_name(raw_name, bundle_id, ipa_filename, meta_data)
        print(f"-> {name} ({bundle_id}, v{version}) | Apple ID: {account_email}")

        min_ios = plist_data.get("MinimumOSVersion")
        if not min_ios:
            ios_m = re.search(r'iOS_([0-9\.\+]+)', ipa_filename)
            if ios_m:
                min_ios = ios_m.group(1).replace('+', '')

        icon_filename = f"{bundle_id}.png"
        icon_dest = os.path.join("icons", icon_filename)
        custom_icon_path = os.path.join("custom-icons", icon_filename)

        if os.path.exists(custom_icon_path):
            with open(custom_icon_path, "rb") as src, open(icon_dest, "wb") as dst:
                dst.write(src.read())
            timestamp = int(os.path.getmtime(custom_icon_path))
            icon_url = f"{BASE_URL}/icons/{icon_filename}?t={timestamp}"
        else:
            has_icon = False
            if os.path.exists(icon_dest) and os.path.getsize(icon_dest) > 1000:
                has_icon = True
            else:
                has_icon = extract_native_icon(z, plist_data, plist_path, icon_dest)
            
            icon_url = f"{BASE_URL}/icons/{icon_filename}?v={version}" if has_icon else f"{BASE_URL}/icons/{icon_filename}"

        manifest_filename = f"{bundle_id}.plist"
        manifest_path = os.path.join("manifests", manifest_filename)
        manifest_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>items</key>
    <array>
        <dict>
            <key>assets</key>
            <array>
                <dict>
                    <key>kind</key>
                    <string>software-package</string>
                    <key>url</key>
                    <string>{download_url}</string>
                </dict>
            </array>
            <key>metadata</key>
            <dict>
                <key>bundle-identifier</key>
                <string>{bundle_id}</string>
                <key>bundle-version</key>
                <string>{version}</string>
                <key>kind</key>
                <string>software</string>
                <key>title</key>
                <string>{name}</string>
            </dict>
        </dict>
    </array>
</dict>
</plist>"""
        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write(manifest_content)

        return {
            "name": name,
            "version": version,
            "bundleId": bundle_id,
            "account": account_email,
            "size": size_str,
            "minIos": min_ios or "14.0",
            "icon": icon_url,
            "manifestUrl": f"{BASE_URL}/manifests/{manifest_filename}",
            "description": f"Приложение {name} выгружено из учетной записи {account_email}."
        }

def fetch_releases(repo, token=None):
    headers = {"User-Agent": "Mozilla/5.0"}
    if token:
        headers["Authorization"] = f"token {token}"
    url = f"https://api.github.com/repos/{repo}/releases"

    try:
        import urllib.request
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"Ошибка запроса релизов: {e}")
        return []

def parse_ver(v):
    parts = re.findall(r'\d+', str(v))
    return [int(x) for x in parts] if parts else [0]

def main():
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY", f"{REPO_OWNER}/{REPO_NAME}")
    releases = fetch_releases(repo, token)

    apps_dict = {}
    for rel in releases:
        for asset in rel.get("assets", []):
            if asset.get("name", "").endswith(".ipa"):
                ipa_name = asset["name"]
                download_url = asset["browser_download_url"]
                local_path = f"/tmp/{ipa_name}"

                print(f"\nЗагрузка {ipa_name}...")
                ok = download_with_curl(download_url, local_path, token)
                if not ok:
                    continue

                try:
                    info = inspect_ipa(local_path, download_url, ipa_name)
                    if info:
                        b_id = info["bundleId"]
                        if b_id not in apps_dict:
                            apps_dict[b_id] = info
                        else:
                            old = apps_dict[b_id]
                            # Deduplication: prefer higher version or explicit account
                            if parse_ver(info["version"]) > parse_ver(old["version"]):
                                apps_dict[b_id] = info
                            elif parse_ver(info["version"]) == parse_ver(old["version"]):
                                if "@" in info.get("account", "") and "@" not in old.get("account", ""):
                                    apps_dict[b_id] = info
                except Exception as ex:
                    print(f"Ошибка анализа {ipa_name}: {ex}")

                if os.path.exists(local_path):
                    os.remove(local_path)

    apps_data = list(apps_dict.values())
    if apps_data:
        apps_data.sort(key=lambda x: x["name"].lower())
        with open("apps.json", "w", encoding="utf-8") as f:
            json.dump(apps_data, f, ensure_ascii=False, indent=2)
        print(f"\nУспех! Каталог обновлен. Всего уникальных приложений: {len(apps_data)}")

if __name__ == "__main__":
    main()

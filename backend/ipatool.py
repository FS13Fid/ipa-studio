import os
import re
import json
import subprocess
import urllib.request
import urllib.parse
import ssl
from .config import IPATOOL_BIN, CURRENT_ENV, APPS_DIR, IPATOOL_HOME
from .accounts import get_active_account_info, get_all_accounts, switch_account

def run_ipatool(args, timeout=120):
    """Runs ipatool with specified arguments, returns (returncode, stdout, stderr)."""
    cmd = [IPATOOL_BIN] + args
    try:
        proc = subprocess.run(
            cmd,
            env=CURRENT_ENV,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)

def login(email, password, auth_code=None, keychain_passphrase=None):
    """Authenticates with Apple ID, supporting 2FA."""
    args = ["auth", "login", "-e", email, "-p", password]
    if auth_code:
        args.extend(["-a", str(auth_code).strip()])
    if keychain_passphrase:
        args.extend(["--keychain-passphrase", keychain_passphrase])
    
    code, stdout, stderr = run_ipatool(args, timeout=60)
    output = f"{stdout}\n{stderr}".strip()
    
    if code == 0:
        os.makedirs(IPATOOL_HOME, exist_ok=True)
        login_marker = os.path.join(IPATOOL_HOME, "login")
        try:
            with open(login_marker, "w") as f:
                f.write("ok")
        except Exception:
            pass
        
        # Trigger kbsync refresh
        run_ipatool(["kbsync", "--refresh"], timeout=30)
        
        account_info = get_active_account_info()
        return {"success": True, "account": account_info, "output": output}
    
    # Analyze failure reason
    low_out = output.lower()
    needs_2fa = False
    if "2fa" in low_out or "code" in low_out or "verification" in low_out or "auth-code" in low_out:
        needs_2fa = True
        
    return {
        "success": False,
        "needs_2fa": needs_2fa,
        "error": output or "Authentication failed"
    }

def revoke():
    """Revokes active credentials."""
    code, stdout, stderr = run_ipatool(["auth", "revoke"], timeout=15)
    return {"success": code == 0, "output": f"{stdout}\n{stderr}".strip()}

def search_appstore(query, limit=20, country="ru"):
    """
    Searches App Store. First tries Apple's public iTunes Search API (returns rich metadata, icons, screenshots),
    with fallback to ipatool search.
    """
    results = []
    # 1. Try iTunes Search API (fast, rich metadata, works even without login)
    try:
        url = f"https://itunes.apple.com/search?term={urllib.parse.quote(query)}&country={country}&entity=software&limit={limit}"
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(url, headers={"User-Agent": "iTunes/12.9.5 (Macintosh; OS X 10.14.6)"})
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for item in data.get("results", []):
                results.append({
                    "id": str(item.get("trackId")),
                    "name": item.get("trackName"),
                    "bundle_id": item.get("bundleId"),
                    "version": item.get("version"),
                    "min_ios": item.get("minimumOsVersion"),
                    "icon": item.get("artworkUrl512") or item.get("artworkUrl100") or item.get("artworkUrl60"),
                    "seller": item.get("sellerName") or item.get("artistName"),
                    "price": item.get("formattedPrice") or "Free",
                    "formatted_size": f"{round(int(item.get('fileSizeBytes', 0)) / (1024*1024), 1)} MB" if item.get('fileSizeBytes') else None,
                    "screenshots": item.get("screenshotUrls", [])[:4],
                    "genres": item.get("genres", []),
                    "release_date": item.get("currentVersionReleaseDate") or item.get("releaseDate")
                })
        if results:
            return {"success": True, "results": results, "source": "itunes_api"}
    except Exception as e:
        pass

    # 2. Fallback to ipatool search if iTunes Search returned empty or failed
    code, stdout, stderr = run_ipatool(["search", query, "-l", str(limit), "--format", "json"])
    if code == 0:
        try:
            data = json.loads(stdout)
            for item in data.get("apps", []):
                results.append({
                    "id": str(item.get("id")),
                    "name": item.get("name"),
                    "bundle_id": item.get("bundleId"),
                    "version": item.get("version"),
                    "icon": None,
                    "price": "Free"
                })
            return {"success": True, "results": results, "source": "ipatool"}
        except Exception:
            pass

    return {"success": False, "results": [], "error": stderr or "No apps found"}

def purchase_app(app_id, bundle_id=None, force=True, all_accounts=False):
    """
    Acquires a free license for an app to the active account (or all saved accounts).
    """
    if all_accounts:
        accounts_data = get_all_accounts()
        all_accs = []
        if accounts_data.get("active") and accounts_data["active"].get("email"):
            all_accs.append(accounts_data["active"]["email"])
        all_accs.extend(accounts_data.get("saved", []))
        
        results = {}
        for acc in all_accs:
            switch_account(acc)
            res = purchase_app(app_id, bundle_id, force=force, all_accounts=False)
            results[acc] = res
        return {"success": True, "batch": True, "results": results}

    args = ["purchase"]
    if app_id:
        args.extend(["-i", str(app_id)])
    elif bundle_id:
        args.extend(["-b", str(bundle_id)])
    else:
        return {"success": False, "error": "App ID or Bundle ID required"}
    
    if force:
        args.append("-f")
    
    code, stdout, stderr = run_ipatool(args, timeout=30)
    output = f"{stdout}\n{stderr}".strip()
    return {
        "success": code == 0,
        "output": output,
        "error": None if code == 0 else output
    }

def list_purchases(all_years=True, since_year=None):
    """
    Retrieves purchase history from Apple Account.
    Returns list of purchased apps (including removed ones).
    """
    args = ["list-purchases"]
    if all_years:
        args.append("--all")
    elif since_year:
        args.extend(["--since-year", str(since_year)])
    
    code, stdout, stderr = run_ipatool(args, timeout=180)
    output = f"{stdout}\n{stderr}"
    
    # Try parsing apps=[...] from output
    match = re.search(r'apps=(\[.*?\])', output, re.DOTALL)
    raw_apps = []
    if match:
        try:
            raw_apps = json.loads(match.group(1))
        except Exception:
            pass
    elif stdout.strip().startswith("{") or stdout.strip().startswith("["):
        try:
            parsed = json.loads(stdout)
            raw_apps = parsed.get("apps", parsed if isinstance(parsed, list) else [])
        except Exception:
            pass
    
    if not raw_apps:
        # Check text lines
        # format: ID  BundleID  Name  Date
        for line in stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("="):
                continue
            parts = [p.strip() for p in line.split("  ") if p.strip()]
            if len(parts) >= 2 and parts[0].isdigit():
                raw_apps.append({
                    "id": parts[0],
                    "name": parts[1],
                    "kind": "iOS App",
                    "purchaseDate": parts[2] if len(parts) > 2 else ""
                })

    # Filter and format
    cleaned_apps = []
    allowed_kinds = ["iOS App", "Mac App"]
    for app in reversed(raw_apps):
        kind = str(app.get("kind", "iOS App")).strip()
        if kind and kind not in allowed_kinds:
            continue
        cleaned_apps.append({
            "id": str(app.get("id", "")),
            "name": str(app.get("name", "")).strip(),
            "kind": kind or "iOS App",
            "purchase_date": str(app.get("purchaseDate", "")).strip()
        })
        
    return {
        "success": len(cleaned_apps) > 0 or code == 0,
        "count": len(cleaned_apps),
        "apps": cleaned_apps,
        "error": None if (len(cleaned_apps) > 0 or code == 0) else output.strip()
    }

def list_versions(app_id, bundle_id=None):
    """
    Fetches available external version IDs for an app.
    """
    args = ["list-versions"]
    if app_id:
        args.extend(["-i", str(app_id)])
    elif bundle_id:
        args.extend(["-b", str(bundle_id)])
    args.append("--purchase")
    
    code, stdout, stderr = run_ipatool(args, timeout=60)
    output = f"{stdout}\n{stderr}"
    
    # Extract version IDs using regex
    version_ids = re.findall(r'"(\d{6,})"', output)
    if not version_ids:
        version_ids = re.findall(r'\b(\d{7,10})\b', output)
    
    # Remove duplicates preserving order
    seen = set()
    unique_ids = []
    for vid in version_ids:
        if vid not in seen:
            seen.add(vid)
            unique_ids.append(vid)
            
    return {
        "success": len(unique_ids) > 0,
        "versions": unique_ids,
        "error": None if unique_ids else output.strip()
    }

def get_version_metadata(app_id, version_id):
    """
    Fetches human readable version metadata (displayVersion, releaseDate).
    """
    args = ["get-version-metadata", "-i", str(app_id), "--external-version-id", str(version_id)]
    code, stdout, stderr = run_ipatool(args, timeout=30)
    output = f"{stdout}\n{stderr}"
    
    display_ver = None
    m_ver = re.search(r'displayVersion=([^\s,]+)', output)
    if m_ver:
        display_ver = m_ver.group(1).strip()
        
    release_date = None
    m_date = re.search(r'releaseDate=([^\s,]+)', output)
    if m_date:
        release_date = m_date.group(1).strip()
        
    return {
        "success": bool(display_ver or code == 0),
        "version_id": version_id,
        "display_version": display_ver or f"ID: {version_id}",
        "release_date": release_date,
        "raw": output.strip()
    }

def start_download_process(app_id, output_path, version_id=None, bundle_id=None):
    """
    Spawns download process and returns the subprocess object for streaming stdout.
    """
    args = [IPATOOL_BIN, "download"]
    if app_id:
        args.extend(["-i", str(app_id)])
    elif bundle_id:
        args.extend(["-b", str(bundle_id)])
    args.extend(["--purchase", "-o", output_path])
    if version_id:
        args.extend(["--external-version-id", str(version_id)])
        
    proc = subprocess.Popen(
        args,
        env=CURRENT_ENV,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    return proc

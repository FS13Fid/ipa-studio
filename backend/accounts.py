import os
import shutil
import json
import subprocess
from .config import IPATOOL_HOME, IPATOOL_BIN, CURRENT_ENV

AUTH_FILES = ["account", "cookies", "login", "keychain-passphrase"]

def get_active_account_info():
    """Returns info about currently authenticated Apple Account, or None if not logged in."""
    if not os.path.isdir(IPATOOL_HOME):
        return None
    
    cmd = [IPATOOL_BIN, "auth", "info", "--format", "json"]
    try:
        proc = subprocess.run(
            cmd,
            env=CURRENT_ENV,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )
        if proc.returncode == 0:
            try:
                data = json.loads(proc.stdout)
                return {
                    "is_logged_in": True,
                    "name": data.get("name", "Apple User"),
                    "email": data.get("email", ""),
                    "dsid": data.get("dsid", ""),
                    "storefront": data.get("storefront", "RUS")
                }
            except Exception:
                # Text output fallback
                lines = proc.stdout.splitlines()
                email = ""
                name = ""
                for line in lines:
                    if "email:" in line.lower():
                        email = line.split(":", 1)[1].strip()
                    elif "name:" in line.lower():
                        name = line.split(":", 1)[1].strip()
                if email:
                    return {
                        "is_logged_in": True,
                        "name": name or "Apple User",
                        "email": email,
                        "dsid": "",
                        "storefront": "RUS"
                    }
        # If exit code != 0, check if login file exists as a fallback check
        login_file = os.path.join(IPATOOL_HOME, "login")
        account_file = os.path.join(IPATOOL_HOME, "account")
        if os.path.exists(login_file) or os.path.exists(account_file):
            return {
                "is_logged_in": False,
                "error": proc.stderr.strip() or "Session expired or invalid"
            }
        return None
    except Exception as e:
        return {"is_logged_in": False, "error": str(e)}

def list_saved_accounts():
    """Returns a list of all saved Apple account folders in ~/.ipatool"""
    if not os.path.isdir(IPATOOL_HOME):
        return []
    
    saved = []
    for item in sorted(os.listdir(IPATOOL_HOME)):
        item_path = os.path.join(IPATOOL_HOME, item)
        if os.path.isdir(item_path):
            # Check if this folder contains account files
            if any(os.path.exists(os.path.join(item_path, f)) for f in ["account", "login", "cookies"]):
                saved.append(item)
    return saved

def get_all_accounts():
    """Returns active account info and list of saved accounts."""
    active = get_active_account_info()
    saved = list_saved_accounts()
    active_email = active.get("email") if active and active.get("is_logged_in") else None
    
    return {
        "active": active,
        "saved": [acc for acc in saved if acc != active_email]
    }

def save_active_account_files(account_email):
    """Moves active files from ~/.ipatool to ~/.ipatool/<account_email>/"""
    if not account_email or not os.path.isdir(IPATOOL_HOME):
        return False
    target_dir = os.path.join(IPATOOL_HOME, account_email)
    os.makedirs(target_dir, exist_ok=True)
    
    for filename in AUTH_FILES:
        src = os.path.join(IPATOOL_HOME, filename)
        if os.path.isfile(src):
            shutil.move(src, os.path.join(target_dir, filename))
    return True

def restore_saved_account_files(account_email):
    """Moves files from ~/.ipatool/<account_email>/ to ~/.ipatool/"""
    source_dir = os.path.join(IPATOOL_HOME, account_email)
    if not os.path.isdir(source_dir):
        return False
    
    for filename in AUTH_FILES:
        src = os.path.join(source_dir, filename)
        if os.path.isfile(src):
            shutil.move(src, os.path.join(IPATOOL_HOME, filename))
    
    try:
        shutil.rmtree(source_dir, ignore_errors=True)
    except Exception:
        pass
    return True

def switch_account(target_account_email):
    """Switches the active account to target_account_email."""
    active = get_active_account_info()
    current_email = active.get("email") if active and active.get("is_logged_in") else None
    
    if current_email == target_account_email:
        return {"success": True, "message": "Already active"}
    
    if current_email:
        save_active_account_files(current_email)
    else:
        # Clear any dangling active files
        for f in AUTH_FILES:
            p = os.path.join(IPATOOL_HOME, f)
            if os.path.isfile(p):
                try: os.remove(p)
                except Exception: pass

    success = restore_saved_account_files(target_account_email)
    if not success:
        return {"success": False, "error": f"Failed to restore {target_account_email}"}
    
    # Verify new account
    new_active = get_active_account_info()
    return {"success": True, "active": new_active}

def delete_saved_account(account_email):
    """Deletes a saved account's files."""
    active = get_active_account_info()
    if active and active.get("email") == account_email:
        # If it's active, revoke and clear
        try:
            subprocess.run([IPATOOL_BIN, "auth", "revoke"], env=CURRENT_ENV, timeout=5)
        except Exception:
            pass
        for f in AUTH_FILES:
            p = os.path.join(IPATOOL_HOME, f)
            if os.path.isfile(p):
                try: os.remove(p)
                except Exception: pass
        return {"success": True, "deleted_active": True}
    
    target_dir = os.path.join(IPATOOL_HOME, account_email)
    if os.path.isdir(target_dir):
        shutil.rmtree(target_dir, ignore_errors=True)
        return {"success": True}
    return {"success": False, "error": "Account not found"}

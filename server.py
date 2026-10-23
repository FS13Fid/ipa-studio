import os
import sys
import json
import time
import queue
import threading
import mimetypes
import plistlib
import subprocess
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import urllib.parse

from backend import config
from backend import accounts
from backend import ipatool
from backend import device
from backend import catalog
from backend import ipa_manager

WEB_DIR = config.PROJECT_ROOT
PORT = 5050

# Global active task registry for SSE notifications
class TaskManager:
    def __init__(self):
        self.subscribers = []
        self.lock = threading.Lock()
        self.tasks = {}

    def subscribe(self):
        q = queue.Queue(maxsize=100)
        with self.lock:
            self.subscribers.append(q)
        return q

    def unsubscribe(self, q):
        with self.lock:
            if q in self.subscribers:
                self.subscribers.remove(q)

    def broadcast(self, event_type, data):
        msg = f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        with self.lock:
            for q in list(self.subscribers):
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    pass

task_manager = TaskManager()

class IPAWebAppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def log_message(self, format, *args):
        if "/api/events" not in args[0] and "/api/status" not in args[0]:
            sys.stdout.write(f"[{time.strftime('%H:%M:%S')}] {args[0]} - {args[1]}\n")

    def send_json(self, data, status_code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length == 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
            return json.loads(raw)
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        # SSE Stream
        if path == "/api/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            q = task_manager.subscribe()
            try:
                self.wfile.write(b": connected\n\n")
                self.wfile.flush()
                while True:
                    msg = q.get(timeout=25)
                    self.wfile.write(msg.encode("utf-8"))
                    self.wfile.flush()
            except (queue.Empty, BrokenPipeError, ConnectionResetError):
                pass
            finally:
                task_manager.unsubscribe(q)
            return

        # API Endpoints
        if path == "/api/status":
            act = accounts.get_active_account_info()
            devs = device.get_connected_devices()
            ipas = ipa_manager.list_downloaded_ipas()
            self.send_json({
                "platform": config.PLATFORM_SUBFOLDER,
                "ipatool_path": config.IPATOOL_BIN,
                "ipatool_ready": os.path.isfile(config.IPATOOL_BIN),
                "idevice_ready": os.path.isfile(config.IDEVICEINSTALLER_BIN),
                "account": act,
                "devices_count": len(devs),
                "devices": devs,
                "ipas_count": len(ipas),
                "settings": config.get_settings()
            })
            return

        elif path == "/api/devices":
            devs = device.get_connected_devices()
            self.send_json({"devices": devs})
            return

        elif path == "/api/accounts":
            self.send_json(accounts.get_all_accounts())
            return

        elif path == "/api/catalog/popular":
            all_apps = catalog.load_apps_list()
            cat = params.get("category", [None])[0]
            query = params.get("q", [None])[0]

            filtered = all_apps
            if cat and cat != "all":
                filtered = [a for a in filtered if a["category"] == cat]
            if query:
                q_low = query.lower()
                filtered = [a for a in filtered if q_low in a["name"].lower() or q_low == a["id"]]

            limit = int(params.get("limit", [100])[0])
            offset = int(params.get("offset", [0])[0])
            page_slice = filtered[offset:offset+limit]

            self.send_json({
                "total": len(filtered),
                "offset": offset,
                "limit": limit,
                "apps": page_slice
            })
            return

        elif path == "/api/catalog/custom":
            self.send_json(catalog.load_custom_apps())
            return

        elif path == "/api/catalog/purchases":
            all_years = params.get("all_years", ["true"])[0].lower() == "true"
            since_year = params.get("since_year", [None])[0]
            res = ipatool.list_purchases(all_years=all_years, since_year=since_year)
            self.send_json(res)
            return

        elif path == "/api/search" or path == "/api/appstore/search":
            q = params.get("q", [""])[0]
            limit = int(params.get("limit", [20])[0])
            if not q:
                self.send_json({"results": []})
                return
            res = ipatool.search_appstore(q, limit=limit)
            self.send_json(res)
            return

        elif path == "/api/versions":
            app_id = params.get("app_id", [None])[0]
            if not app_id:
                self.send_json({"error": "app_id required"}, 400)
                return
            res = ipatool.list_versions(app_id)
            self.send_json(res)
            return

        elif path == "/api/library":
            self.send_json(ipa_manager.list_downloaded_ipas())
            return

        elif path == "/api/settings":
            self.send_json(config.get_settings())
            return

        # Direct file download of an IPA
        elif path.startswith("/download-ipa/"):
            filename = urllib.parse.unquote(path.replace("/download-ipa/", ""))
            safe_name = os.path.basename(filename)
            filepath = os.path.join(config.APPS_DIR, safe_name)
            if os.path.isfile(filepath):
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", f'attachment; filename="{safe_name}"')
                self.send_header("Content-Length", str(os.path.getsize(filepath)))
                self.end_headers()
                with open(filepath, "rb") as f:
                    while chunk := f.read(64 * 1024):
                        self.wfile.write(chunk)
                return
            else:
                self.send_error(404, "File not found")
                return

        # Fallback to static web files
        super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self.read_json_body()

        if path == "/api/auth/login" or path == "/api/appstore/login":
            email = body.get("email")
            password = body.get("password")
            auth_code = body.get("auth_code")
            keychain_kp = body.get("keychain_passphrase")
            if not email or not password:
                self.send_json({"success": False, "error": "Email and password are required"}, 400)
                return
            res = ipatool.login(email, password, auth_code=auth_code, keychain_passphrase=keychain_kp)
            task_manager.broadcast("auth_change", res)
            self.send_json(res)
            return

        elif path == "/api/auth/revoke":
            res = ipatool.revoke()
            task_manager.broadcast("auth_change", {"logged_out": True})
            self.send_json(res)
            return

        elif path == "/api/accounts/switch":
            email = body.get("email")
            if not email:
                self.send_json({"success": False, "error": "Email required"}, 400)
                return
            res = accounts.switch_account(email)
            task_manager.broadcast("auth_change", res)
            self.send_json(res)
            return

        elif path == "/api/download" or path == "/api/appstore/download":
            app_id = body.get("app_id")
            bundle_id = body.get("bundle_id")
            version_id = body.get("version_id")
            app_name = body.get("app_name") or f"App_{bundle_id or app_id}"

            safe_name = "".join(c for c in app_name if c.isalnum() or c in " ._-").strip()
            if not safe_name: safe_name = f"App_{bundle_id or app_id}"
            out_filename = f"{safe_name}.ipa"
            out_path = os.path.join(config.APPS_DIR, out_filename)

            def download_worker():
                task_id = f"dl_{int(time.time()*1000)}"
                task_manager.broadcast("task_start", {
                    "id": task_id,
                    "title": f"Скачивание: {app_name}",
                    "type": "download"
                })
                
                proc = ipatool.start_download_process(app_id, out_path, version_id=version_id, bundle_id=bundle_id)
                for line in proc.stdout:
                    line = line.strip()
                    if line:
                        task_manager.broadcast("task_log", {
                            "id": task_id,
                            "line": line
                        })
                proc.wait()
                success = proc.returncode == 0 and os.path.isfile(out_path)
                task_manager.broadcast("task_complete", {
                    "id": task_id,
                    "success": success,
                    "filename": out_filename,
                    "message": "Загрузка завершена!" if success else "Ошибка при загрузке IPA"
                })

            threading.Thread(target=download_worker, daemon=True).start()
            self.send_json({"success": True, "message": "Download task queued", "filename": out_filename})
            return

        elif path == "/api/install-catalog-app" or path == "/api/install":
            bundle_id = body.get("bundle_id")
            udid = body.get("udid")

            # Auto-detect UDID if not specified
            if not udid:
                devs = device.get_connected_devices()
                if devs:
                    udid = devs[0]["udid"]
                else:
                    self.send_json({"status": "error", "message": "iPhone не подключен к компьютеру по USB!"}, 400)
                    return

            manifest_path = os.path.join(config.PROJECT_ROOT, "manifests", f"{bundle_id}.plist")
            download_url = None
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, "rb") as mf:
                        m_plist = plistlib.load(mf)
                        download_url = m_plist["items"][0]["assets"][0]["url"]
                except Exception:
                    pass

            target_ipa = os.path.join(config.APPS_DIR, f"{bundle_id}.ipa")

            def catalog_install_worker():
                task_id = f"inst_{int(time.time()*1000)}"
                task_manager.broadcast("task_start", {
                    "id": task_id,
                    "title": f"Установка: {bundle_id}",
                    "type": "install"
                })

                if not os.path.exists(target_ipa) or os.path.getsize(target_ipa) < 10000:
                    if download_url:
                        task_manager.broadcast("task_log", {"id": task_id, "line": "Загрузка IPA архива с GitHub..."})
                        subprocess.run(["curl", "-L", "-s", "--retry", "2", "-o", target_ipa, download_url])

                if not os.path.exists(target_ipa) or os.path.getsize(target_ipa) < 10000:
                    task_manager.broadcast("task_complete", {
                        "id": task_id,
                        "success": False,
                        "message": "Не удалось скачать файл IPA"
                    })
                    return

                task_manager.broadcast("task_log", {"id": task_id, "line": f"Установка на iPhone ({udid[:8]}...)..."})
                proc = device.start_install_process(udid, target_ipa)
                for line in proc.stdout:
                    line = line.strip()
                    if line:
                        task_manager.broadcast("task_log", {"id": task_id, "line": line})
                proc.wait()

                success = proc.returncode == 0
                if not success:
                    # Upgrade attempt
                    task_manager.broadcast("task_log", {"id": task_id, "line": "Обновление существующего приложения..."})
                    upgrade_args = [config.IDEVICEINSTALLER_BIN] + device.get_air_args() + ["--udid", udid, "upgrade", target_ipa]
                    up_proc = subprocess.Popen(
                        upgrade_args,
                        env=config.CURRENT_ENV,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True
                    )
                    for line in up_proc.stdout:
                        if line.strip():
                            task_manager.broadcast("task_log", {"id": task_id, "line": line.strip()})
                    up_proc.wait()
                    success = up_proc.returncode == 0

                task_manager.broadcast("task_complete", {
                    "id": task_id,
                    "success": success,
                    "message": "Приложение успешно установлено на iPhone!" if success else "Ошибка ideviceinstaller"
                })

            threading.Thread(target=catalog_install_worker, daemon=True).start()
            self.send_json({"status": "success", "message": "Установка запущена"})
            return

        elif path == "/api/devices/install":
            udid = body.get("udid")
            ipa_filename = body.get("filename")
            if not udid or not ipa_filename:
                self.send_json({"success": False, "error": "UDID and filename required"}, 400)
                return
            
            ipa_path = os.path.join(config.APPS_DIR, os.path.basename(ipa_filename))
            if not os.path.isfile(ipa_path):
                self.send_json({"success": False, "error": "IPA file does not exist"}, 404)
                return

            def install_worker():
                task_id = f"inst_{int(time.time()*1000)}"
                task_manager.broadcast("task_start", {
                    "id": task_id,
                    "title": f"Установка на устройство: {ipa_filename}",
                    "type": "install"
                })

                proc = device.start_install_process(udid, ipa_path)
                for line in proc.stdout:
                    line = line.strip()
                    if line:
                        task_manager.broadcast("task_log", {
                            "id": task_id,
                            "line": line
                        })
                proc.wait()
                
                success = proc.returncode == 0
                task_manager.broadcast("task_complete", {
                    "id": task_id,
                    "success": success,
                    "message": "Установка успешно выполнена!" if success else "Ошибка установки приложения на устройство."
                })

            threading.Thread(target=install_worker, daemon=True).start()
            self.send_json({"success": True, "message": "Installation task queued"})
            return

        elif path == "/api/settings":
            updated = config.update_settings(body)
            self.send_json({"success": True, "settings": updated})
            return

        self.send_json({"error": "Not found"}, 404)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self.read_json_body()

        if path == "/api/accounts":
            email = body.get("email")
            if not email:
                self.send_json({"success": False, "error": "Email required"}, 400)
                return
            res = accounts.delete_saved_account(email)
            self.send_json(res)
            return

        elif path == "/api/library":
            filename = body.get("filename")
            if not filename:
                self.send_json({"success": False, "error": "Filename required"}, 400)
                return
            res = ipa_manager.delete_ipa(filename)
            self.send_json(res)
            return

        self.send_json({"error": "Not found"}, 404)

def run_server(port=PORT):
    server_address = ("0.0.0.0", port)
    httpd = ThreadingHTTPServer(server_address, IPAWebAppHandler)
    print(f"\n=======================================================")
    print(f"🍏 IPA Studio Desktop Server running at http://localhost:{port}")
    print(f"📱 Connect iPhone via USB cable to this computer to install IPAs")
    print(f"=======================================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.server_close()

if __name__ == "__main__":
    p = PORT
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        p = int(sys.argv[1])
    run_server(p)

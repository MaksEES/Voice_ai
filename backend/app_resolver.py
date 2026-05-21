import os
import re
import subprocess
import json
import threading
from difflib import SequenceMatcher

RU_ALIASES = {
    "телеграм": "telegram",
    "телеграмм": "telegram",
    "дискорд": "discord",
    "вайбер": "viber",
    "ватсап": "whatsapp",
    "ватсапп": "whatsapp",
    "скайп": "skype",
    "хром": "chrome",
    "гугл хром": "google chrome",
    "яндекс браузер": "yandex",
    "яндекс": "yandex",
    "опера": "opera",
    "фаерфокс": "firefox",
    "мозилла": "firefox",
    "ворд": "word",
    "эксель": "excel",
    "повер поинт": "powerpoint",
    "пауэрпоинт": "powerpoint",
    "аутлук": "outlook",
    "ван ноут": "onenote",
    "уаннот": "onenote",
    "вижуал студио": "visual studio",
    "вс код": "visual studio code",
    "vs code": "visual studio code",
    "стим": "steam",
    "эпик геймс": "epic games",
    "эпик": "epic games",
    "спотифай": "spotify",
    "зум": "zoom",
    "тимс": "teams",
    "тимз": "teams",
    "обс": "obs studio",
    "фотошоп": "photoshop",
    "иллюстратор": "illustrator",
    "проводник": "explorer",
    "диспетчер задач": "taskmgr",
    "терминал": "terminal",
    "командная строка": "cmd",
    "пейнт": "paint",
    "ножницы": "snipping tool",
    "настройки": "settings",
    "параметры": "settings",
    "магазин": "microsoft store",
    "почта": "mail",
    "погода": "weather",
    "часы": "clock",
    "камера": "camera",
    "запись голоса": "voice recorder",
    "дота 2": "dota 2",
    "осу":"Osu!",
    "кс 2": "Counter-Strike 2",
    "cs2": "Counter-Strike 2",
    "виндхоук": "windhawk",
    "браузерді": "chrome",
    "блокнотты": "notepad",
    "калькуляторды": "calculator",
    "ойындар": "steam",
    "сурет": "paint",
    "пошта": "mail",
    "ауа райы": "weather",
    "сағат": "clock",
    "камераны": "camera",
    "терминалды": "terminal",
}


class AppResolver:
    def __init__(self):
        self._index = []
        self._index_ready = False
        self._lock = threading.Lock()
        t = threading.Thread(target=self._bg_refresh, daemon=True)
        t.start()

    def _bg_refresh(self):
        self.refresh_index()

    def refresh_index(self):
        new_index = []
        self._scan_start_menu(new_index)
        self._scan_uwp_apps(new_index)
        self._scan_steam_games(new_index)

        seen = set()
        deduped = []
        for app in new_index:
            key = app["name_lower"]
            if key not in seen:
                seen.add(key)
                deduped.append(app)

        with self._lock:
            self._index = deduped
            self._index_ready = True

    def _scan_start_menu(self, index_list):
        dirs = []
        programdata = os.environ.get("PROGRAMDATA", "")
        appdata = os.environ.get("APPDATA", "")

        if programdata:
            dirs.append(os.path.join(programdata, "Microsoft", "Windows", "Start Menu", "Programs"))
        if appdata:
            dirs.append(os.path.join(appdata, "Microsoft", "Windows", "Start Menu", "Programs"))

        for base in dirs:
            if not os.path.isdir(base):
                continue
            for root, _, files in os.walk(base):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in (".lnk", ".exe"):
                        full_path = os.path.join(root, f)
                        name = os.path.splitext(f)[0]
                        index_list.append({
                            "name": name,
                            "name_lower": name.lower(),
                            "path": full_path,
                            "type": "lnk" if ext == ".lnk" else "exe",
                        })

    def _scan_uwp_apps(self, index_list):
        try:
            result = subprocess.run(
                [
                    "powershell", "-NoProfile", "-NonInteractive",
                    "-Command", "Get-StartApps | ConvertTo-Json -Compress"
                ],
                capture_output=True, text=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return

            apps = json.loads(result.stdout)
            if isinstance(apps, dict):
                apps = [apps]

            for app in apps:
                name = app.get("Name", "")
                app_id = app.get("AppID", "")
                if not name or not app_id:
                    continue
                if "!" in app_id:
                    index_list.append({
                        "name": name,
                        "name_lower": name.lower(),
                        "path": app_id,
                        "type": "uwp",
                    })
        except Exception as e:
            print(f"[AppResolver] UWP scan error: {e}")

    def _scan_steam_games(self, index_list):
        steam_paths = self._find_steam_libraries()
        game_count = 0

        for lib_path in steam_paths:
            steamapps = os.path.join(lib_path, "steamapps")
            if not os.path.isdir(steamapps):
                continue

            try:
                for f in os.listdir(steamapps):
                    if not f.startswith("appmanifest_") or not f.endswith(".acf"):
                        continue

                    acf_path = os.path.join(steamapps, f)
                    app_id, name = self._parse_acf(acf_path)

                    if app_id and name:
                        index_list.append({
                            "name": name,
                            "name_lower": name.lower(),
                            "path": app_id,
                            "type": "steam",
                        })
                        game_count += 1
            except Exception as e:
                print(f"[AppResolver] Steam scan error in {steamapps}: {e}")

        pass

    def _find_steam_libraries(self):
        libraries = []

        steam_default = os.path.join(
            os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"),
            "Steam"
        )

        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")
            steam_default, _ = winreg.QueryValueEx(key, "InstallPath")
            winreg.CloseKey(key)
        except Exception:
            pass

        if not os.path.isdir(steam_default):
            return libraries

        libraries.append(steam_default)

        vdf_path = os.path.join(steam_default, "config", "libraryfolders.vdf")
        if not os.path.isfile(vdf_path):
            return libraries

        try:
            with open(vdf_path, "r", encoding="utf-8") as f:
                content = f.read()

            for match in re.finditer(r'"path"\s+"([^"]+)"', content):
                lib_path = match.group(1).replace("\\\\", "\\")
                if os.path.isdir(lib_path) and lib_path not in libraries:
                    libraries.append(lib_path)
        except Exception as e:
            print(f"[AppResolver] Error reading libraryfolders.vdf: {e}")

        return libraries

    def _parse_acf(self, acf_path):
        try:
            with open(acf_path, "r", encoding="utf-8") as f:
                content = f.read()

            appid_match = re.search(r'"appid"\s+"(\d+)"', content)
            name_match = re.search(r'"name"\s+"([^"]+)"', content)

            if appid_match and name_match:
                appid = appid_match.group(1)
                name = name_match.group(1)
                skip_keywords = ["redistribut", "steamworks", "proton", "steam linux"]
                if any(kw in name.lower() for kw in skip_keywords):
                    return None, None
                return appid, name
        except Exception:
            pass
        return None, None

    def _try_where(self, name):
        for query in (name, f"{name}.exe"):
            try:
                result = subprocess.run(
                    ["where.exe", query],
                    capture_output=True, text=True, timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip().split("\n")[0].strip()
            except Exception:
                pass
        return None

    def resolve(self, query):
        with self._lock:
            index = list(self._index)

        query_lower = query.lower().strip()

        resolved_alias = RU_ALIASES.get(query_lower)
        queries = [query_lower]
        if resolved_alias:
            queries.insert(0, resolved_alias.lower())

        for q in queries:
            for app in index:
                if app["name_lower"] == q:
                    return app

            candidates = []
            for app in index:
                if q in app["name_lower"] or app["name_lower"] in q:
                    candidates.append(app)
            if candidates:
                candidates.sort(key=lambda a: abs(len(a["name_lower"]) - len(q)))
                return candidates[0]

            best = None
            best_score = 0
            for app in index:
                score = SequenceMatcher(None, q, app["name_lower"]).ratio()
                if score > best_score:
                    best_score = score
                    best = app
            if best and best_score >= 0.55:
                print(f"[AppResolver] Fuzzy match: '{q}' → '{best['name']}' ({best_score:.0%})")
                return best

        # 4. Fallback: where.exe
        path = self._try_where(query_lower)
        if not path and resolved_alias:
            path = self._try_where(resolved_alias)
        if path:
            return {
                "name": query,
                "name_lower": query_lower,
                "path": path,
                "type": "exe",
            }

        return None

    def launch(self, query):
        if not self._index_ready:
            import time
            for _ in range(20):
                if self._index_ready:
                    break
                time.sleep(0.25)

        app = self.resolve(query)
        if not app:
            return False, f"Приложение \u00ab{query}\u00bb не найдено."

        try:
            if app["type"] == "uwp":
                subprocess.Popen(
                    ["explorer.exe", f"shell:AppsFolder\\{app['path']}"],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            elif app["type"] == "steam":
                import webbrowser
                webbrowser.open(f"steam://rungameid/{app['path']}")
            else:
                os.startfile(app["path"])

            print(f"[AppResolver] Launched: {app['name']} ({app['type']}: {app['path']})")
            return True, f"Запускаю {app['name']}."

        except Exception as e:
            print(f"[AppResolver] Launch error {app['name']}: {e}")
            return False, f"Ошибка при запуске {app['name']}: {e}"

    def get_app_list(self):
        with self._lock:
            return [app["name"] for app in self._index]

    def get_app_count(self):
        with self._lock:
            return len(self._index)

import webview
import os
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN_WARNING"] = "1"
import sys
import subprocess
import threading
import time
import requests
import base64
from nlp_engine import NLPProcessor
from database import init_db, create_session, add_message, update_session_title, get_all_sessions, get_session_messages, delete_session, get_command_frequencies
from app_resolver import AppResolver

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

try:
    import speech_recognition as sr
except ImportError:
    sr = None
    
_whisper_model = None
_silero_ru_model = None 
WHISPER_PROMPTS = {
    "ru": (
        "Макс, открой браузер. Открой калькулятор. "
        "Напечатай текст. Что на экране? Закрой окно. "
        "Найди на ютубе. Поищи в интернете. "
        "Открой блокнот. Открой музыку. Открой загрузки. "
        "Открой фото. Открой картинки."
    ),
    "en": (
        "Max, open browser. Open calculator. "
        "Type text. What's on the screen? Close window. "
        "Search on YouTube. Search the internet. "
        "Open notepad. Open music. Open downloads. "
        "Open photos. Open pictures."
    ),
    "kk": (
        "Макс, браузерді аш. Калькуляторды аш. "
        "Мәтін жаз. Экранда не бар? Терезені жап. "
        "YouTube-тен іздеу. Интернеттен іздеу. "
        "Блокнотты аш. Музыканы аш. Жүктеулерді аш."
    ),
}

WHISPER_CORRECTIONS = {
    "ru": {
        "макса": "макс",
        "максим": "макс",
        "max": "макс",
        "максу": "макс",
        "мэкс": "макс",
        "калькулято": "калькулятор",
        "блокно": "блокнот",
        "блакнот": "блокнот",
        "гугло": "гугл",
        "гугол": "гугл",
        "закрыть": "закрой",
        "открыть": "открой",
        "запустить": "запусти",
        "включить": "включи",
        "найти": "найди",
        "напечатать": "напечатай",
        "загрузка": "загрузки",
        "музыка": "музыку",
        "бразуер": "браузер",
        "бруазер": "браузер",
        "брауер": "браузер",
        "ютуб": "ютубе",
        "ютюб": "ютубе",
    },
    "en": {
        "max": "макс",
        "macs": "макс",
        "marks": "макс",
        "maks": "макс",
        "opn": "open",
        "brawser": "browser",
        "calculater": "calculator",
    },
    "kk": {
        "макс": "макс",
        "максе": "макс",
        "мақс": "макс",
        "ашу": "аш",
        "жабу": "жап",
    },
}

WAKE_WORDS = {
    "ru": ["макс"],
    "en": ["max", "macs", "marks"],
    "kk": ["макс", "мақс"],
}

def _correct_text(text, lang="ru"):
    corrections = WHISPER_CORRECTIONS.get(lang, WHISPER_CORRECTIONS["ru"])
    words = text.split()
    corrected = []
    for word in words:
        corrected.append(corrections.get(word, word))
    return " ".join(corrected)

def _detect_wake_word(text_clean, lang=None):
    langs_to_check = [lang] if lang and lang in WAKE_WORDS else WAKE_WORDS.keys()
    for check_lang in langs_to_check:
        for ww in WAKE_WORDS[check_lang]:
            if ww in text_clean:
                parts = text_clean.split(ww, 1)
                rest = parts[1].strip() if len(parts) > 1 else ""
                return True, rest
    return False, ""

"""Оптимизирование под каждый пк"""
def _load_model(model_size, device, compute_type):
    from faster_whisper import WhisperModel
    return WhisperModel(model_size, device=device, compute_type=compute_type)

def _init_whisper():
    global _whisper_model
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("[Whisper] Библиотека faster_whisper не установлена!")
        _whisper_model = None
        return

    device_chain = [
        ("cuda", "float16",      "CUDA GPU (float16)"),
        ("cuda", "int8_float16", "CUDA GPU (int8)"),
        ("cpu",  "int8",         "CPU (int8)"),
    ]

    for device, compute_type, label in device_chain:
        try:
            print(f"[Whisper] Пробую large-v3-turbo: {label}...")
            _whisper_model = _load_model("large-v3-turbo", device, compute_type)
            print(f"[Whisper] ✓ large-v3-turbo загружено: {label}")
            return
        except Exception as e:
            print(f"[Whisper] ✗ {label}: {e}")

    print("[Whisper] ОШИБКА: Не удалось загрузить модель")
    _whisper_model = None

_audio_cache = {}
_audio_cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".audio_cache")
os.makedirs(_audio_cache_dir, exist_ok=True)

def _load_audio_cache():
    global _audio_cache
    try:
        for f in os.listdir(_audio_cache_dir):
            if f.endswith(".b64"):
                key = f[:-4]
                with open(os.path.join(_audio_cache_dir, f), "r", encoding="utf-8") as fh:
                    _audio_cache[key] = fh.read()
        pass
    except Exception as e:
        print(f"[AudioCache] Ошибка загрузки: {e}")

def _save_to_audio_cache(text, audio_b64):
    import hashlib
    key = hashlib.md5(text.encode()).hexdigest()
    _audio_cache[key] = audio_b64
    try:
        with open(os.path.join(_audio_cache_dir, f"{key}.b64"), "w", encoding="utf-8") as fh:
            fh.write(audio_b64)
    except Exception:
        pass

def _get_from_audio_cache(text):
    import hashlib
    key = hashlib.md5(text.encode()).hexdigest()
    return _audio_cache.get(key)

_load_audio_cache()


class API:
    def __init__(self):
        self.nlp = NLPProcessor()
        self.engine = True if pyttsx3 else None
        self.force_stop = False
        self.is_awake = False
        self.current_session_id = None
        self.current_language = None 
        self.detected_language = "ru"  
        init_db()
        self.app_resolver = AppResolver()
        self._pyaudio_instance = None
        self._audio_stream = None
        threading.Thread(target=self._preload_common_audio, daemon=True).start()

    def stop_listening(self):
        self.force_stop = True

    def set_awake(self):
        self.is_awake = True

    def set_language(self, lang_code):
        if lang_code in ("ru", "en", "kk", None, "auto"):
            self.current_language = None if lang_code == "auto" else lang_code
            print(f"[Lang] Язык установлен: {self.current_language or 'авто'}")
            return {"status": "ok", "language": self.current_language or "auto"}
        return {"status": "error", "message": f"Неизвестный язык: {lang_code}"}

    def get_language(self):
        return {"current": self.current_language or "auto", "detected": self.detected_language}

    def speak(self, text):
        if not pyttsx3:
            return
  
        def _speak():
            try:
                engine = pyttsx3.init()
                voices = engine.getProperty('voices')
                for voice in voices:
                    if "russian" in voice.name.lower():
                        engine.setProperty('voice', voice.id)
                        break
                engine.say(text)
                engine.runAndWait()
                del engine
            except Exception as e:
                print(f"Speak Error: {e}")
                
        threading.Thread(target=_speak, daemon=True).start()

    def _play_audio_locally(self, audio_base64):
        def _play():
            try:
                import tempfile
                audio_bytes = base64.b64decode(audio_base64)
                temp_path = os.path.join(tempfile.gettempdir(), "max_voice.mp3")
                with open(temp_path, "wb") as f:
                    f.write(audio_bytes)
                if sys.platform == "win32":
                    subprocess.run(
                        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                         f'Add-Type -AssemblyName presentationCore;'
                         f'$p = New-Object System.Windows.Media.MediaPlayer;'
                         f'$p.Open([uri]"{temp_path}");'
                         f'$p.Play();'
                         f'Start-Sleep -Milliseconds 500;'
                         f'while($p.Position -lt $p.NaturalDuration.TimeSpan){{Start-Sleep -Milliseconds 100}};'
                         f'$p.Close()'],
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        timeout=30,
                    )
            except Exception as e:
                print(f"[LocalPlay] Ошибка: {e}")
        threading.Thread(target=_play, daemon=True).start()

    def _get_silero_audio(self, text):
        cached = _get_from_audio_cache(text)
        if cached:
            print(f"[AudioCache] HIT: {text[:40]}...")
            return cached

        import re
        import tempfile
        import subprocess
        import os

        # Проверка на казахский язык (специфичные буквы)
        is_kazakh = bool(re.search(r"[әіңғүұқөһӘІҢҒҮҰҚӨҺ]", text))
        # Проверка на английский (есть латиница, нет кириллицы)
        is_english = bool(re.search(r"[a-zA-Z]", text)) and not bool(re.search(r"[а-яА-ЯёЁ]", text))

        if is_kazakh or is_english:
            voice = "kk-KZ-DauletNeural" if is_kazakh else "en-US-GuyNeural"
            try:
                temp_path = os.path.join(tempfile.gettempdir(), f"edge_tts_{hash(text)}.mp3")
                cmd = ["edge-tts", "--text", text, "--voice", voice, "--write-media", temp_path]
                kwargs = {}
                if sys.platform == "win32":
                    kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                
                subprocess.run(cmd, check=True, **kwargs)
                
                with open(temp_path, "rb") as f:
                    audio_b64 = base64.b64encode(f.read()).decode('utf-8')
                
                try:
                    os.remove(temp_path)
                except:
                    pass
                    
                _save_to_audio_cache(text, audio_b64)
                return audio_b64
            except Exception as e:
                print(f"[Edge-TTS] Ошибка: {e}")
                return None

        try:
            import io
            import time as _time
            from scipy.io import wavfile
            from silero import silero_tts
            import torch
            import numpy as np
            
            t0 = _time.time()
            global _silero_ru_model
            if '_silero_ru_model' not in globals() or _silero_ru_model is None:
                pass  # print("[Silero] Загрузка модели v5_5_ru...")
                _silero_ru_model, _ = silero_tts(language='ru', speaker='v5_5_ru')
                device = torch.device('cpu')
                _silero_ru_model.to(device)

            audio_tensor = _silero_ru_model.apply_tts(text=text, speaker='aidar', sample_rate=24000)
            
            audio_np = audio_tensor.cpu().numpy()
            audio_buf = io.BytesIO()
            wavfile.write(audio_buf, 24000, audio_np)
            
            audio_b64 = base64.b64encode(audio_buf.getvalue()).decode('utf-8')
            _save_to_audio_cache(text, audio_b64)
            return audio_b64
        except Exception as e:
            pass  # print(f"[Silero] Ошибка синтеза: {e}")
            return None
    def _preload_common_audio(self):
        common_phrases = [
            "Я слушаю.",
            "Запускаю ваш стандартный браузер. Готов к работе в сети.",
            "Открываю калькулятор. Что будем считать?",
            "Блокнот открыт. Можете записывать.",
            "Открываю вашу галерею.",
            "Открываю папку с музыкой.",
            "Открываю папку загрузок.",
            "I'm listening.",
            "Launching your default browser. Ready to surf.",
            "Opening calculator. What shall we compute?",
            "Notepad is open. You can start writing.",
            "Мен тыңдап тұрмын.",
        ]

        preloaded = 0
        for phrase in common_phrases:
            if _get_from_audio_cache(phrase):
                continue
            try:
                audio = self._get_silero_audio(phrase)
                if audio:
                    preloaded += 1
            except Exception:
                pass
            import time
            time.sleep(0.3)

    """База данных"""
    def create_chat_session(self, title="Новый чат"):
        session_id = create_session(title)
        self.current_session_id = session_id
        return {"session_id": session_id}

    def save_message(self, session_id, sender, text, intent=None):
        msg_id = add_message(session_id, sender, text, intent)
        return {"message_id": msg_id}

    def get_chat_history(self):
        return get_all_sessions()

    def get_chat_messages(self, session_id):
        return get_session_messages(session_id)

    def delete_chat(self, session_id):
        delete_session(session_id)
        return {"status": "ok"}

    def get_word_cloud_data(self):
        return get_command_frequencies()

    """Команды"""
    _HANDLED_INTENTS = {
        "OPEN_BROWSER", "OPEN_CALC", "OPEN_NOTEPAD", "OPEN_PICTURES",
        "OPEN_MUSIC", "OPEN_DOWNLOADS", "YOUTUBE", "SEARCH",
        "VOLUME_UP", "VOLUME_DOWN", "VOLUME_MUTE", "MEDIA_PLAY_PAUSE",
        "MEDIA_NEXT", "MEDIA_PREV", "SYS_SLEEP", "SYS_SHUTDOWN", "SPOTIFY",
        "CREATE_FOLDER", "RENAME_FILE", "DELETE_FILE", "OPEN_FILE"
    }
    _SPLIT_WORDS = [
        " а также ", " а потом ", " потом ", " затем ", " после этого ", " и ещё ", " плюс ",
        " and then ", " then ", " also ", " after that ",
        " содан кейін ", " сонымен қатар ", " сосын ",
    ]

    def handle_command(self, text):
        sub_commands = self._split_commands(text)

        all_responses = []
        last_intent = None

        for cmd in sub_commands:
            result = self._execute_single_command(cmd.strip())
            all_responses.append(result["response"])
            last_intent = result["intent"]

        combined_response = " ".join(all_responses)

        """Сохранение чатов"""
        if self.current_session_id:
            try:
                add_message(self.current_session_id, "user", text, last_intent)
                add_message(self.current_session_id, "bot", combined_response, last_intent)
                session_msgs = get_session_messages(self.current_session_id)
                user_msgs = [m for m in session_msgs if m["sender"] == "user"]
                if len(user_msgs) == 1:
                    update_session_title(self.current_session_id, text[:50])
            except Exception as e:
                print(f"[DB] Ошибка сохранения сообщения: {e}")

        audio_base64 = _get_from_audio_cache(combined_response)
        if audio_base64:
            return {
                "intent": last_intent,
                "response": combined_response,
                "audio_base64": audio_base64,
            }
        else:
            def _bg_tts():
                audio = self._get_silero_audio(combined_response)
                if audio:
                    self._play_audio_locally(audio)
                else:
                    self.speak(combined_response)
            threading.Thread(target=_bg_tts, daemon=True).start()
            return {
                "intent": last_intent,
                "response": combined_response,
                "audio_base64": None,
            }

    def _split_commands(self, text):
        text_lower = text.lower()

        """Мультизадачность для чата"""
        for sep in self._SPLIT_WORDS:
            if sep in text_lower:
                parts = []
                remaining = text
                remaining_lower = text_lower
                while sep in remaining_lower and len(parts) < 3:
                    idx = remaining_lower.index(sep)
                    parts.append(remaining[:idx])
                    remaining = remaining[idx + len(sep):]
                    remaining_lower = remaining_lower[idx + len(sep):]
                parts.append(remaining)
                parts = [p.strip() for p in parts if p.strip()]
                if len(parts) > 1:
                    print(f"[CMD] Мульти-команда ({len(parts)}): {parts}")
                    return parts[:3]

        for conj in [" и ", " and ", " және "]:
            if conj not in text_lower:
                continue
            parts = text_lower.split(conj, 2)
            command_verbs = ["открой", "запусти", "включи", "закрой", "найди",
                           "поищи", "напечатай", "покажи", "загрузи",
                           "open", "launch", "start", "close", "find",
                           "search", "type", "show",
                           "аш", "қос", "жап", "іздеу", "тап", "жаз"]
            valid_parts = []
            for p in parts:
                p = p.strip()
                if any(p.startswith(v) for v in command_verbs):
                    valid_parts.append(p)
                elif valid_parts:
                    last_verb = None
                    for v in command_verbs:
                        if valid_parts[-1].startswith(v):
                            last_verb = v
                            break
                    if last_verb:
                        valid_parts.append(f"{last_verb} {p}")
                    else:
                        valid_parts.append(p)

            if len(valid_parts) > 1:
                print(f"[CMD] Мульти-команда ({len(valid_parts)}): {valid_parts}")
                return valid_parts[:3]

        return [text]

    def _execute_single_command(self, text):
        lang = self.detected_language or "ru"
        intent, original = self.nlp.analyze(text)
        
        history = []
        if self.current_session_id:
            try:
                session_msgs = get_session_messages(self.current_session_id)
                for m in session_msgs[-24:]:
                    role = "user" if m["sender"] == "user" else "assistant"
                    history.append({"role": role, "content": m["text"]})
            except Exception as e:
                print(f"[Memory] Ошибка чтения истории: {e}")
                
        response_text = self.nlp.get_response(intent, original, lang, history=history)

        if intent == "OPEN_BROWSER":
            self.open_browser()
        elif intent == "OPEN_CALC":
            self.open_app('calc.exe')
        elif intent == "OPEN_NOTEPAD":
            self.open_app('notepad.exe')
        elif intent == "OPEN_PICTURES":
            self.open_folder('pictures')
        elif intent == "OPEN_MUSIC":
            self.open_folder('music')
        elif intent == "OPEN_DOWNLOADS":
            self.open_folder('downloads')
        elif intent == "YOUTUBE":
            import urllib.request
            import urllib.parse
            import re
            import webbrowser
            try:
                query_encoded = urllib.parse.quote(original)
                html = urllib.request.urlopen("https://www.youtube.com/results?search_query=" + query_encoded)
                video_ids = re.findall(r"watch\?v=(\S{11})", html.read().decode())
                if video_ids:
                    webbrowser.open("https://www.youtube.com/watch?v=" + video_ids[0])
                else:
                    webbrowser.open("https://www.youtube.com/results?search_query=" + query_encoded)
            except Exception as e:
                webbrowser.open("https://www.youtube.com/")
        elif intent == "SPOTIFY":
            import urllib.parse
            import os
            try:
                query_encoded = urllib.parse.quote(original)
                os.startfile(f"spotify:search:{query_encoded}")
            except Exception as e:
                print(f"[CMD] Ошибка Spotify: {e}")
        elif intent == "VOLUME_UP":
            import pyautogui
            for _ in range(5): pyautogui.press('volumeup')
        elif intent == "VOLUME_DOWN":
            import pyautogui
            for _ in range(5): pyautogui.press('volumedown')
        elif intent == "VOLUME_MUTE":
            import pyautogui
            pyautogui.press('volumemute')
        elif intent == "MEDIA_PLAY_PAUSE":
            import pyautogui
            pyautogui.press('playpause')
        elif intent == "MEDIA_NEXT":
            import pyautogui
            pyautogui.press('nexttrack')
        elif intent == "MEDIA_PREV":
            import pyautogui
            pyautogui.press('prevtrack')
        elif intent == "SYS_SLEEP":
            import os
            os.system("rundll32.exe powrprof.dll,SetSuspendState Sleep")
        elif intent == "SYS_SHUTDOWN":
            import os
            os.system("shutdown /s /t 5")
        elif intent == "SEARCH":
            try:
                from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    results = list(ddgs.text(original, max_results=3))
                if results:
                    snippets = "\n".join([f"- {r.get('title','')}: {r.get('body','')}" for r in results])
                    search_prompt = f"На основе этих данных из интернета:\n{snippets}\n\nКратко и точно ответь на вопрос: {original}"
                    response_text = self.nlp.get_response("AI_THINK", search_prompt, lang)
                else:
                    response_text = f"К сожалению, ничего не нашел по запросу «{original}»."
            except Exception as e:
                print(f"[SEARCH] Ошибка поиска: {e}")
                import webbrowser
                webbrowser.open(f"https://www.google.com/search?q={original}")
                response_text = f"Не удалось выполнить умный поиск, открыл Google."
        elif intent == "CREATE_FOLDER":
            response_text = self.create_folder(original)
        elif intent == "RENAME_FILE":
            response_text = self.rename_file_or_folder(original)
        elif intent == "DELETE_FILE":
            response_text = self.delete_file_or_folder(original)
        elif intent == "OPEN_FILE":
            response_text = self.open_file_by_name(original)

        if intent not in self._HANDLED_INTENTS:
            command = text.lower()
            if any(v in command for v in ["открой", "open", "аш"]):
                result = self.open_app_by_name(command)
                if result:
                    response_text = result
            if any(v in command for v in ["напечатай", "type", "жаз"]):
                result = self.type_text(command)
                if result:
                    response_text = result
            if any(p in command for p in ["что на экране", "what's on screen", "what is on screen", "экранда не бар"]):
                result = self.describe_screen()
                if result:
                    response_text = result
            if any(v in command for v in ["закрой", "close", "жап"]):
                result = self.close_window(command)
                if result:
                    response_text = result

        return {"intent": intent, "response": response_text}

    def _extract_name_from_command(self, text, verbs, object_words):
        t = text.lower().strip()
        for v in verbs:
            if t.startswith(v):
                t = t[len(v):].strip()
                break
        for ow in object_words:
            if t.startswith(ow):
                t = t[len(ow):].strip()
                break
        return t.strip()

    def _resolve_location(self, name):
        base_dir = os.path.expanduser("~")
        onedrive_dir = os.path.join(base_dir, "OneDrive")
        
        def get_path(folder):
            onedrive_path = os.path.join(onedrive_dir, folder)
            if os.path.exists(onedrive_path):
                return onedrive_path
            return os.path.join(base_dir, folder)

        location_map = {
            "на рабочем столе": get_path("Desktop"),
            "on desktop": get_path("Desktop"),
            "в документах": get_path("Documents"),
            "in documents": get_path("Documents"),
            "в загрузках": get_path("Downloads"),
            "in downloads": get_path("Downloads"),
        }
        name_lower = name.lower()
        for keyword, path in location_map.items():
            if keyword in name_lower:
                clean_name = name_lower.replace(keyword, "").strip()
                return clean_name, path
        return name, get_path("Desktop")

    def create_folder(self, text):
        verbs = ["создай", "сделай", "create", "make", "жаса", "құр"]
        objects = ["папку", "папка", "каталог", "директорию", "folder", "directory", "қалта", "новую папку", "новая папка"]
        folder_name = self._extract_name_from_command(text, verbs, objects)
        if not folder_name:
            return "Не удалось понять имя папки."
        folder_name, base_path = self._resolve_location(folder_name)
        if not folder_name:
            return "Не удалось понять имя папки."
        full_path = os.path.join(base_path, folder_name)
        try:
            os.makedirs(full_path, exist_ok=True)
            return f"Папка '{folder_name}' создана в {os.path.basename(base_path)}."
        except Exception as e:
            return f"Ошибка создания папки: {e}"

    def rename_file_or_folder(self, text):
        verbs = ["переименуй", "переназови", "назови", "rename", "атын өзгерт", "қайта ата"]
        objects = ["файл", "папку", "папка", "каталог", "file", "folder", "directory", "файлды", "қалтаны"]
        name_part = self._extract_name_from_command(text, verbs, objects)
        separators = [" в ", " на ", " to ", " into "]
        old_name = None
        new_name = None
        for sep in separators:
            if sep in name_part:
                parts = name_part.split(sep, 1)
                old_name = parts[0].strip()
                new_name = parts[1].strip()
                break
        if not old_name or not new_name:
            return "Не понял старое и новое имя. Скажите: переименуй папку старое в новое."
        new_name_clean, base_path = self._resolve_location(new_name)
        old_name_clean, _ = self._resolve_location(old_name)
        old_name_clean = old_name_clean or old_name
        new_name_clean = new_name_clean or new_name
        old_path = os.path.join(base_path, old_name_clean)
        new_path = os.path.join(base_path, new_name_clean)
        if not os.path.exists(old_path):
            return f"Не найдено: '{old_name_clean}' в {os.path.basename(base_path)}."
        try:
            os.rename(old_path, new_path)
            return f"'{old_name_clean}' переименовано в '{new_name_clean}'."
        except Exception as e:
            return f"Ошибка переименования: {e}"

    def delete_file_or_folder(self, text):
        import shutil
        verbs = ["удали", "убери", "сотри", "delete", "remove", "erase", "жой", "өшір"]
        objects = ["файл", "папку", "папка", "каталог", "file", "folder", "directory", "файлды", "папканы"]
        target = self._extract_name_from_command(text, verbs, objects)
        if not target:
            return "Не удалось понять, что удалять."
        target, base_path = self._resolve_location(target)
        if not target:
            return "Не удалось понять, что удалять."
        full_path = os.path.join(base_path, target)
        if not os.path.exists(full_path):
            return f"Не найдено: '{target}' в {os.path.basename(base_path)}."
        try:
            if os.path.isdir(full_path):
                shutil.rmtree(full_path)
            else:
                os.remove(full_path)
            return f"'{target}' удалено."
        except Exception as e:
            return f"Ошибка удаления: {e}"

    def open_file_by_name(self, text):
        from difflib import SequenceMatcher
        verbs = ["открой", "запусти", "покажи", "open", "launch", "show", "аш", "қос"]
        objects = ["файл", "документ", "file", "document", "файлды", "құжат"]
        target = self._extract_name_from_command(text, verbs, objects)
        if not target:
            return "Не понял имя файла."
        target_clean, location = self._resolve_location(target)
        if not target_clean:
            return "Не понял имя файла."
        search_dirs = list(dict.fromkeys([
            location,
            os.path.join(os.path.expanduser("~"), "Desktop"),
            os.path.join(os.path.expanduser("~"), "Documents"),
            os.path.join(os.path.expanduser("~"), "Downloads"),
        ]))
        best_match = None
        best_score = 0
        target_lower = target_clean.lower()
        for search_dir in search_dirs:
            if not os.path.isdir(search_dir):
                continue
            try:
                for entry in os.listdir(search_dir):
                    entry_path = os.path.join(search_dir, entry)
                    if not os.path.isfile(entry_path):
                        continue
                    name_no_ext = os.path.splitext(entry)[0].lower()
                    if target_lower == name_no_ext or target_lower == entry.lower():
                        best_match = entry_path
                        best_score = 1.0
                        break
                    score = SequenceMatcher(None, target_lower, name_no_ext).ratio()
                    if score > best_score and score >= 0.6:
                        best_score = score
                        best_match = entry_path
            except PermissionError:
                continue
            if best_score == 1.0:
                break
        if not best_match:
            return f"Файл '{target_clean}' не найден."
        try:
            os.startfile(best_match)
            return f"Открываю '{os.path.basename(best_match)}'."
        except Exception as e:
            return f"Ошибка открытия файла: {e}"
        
    def open_app_by_name(self, command):
         open_verbs = ["открой", "запусти", "включи", "open", "launch", "start", "run", "аш", "қос", "іске қос"]
         app_name = None
         for verb in open_verbs:
             if verb in command:
                 parts = command.split(verb, 1)
                 if len(parts) > 1 and parts[1].strip():
                     app_name = parts[1].strip()
                     break
         if not app_name:
             return None
         ok, msg = self.app_resolver.launch(app_name)
         return msg
                  
    def type_text(self, command):
         try:
             import pyautogui
             import pyperclip
             import time
             
             parts = command.split("напечатай", 1)
             if len(parts) <= 1:
                 return None
             
             raw_text = parts[1].strip()
             if not raw_text:
                 return None
             
             new_line_first = False
             if raw_text.startswith("с новой строки"):
                 new_line_first = True
                 raw_text = raw_text.replace("с новой строки", "", 1).strip()
             
             punctuation_map = {
                 " точка": ".",
                 " запятая": ",",
                 " вопросительный знак": "?",
                 " вопрос": "?",
                 " восклицательный знак": "!",
                 " двоеточие": ":",
                 " точка с запятой": ";",
                 " тире": " — ",
                 " дефис": "-",
                 " кавычки": "\"",
                 " открыть скобку": "(",
                 " закрыть скобку": ")",
                 " многоточие": "...",
                 " новая строка": "\n",
                 " новый абзац": "\n\n",
             }
             
             text_to_type = raw_text
             for voice_cmd, symbol in punctuation_map.items():
                 text_to_type = text_to_type.replace(voice_cmd, symbol)
             
             special_keys = {
                 "пробел": "space",
                 "энтер": "enter",
                 "таб": "tab",
                 "табуляция": "tab",
                 "удалить": "backspace",
                 "удали": "backspace",
             }
             
             text_lower = text_to_type.lower().strip()
             
             if text_lower in special_keys:
                 pyautogui.press(special_keys[text_lower])
                 return f"Нажато: {text_lower}"
             
             if new_line_first:
                 pyautogui.press('enter')
                 time.sleep(0.05)
             
             pyperclip.copy(text_to_type)
             time.sleep(0.1)
             pyautogui.hotkey('ctrl', 'v')
             return f"Напечатано: {text_to_type}"
             
         except Exception as e:
             print(f"Ошибка при вводе текста: {e}")
             return f"Ошибка при вводе текста: {e}"

    def close_window(self, command):
         try:
             import pyautogui
             import time
             
             cmd = command.lower()
             
             if "вкладку" in cmd or "таб" in cmd:
                 pyautogui.hotkey('alt', 'tab')
                 time.sleep(0.3)
                 pyautogui.hotkey('ctrl', 'w')
                 return "Вкладка закрыта."
             elif "всё" in cmd or "все окна" in cmd:
                 pyautogui.hotkey('alt', 'tab')
                 time.sleep(0.3)
                 pyautogui.hotkey('alt', 'F4')
                 return "Окно закрыто."
             else:
                 pyautogui.hotkey('alt', 'tab')
                 time.sleep(0.3)
                 pyautogui.hotkey('alt', 'F4')
                 return "Окно закрыто."
         except Exception as e:
             print(f"Ошибка при закрытии окна: {e}")
             return f"Ошибка при закрытии: {e}"
             
    def describe_screen(self):
         try:
             import pyautogui
             import io
             import base64 as b64

             screenshot = pyautogui.screenshot()
             buf = io.BytesIO()
             screenshot.save(buf, format="PNG")
             img_b64 = b64.b64encode(buf.getvalue()).decode("utf-8")

             lang = self.detected_language or "ru"
             lang_prompts = {
                 "ru": "Опиши кратко что изображено на экране (2-3 предложения, на русском).",
                 "en": "Briefly describe what is shown on the screen (2-3 sentences, in English).",
                 "kk": "Экранда не бейнеленгенін қысқаша сипатта (2-3 сөйлем, қазақша).",
             }
             prompt_text = lang_prompts.get(lang, lang_prompts["ru"])

             from nlp_engine import _call_openrouter
             result = _call_openrouter(
                 messages=[{
                     "role": "user",
                     "content": [
                         {"type": "text", "text": prompt_text},
                         {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
                     ]
                 }],
                 max_tokens=256,
                 temperature=0.4
             )
             return result.strip()
         except Exception as e:
             print(f"Ошибка при анализе экрана: {e}")
             return f"Я сделал снимок экрана, но произошла ошибка при анализе: {e}"

    def open_folder(self, folder_type):
        try:
            path = ""
            if sys.platform == "win32":
                if folder_type == "pictures": path = os.path.join(os.environ['USERPROFILE'], 'Pictures')
                elif folder_type == "music": path = os.path.join(os.environ['USERPROFILE'], 'Music')
                elif folder_type == "downloads": path = os.path.join(os.environ['USERPROFILE'], 'Downloads')
                if path:
                    os.startfile(path)
            return f"Папка {folder_type} открыта"
        except Exception as e:
            return str(e)


    def open_browser(self):
        import webbrowser
        webbrowser.open('https://google.com')
        return "Браузер открыт"

    def open_app(self, app_name):
        try:
            if sys.platform == "win32":
                os.startfile(app_name)
            else:
                if app_name == "calc.exe": app_name = "gnome-calculator"
                elif app_name == "notepad.exe": app_name = "gedit"
                subprocess.Popen([app_name])
            return f"{app_name} запущен"
        except Exception as e:
            return f"Ошибка: {str(e)}"

    def _ensure_audio_stream(self):
        """Persistent audio stream — opens once, reuses across listen_voice() calls"""
        import pyaudio
        if self._audio_stream is not None:
            try:
                if self._audio_stream.is_active():
                    return self._audio_stream
            except Exception:
                pass
            self._close_audio_stream()

        if self._pyaudio_instance is None:
            self._pyaudio_instance = pyaudio.PyAudio()

        self._audio_stream = self._pyaudio_instance.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            frames_per_buffer=1024
        )
        print("[Audio] Стрим микрофона открыт")
        return self._audio_stream

    def _close_audio_stream(self):
        if self._audio_stream:
            try:
                self._audio_stream.stop_stream()
                self._audio_stream.close()
            except Exception:
                pass
            self._audio_stream = None
        if self._pyaudio_instance:
            try:
                self._pyaudio_instance.terminate()
            except Exception:
                pass
            self._pyaudio_instance = None
        print("[Audio] Стрим микрофона закрыт")

    def listen_voice(self):
        import numpy as np
        import time
        import math
        import string

        CHUNK = 1024
        RATE = 16000
        SILENCE_THRESHOLD = 300
        SILENCE_DURATION = 1.0 

        try:
            stream = self._ensure_audio_stream()
        except Exception as e:
            return {"status": "error", "message": f"Ошибка микрофона: {str(e)}"}

        try:
            self.force_stop = False

            while not getattr(self, "force_stop", False):
                # Flush stale audio from buffer before each recording cycle
                try:
                    while stream.get_read_available() > CHUNK:
                        stream.read(CHUNK, exception_on_overflow=False)
                except Exception:
                    pass

                frames = []
                silent_chunks = 0
                speaking = False
                start_time = time.time()
                
                print("Слушаю..." if not hasattr(self, '_listen_count') else ".", end="" if hasattr(self, '_listen_count') else "\n", flush=True)
                self._listen_count = getattr(self, '_listen_count', 0) + 1
                if self._listen_count % 10 == 0:
                    print(f"\n[Фоновое прослушивание активно, цикл #{self._listen_count}]")
                
                def get_rms(data):
                    count = len(data) / 2
                    format = "%dh" % (count)
                    import struct
                    shorts = struct.unpack(format, data)
                    sum_squares = 0.0
                    for sample in shorts:
                        n = sample * (1.0 / 32768.0)
                        sum_squares += n * n
                    return math.sqrt( sum_squares / count ) * 32768.0

                while not getattr(self, "force_stop", False):
                     try:
                         data = stream.read(CHUNK, exception_on_overflow=False)
                     except Exception:
                         continue
                     rms = get_rms(data)
                     
                     is_speech = rms > SILENCE_THRESHOLD
                     
                     if is_speech:
                         speaking = True
                         silent_chunks = 0
                         frames.append(data)
                     elif speaking:
                         frames.append(data)
                         silent_chunks += 1
                         if silent_chunks > int(RATE / CHUNK * SILENCE_DURATION):
                             break

                     if time.time() - start_time > 3 and not speaking:
                         break
                     elif time.time() - start_time > 15:
                         break
                         
                if getattr(self, "force_stop", False):
                     return {"status": "ignore", "text": ""}
                         
                if not frames:
                     continue

                audio_data = b''.join(frames)
                
                audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

                # Шумоподавление
                try:
                    import noisereduce as nr
                    audio_np = nr.reduce_noise(y=audio_np, sr=RATE, stationary=False, prop_decrease=0.3)
                except ImportError:
                    pass
                except Exception as e:
                    pass

                whisper_lang = self.current_language
                whisper_prompt = WHISPER_PROMPTS.get(whisper_lang, None) if whisper_lang else "Макс, привет. Max, open browser. Сәлем. Русский. English. Қазақша."

                if _whisper_model is None:
                    print("\n[Загрузка Whisper модели...]")
                    _init_whisper()
                use_model = _whisper_model

                if use_model is None:
                     return {"status": "error", "message": "Не удалось загрузить Whisper"}

                segments_list = []
                t0 = time.time()
                segments, info = use_model.transcribe(
                    audio_np,
                    language=whisper_lang,
                    vad_filter=True,
                    beam_size=5,
                    initial_prompt=whisper_prompt,
                    condition_on_previous_text=False,
                    no_speech_threshold=0.5,
                    compression_ratio_threshold=2.4,
                )
                for segment in segments:
                    segments_list.append(segment.text)
                text = "".join(segments_list).strip()
                
                # Определённый язык
                detected_lang = getattr(info, 'language', 'ru') or 'ru'
                self.detected_language = detected_lang
                
                if detected_lang not in ["ru", "en", "kk"]:
                    continue

                if not text:
                   continue

                command = text.lower()
                command = _correct_text(command, detected_lang)
                
                command_clean = command.translate(str.maketrans('', '', string.punctuation))
                
                if not getattr(self, "is_awake", False):
                     found, rest_command = _detect_wake_word(command_clean, detected_lang)
                     if found:
                          self.is_awake = True
                          if rest_command:
                              return {"status": "success", "text": rest_command, "language": detected_lang}
                          wake_text = "Я слушаю."
                          wake_audio = self._get_silero_audio(wake_text)
                          return {"status": "wake", "text": wake_text, "audio_base64": wake_audio, "language": detected_lang}
                     else:
                          continue
                
                self.is_awake = False
                return {"status": "success", "text": command_clean, "language": detected_lang}

        except Exception as e:
            self._close_audio_stream()
            return {"status": "error", "message": f"Ошибка распознавания: {str(e)}"}

def run_app():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    html_file = os.path.join(project_root, 'frontend', 'index.html')
    api = API()
    window = webview.create_window(
        'Test', 
        html_file, 
        js_api=api,
        width=600, 
        height=850,
        background_color='#070b14'
    )
    webview.start()

if __name__ == '__main__':
    try:
        run_app()
    except Exception as e:
        print("\n" + "="*50)
        print("КРИТИЧЕСКАЯ ОШИБКА ЗАПУСКА:")
        print(e)
        print("="*50)
        input("\nНажмите Enter, чтобы закрыть...")
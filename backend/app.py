import webview
import os
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
import sys
import subprocess
import threading
import time
import requests
import base64
from nlp_engine import NLPProcessor
from database import init_db, create_session, add_message, update_session_title, get_all_sessions, get_session_messages, delete_session, get_command_frequencies

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

try:
    import speech_recognition as sr
except ImportError:
    sr = None
    
_whisper_model = None
"""Исправление лексических ошибок"""
WHISPER_PROMPT = (
    "Макс, открой браузер. Открой калькулятор. "
    "Напечатай текст. Что на экране? Закрой окно. "
    "Найди на ютубе. Поищи в интернете. "
    "Открой блокнот. Открой музыку. Открой загрузки. "
    "Открой фото. Открой картинки."
)

WHISPER_CORRECTIONS = {
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
}
def _correct_text(text):
    words = text.split()
    corrected = []
    for word in words:
        corrected.append(WHISPER_CORRECTIONS.get(word, word))
    return " ".join(corrected)

"""Оптимизирование под каждый пк"""
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
            print(f"[Whisper] Пробую: {label}...")
            _whisper_model = WhisperModel("medium", device=device, compute_type=compute_type)
            print(f"[Whisper] ✓ Загружено: {label}")
            return
        except Exception as e:
            print(f"[Whisper] ✗ {label}: {e}")

    print("[Whisper] ОШИБКА: Не удалось загрузить модель ни одним способом")
    _whisper_model = None

_init_whisper()


class API:
    def __init__(self):
        self.nlp = NLPProcessor()
        self.engine = True if pyttsx3 else None
        self.force_stop = False
        self.is_awake = False
        self.current_session_id = None
        init_db()

    def stop_listening(self):
        self.force_stop = True

    def set_awake(self):
        self.is_awake = True

    def speak(self, text):
        if not pyttsx3:
            return

        """ElevenLabs подключение"""    
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

    def _get_elevenlabs_audio(self, text):
        voice_api_key = os.getenv("Voice_API")
        if not voice_api_key:
            return None
        try:
            url = "https://api.elevenlabs.io/v1/text-to-speech/JBFqnCBsd6RMkjVDRZzb"
            headers = {
                "Accept": "audio/mpeg",
                "Content-Type": "application/json",
                "xi-api-key": voice_api_key.strip('"')
            }
            data = {
                "text": text,
                "model_id": "eleven_multilingual_v2"
            }
            res = requests.post(url, json=data, headers=headers)
            if res.status_code == 200:
                return base64.b64encode(res.content).decode('utf-8')
            else:
                print(f"ElevenLabs API Error: {res.text}")
                return None
        except Exception as e:
            print(f"ElevenLabs Request Error: {e}")
            return None

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
        "OPEN_MUSIC", "OPEN_DOWNLOADS", "YOUTUBE", "SEARCH", "GET_STATS",
    }
    """Совмещение команд"""
    _SPLIT_WORDS = [" а также ", " а потом ", " потом ", " затем ", " после этого ", " и ещё ", " плюс "]

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

        audio_base64 = self._get_elevenlabs_audio(combined_response)
        if not audio_base64:
            self.speak(combined_response)
            
        return {
            "intent": last_intent,
            "response": combined_response,
            "audio_base64": audio_base64
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

        if " и " in text_lower:
            parts = text_lower.split(" и ", 2)
            command_verbs = ["открой", "запусти", "включи", "закрой", "найди",
                           "поищи", "напечатай", "покажи", "загрузи"]
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
        intent, original = self.nlp.analyze(text)
        response_text = self.nlp.get_response(intent, original)

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
            import webbrowser
            webbrowser.open("https://www.youtube.com/")
        elif intent == "SEARCH":
            import webbrowser
            webbrowser.open(f"https://www.google.com/search?q={original}")

        if intent not in self._HANDLED_INTENTS:
            command = text.lower()
            if "открой" in command:
                self.open_app_by_name(command)
            if "напечатай" in command:
                result = self.type_text(command)
                if result:
                    response_text = result
            if "что на экране" in command:
                result = self.describe_screen()
                if result:
                    response_text = result
            if "закрой" in command:
                result = self.close_window(command)
                if result:
                    response_text = result

        return {"intent": intent, "response": response_text}
        
    def open_app_by_name(self, command):
         parts = command.split("открой", 1)
         if len(parts) > 1:
              app_name = parts[1].strip()
              if app_name:
                  self.open_app(f"{app_name}.exe")
                  
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
             import os
             import io
             import base64 as b64
             
             screenshot = pyautogui.screenshot()
             
             screenshot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screen.png")
             screenshot.save(screenshot_path)
             print(f"Скриншот сохранен: {screenshot_path}")
             
             from nlp_engine import client, use_new_sdk, model_name
             if client and use_new_sdk:
                 try:
                     buf = io.BytesIO()
                     screenshot.save(buf, format='PNG')
                     image_bytes = buf.getvalue()
                     
                     from google import genai
                     from google.genai import types
                     
                     response = client.models.generate_content(
                         model=model_name,
                         contents=[
                             types.Content(parts=[
                                 types.Part.from_text("Опиши что ты видишь на этом скриншоте экрана. Ответь коротко, на русском языке."),
                                 types.Part.from_bytes(data=image_bytes, mime_type="image/png")
                             ])
                         ]
                     )
                     description = response.text
                     print(f"Описание экрана: {description}")
                     return description
                 except Exception as e:
                     print(f"Ошибка анализа скриншота через Gemini: {e}")
                     return "Я сделал снимок экрана, но не смог его проанализировать."
             else:
                 return "Я сделал снимок экрана, но ИИ для анализа недоступен."
         except Exception as e:
             print(f"Ошибка при снятии скриншота: {e}")
             return f"Ошибка при снятии скриншота: {e}"

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

    def get_system_stats(self):
        try:
            import psutil
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            return {"cpu": cpu, "ram": ram}
        except Exception:
            import random
            return {"cpu": random.randint(10, 40), "ram": random.randint(30, 60)}

    def listen_voice(self):
        import pyaudio
        import numpy as np
        import time
        import math
        import string

        if _whisper_model is None:
            return {"status": "error", "message": "Модель Whisper не загружена"}

        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        RATE = 16000
        SILENCE_THRESHOLD = 500  
        SILENCE_DURATION = 1.0 
        
        p = pyaudio.PyAudio()
        stream = p.open(format=FORMAT,
                        channels=CHANNELS,
                        rate=RATE,
                        input=True,
                        frames_per_buffer=CHUNK)
        try:
            self.force_stop = False

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
                 data = stream.read(CHUNK)
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
                 return {"status": "ignore", "text": ""}

            audio_data = b''.join(frames)
            
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

            segments, info = _whisper_model.transcribe(
                audio_np,
                language="ru",
                vad_filter=True,
                beam_size=7,
                initial_prompt=WHISPER_PROMPT,
                condition_on_previous_text=False,
                no_speech_threshold=0.5,
                compression_ratio_threshold=2.4,
            )
            text = "".join([segment.text for segment in segments]).strip()

            if not text:
               return {"status": "ignore", "text": ""}
            
            command = text.lower()
            command = _correct_text(command)
            print(f"Распознано: {command}")
            
            command_clean = command.translate(str.maketrans('', '', string.punctuation))
            
            if not getattr(self, "is_awake", False):
                 if "макс" in command_clean:
                      self.is_awake = True
                      parts = command_clean.split("макс", 1)
                      rest_command = parts[1].strip() if len(parts) > 1 else ""
                      if rest_command:
                          return {"status": "success", "text": rest_command}
                      wake_text = "Я вас слушаю."
                      wake_audio = self._get_elevenlabs_audio(wake_text)
                      return {"status": "wake", "text": wake_text, "audio_base64": wake_audio}
                 else:
                      return {"status": "ignore", "text": ""}
            
            self.is_awake = False
            return {"status": "success", "text": command_clean}

        except Exception as e:
            return {"status": "error", "message": f"Ошибка распознавания: {str(e)}"}
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()

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
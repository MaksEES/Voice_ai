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

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

try:
    import speech_recognition as sr
except ImportError:
    sr = None
    


class API:
    def __init__(self):
        self.nlp = NLPProcessor()
        self.engine = True if pyttsx3 else None
        self.force_stop = False
        self.is_awake = False
        try:
            from faster_whisper import WhisperModel
            print("Загрузка WhisperModel...")
            self.whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
            print("WhisperModel загружена.")
        except Exception as e:
            print(f"Ошибка загрузки Whisper: {e}")
            self.whisper_model = None

    def stop_listening(self):
        self.force_stop = True

    def set_awake(self):
        self.is_awake = True

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

    def handle_command(self, text):
        intent, original = self.nlp.analyze(text)
        response_text = self.nlp.get_response(intent, original)
        
        audio_base64 = None
        voice_api_key = os.getenv("Voice_API")
        if voice_api_key:
            try:
                url = "https://api.elevenlabs.io/v1/text-to-speech/JBFqnCBsd6RMkjVDRZzb"
                headers = {
                    "Accept": "audio/mpeg",
                    "Content-Type": "application/json",
                    "xi-api-key": voice_api_key.strip('"')
                }
                data = {
                    "text": response_text,
                    "model_id": "eleven_multilingual_v2"
                }
                res = requests.post(url, json=data, headers=headers)
                if res.status_code == 200:
                    audio_base64 = base64.b64encode(res.content).decode('utf-8')
                else:
                    print(f"ElevenLabs API Error: {res.text}")
            except Exception as e:
                print(f"ElevenLabs Request Error: {e}")
                
        if not audio_base64:
            self.speak(response_text)
        
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
            webbrowser.open(f"https://www.youtube.com/results?search_query={original}")
        elif intent == "SEARCH":
            import webbrowser
            webbrowser.open(f"https://www.google.com/search?q={original}")
            
        command = text.lower()
        if "открой" in command:
            self.open_app_by_name(command)
        if "напечатай" in command:
            self.type_text(command)
        if "что на экране" in command:
            self.describe_screen()
            
        return {
            "intent": intent,
            "response": response_text,
            "audio_base64": audio_base64
        }
        
    def open_app_by_name(self, command):
         parts = command.split("открой", 1)
         if len(parts) > 1:
              app_name = parts[1].strip()
              if app_name:
                  self.open_app(f"{app_name}.exe")
                  
    def type_text(self, command):
         try:
             import pyautogui
             parts = command.split("напечатай", 1)
             if len(parts) > 1:
                 text_to_type = parts[1].strip()
                 if text_to_type:
                    pyautogui.write(text_to_type, interval=0.05)
         except Exception as e:
             print(f"Ошибка при вводе текста: {e}")
             
    def describe_screen(self):
         try:
             import pyautogui
             import os
             screenshot_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screen.png")
             screenshot = pyautogui.screenshot()
             screenshot.save(screenshot_path)
             print(f"Скриншот сохранен: {screenshot_path}")
             self.speak("Я сделал снимок экрана")
         except Exception as e:
             print(f"Ошибка при снятии скриншота: {e}")

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

        if not getattr(self, "whisper_model", None):
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

                 if time.time() - start_time > 7 and not speaking:
                     break
                 elif time.time() - start_time > 15:
                     break
                     
            if getattr(self, "force_stop", False):
                 return {"status": "ignore", "text": ""}
                     
            if not frames:
                 return {"status": "ignore", "text": ""}

            audio_data = b''.join(frames)
            
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

            segments, info = self.whisper_model.transcribe(audio_np, language="ru", vad_filter=True)
            text = "".join([segment.text for segment in segments]).strip()

            if not text:
               return {"status": "ignore", "text": ""}
            
            command = text.lower()
            print(f"Распознано: {command}")
            
            command_clean = command.translate(str.maketrans('', '', string.punctuation))
            
            if not getattr(self, "is_awake", False):
                 if "макс" in command_clean:
                      self.is_awake = True
                      parts = command_clean.split("макс", 1)
                      rest_command = parts[1].strip() if len(parts) > 1 else ""
                      if rest_command:
                          return {"status": "success", "text": rest_command}
                      return {"status": "wake", "text": "Я вас слушаю."}
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
import webview
import os
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
        elif intent == "YOUTUBE":
            import webbrowser
            webbrowser.open(f"https://www.youtube.com/results?search_query={original}")
        elif intent == "SEARCH":
            import webbrowser
            webbrowser.open(f"https://www.google.com/search?q={original}")
            
        return {
            "intent": intent,
            "response": response_text,
            "audio_base64": audio_base64
        }

    def open_folder(self, folder_type):
        try:
            path = ""
            if sys.platform == "win32":
                if folder_type == "pictures": path = os.path.join(os.environ['USERPROFILE'], 'Pictures')
                elif folder_type == "music": path = os.path.join(os.environ['USERPROFILE'], 'Music')
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
        if not sr:
            return {"status": "error", "message": "Библиотека speech_recognition не найдена"}
        
        try:
            r = sr.Recognizer()
            with sr.Microphone() as source:
                r.adjust_for_ambient_noise(source, duration=0.5)
                audio = r.listen(source, timeout=5, phrase_time_limit=8)
            text = r.recognize_google(audio, language="ru-RU")
            return {"status": "success", "text": text}
        except Exception as e:
            return {"status": "error", "message": str(e)}

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





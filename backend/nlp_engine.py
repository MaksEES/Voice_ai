import re
import os
from dotenv import load_dotenv

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(project_root, '.env')
load_dotenv(dotenv_path=env_path)

client = None
model_name = 'gemini-1.5-flash' 
use_new_sdk = False

def init_ai():
    global client, use_new_sdk
    api_key = os.getenv("API_KEY")
    
    try:
        #SDK genai
        from google import genai
        client = genai.Client(api_key=api_key)
        use_new_sdk = True
        print("ИИ: Использован новый SDK (google-genai)")
    except Exception:
        try:
            #google-generativeai
            import google.generativeai as genai_old
            genai_old.configure(api_key=api_key)
            client = genai_old.GenerativeModel('gemini-1.5-flash')
            use_new_sdk = False
            print("ИИ: Использован старый SDK (google-generativeai)")
        except Exception as e:
            print(f"ИИ: Ошибка инициализации: {e}")
            client = None


init_ai()

class NLPProcessor:
    def __init__(self):
        self.system_intents = {
            "OPEN_BROWSER": [r"открой (браузер|интернет|гугл|сайт)", r"запусти (браузер|интернет)"],
            "OPEN_CALC": [r"открой (калькулятор|счеты)", r"запусти калькулятор"],
            "OPEN_NOTEPAD": [r"открой (блокнот|текстовый редактор)", r"запиши (заметку|текст)"],
            "GET_STATS": [r"(покажи|какая) (статистика|нагрузка|состояние)", r"как дела у системы"],
            "YOUTUBE": [r"(найди|включи|открой) на (ютубе|youtube)", r"видео про (.+)"],
            "SEARCH": [r"(найди|поищи) в (интернете|гугле|сети) (.+)", r"что такое (.+)"],
        }

    def analyze(self, text):
        text = text.lower().strip()
        for intent, patterns in self.system_intents.items():
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    query = match.group(match.lastindex) if match.lastindex else ""
                    return intent, query or text
        return "AI_THINK", text

    def get_response(self, intent, original_text):
        system_responses = {
            "OPEN_BROWSER": "Запускаю ваш стандартный браузер. Готов к работе в сети.",
            "OPEN_CALC": "Открываю калькулятор. Что будем считать?",
            "OPEN_NOTEPAD": "Блокнот открыт. Можете записывать.",
            "GET_STATS": "Проверяю состояние ресурсов... Система работает стабильно.",
            "YOUTUBE": f"Ищу '{original_text}' на YouTube. Сейчас откроется видео.",
            "SEARCH": f"Ищу информацию про '{original_text}' в интернете.",
        }

        if intent in system_responses:
            return system_responses[intent]

        if client and intent == "AI_THINK":
            try:
                clean_text = original_text[:500]
                prompt = f"Ты — интеллектуальный помощник Voice OS. Ответь коротко и ясно на запрос пользователя: {clean_text}"
                
                if use_new_sdk:
                    try:
                        response = client.models.generate_content(model=model_name, contents=prompt)
                        return response.text
                    except Exception:
                        response = client.models.generate_content(model='gemini-1.0-pro', contents=prompt)
                        return response.text
                else:
                    # Старый SDK
                    response = client.generate_content(prompt)
                    return response.text
            except Exception as e:
                error_msg = str(e)
                print(f"AI ERROR (Gemini): {error_msg}")
                if "404" in error_msg:
                    return "Ошибка: Модель ИИ не найдена. Попробуйте обновить библиотеку: pip install -U google-genai"
                if "403" in error_msg:
                    return "Ошибка: Доступ к модели заблокирован для этого ключа."
                return f"Ошибка ИИ: {error_msg[:100]}..."

        
        if not client and intent == "AI_THINK":
            return "ИИ не настроен. Убедитесь, что установлена библиотека 'google-genai' и API ключ верен."


import os
import sys
from dotenv import load_dotenv

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(project_root, '.env')
load_dotenv(dotenv_path=env_path)
API_KEY = os.getenv("API_KEY")

print("--- ДИАГНОСТИКА GEMINI API ---")

try:
    from google import genai
    print("[OK] Библиотека 'google-genai' найдена.")
    client = genai.Client(api_key=API_KEY)
    try:
        print("Попытка запроса через новый SDK...")
        response = client.models.generate_content(model='gemini-1.5-flash', contents="Привет, протестируй связь.")
        print(f"[УСПЕХ] Ответ ИИ: {response.text}")
    except Exception as e:
        print(f"[ОШИБКА] Новый SDK не смог получить ответ: {e}")
except ImportError:
    print("[INFO] Библиотека 'google-genai' не найдена. Пробую старый метод...")
    try:
        import google.generativeai as genai_old
        print("[OK] Библиотека 'google-generativeai' найдена.")
        genai_old.configure(api_key=API_KEY)
        model = genai_old.GenerativeModel('gemini-1.5-flash')
        try:
            print("Попытка запроса через старый SDK...")
            response = model.generate_content("Привет, протестируй связь.")
            print(f"[УСПЕХ] Ответ ИИ: {response.text}")
        except Exception as e:
            print(f"[ОШИБКА] Старый SDK не смог получить ответ: {e}")
    except ImportError:
        print("[КРИТИЧЕСКАЯ ОШИБКА] Ни одна библиотека для ИИ не установлена.")
        print("Запустите: pip install google-genai")

print("\n--- КОНЕЦ ДИАГНОСТИКИ ---")
input("Нажмите Enter, чтобы закрыть...")

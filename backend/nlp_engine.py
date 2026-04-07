import re
import os
import json
from difflib import SequenceMatcher
from dotenv import load_dotenv

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(project_root, '.env')
load_dotenv(dotenv_path=env_path)

client = None
model_name = 'gemini-2.5-flash' 
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
            import google.generativeai as genai_old
            genai_old.configure(api_key=api_key)
            client = genai_old.GenerativeModel('gemini-1.5-flash')
            use_new_sdk = False
            print("ИИ: Использован старый SDK (google-generativeai)")
        except Exception as e:
            print(f"ИИ: Ошибка инициализации: {e}")
            client = None


init_ai()
"""Гибридный NLP через поиск ключевых слов и Gemini"""
"""1 часть - расширенные ключевые слова"""
INTENT_KEYWORDS = {
    "OPEN_BROWSER": {
        "verbs": ["открой", "запусти", "включи", "покажи", "загрузи", "давай", "хочу"],
        "nouns": ["браузер", "интернет", "гугл", "хром", "chrome", "сайт", "веб", "google"],
    },
    "OPEN_CALC": {
        "verbs": ["открой", "запусти", "включи", "покажи", "давай"],
        "nouns": ["калькулятор", "счеты", "считалку", "считалка", "calculator"],
    },
    "OPEN_NOTEPAD": {
        "verbs": ["открой", "запусти", "включи", "давай"],
        "nouns": ["блокнот", "текстовый редактор", "редактор", "notepad", "заметки"],
    },
    "GET_STATS": {
        "verbs": ["покажи", "какая", "скажи", "проверь"],
        "nouns": ["статистика", "нагрузка", "состояние", "система", "ресурсы", "память"],
    },
    "YOUTUBE": {
        "verbs": ["найди", "включи", "открой", "покажи", "запусти", "поищи"],
        "nouns": ["ютуб", "ютубе", "youtube", "видео"],
    },
    "SEARCH": {
        "verbs": ["найди", "поищи", "загугли", "покажи", "расскажи"],
        "nouns": ["интернет", "интернете", "гугле", "сети", "google"],
    },
    "OPEN_PICTURES": {
        "verbs": ["открой", "покажи", "запусти"],
        "nouns": ["фото", "картинки", "фотографии", "галерея", "галерею", "изображения"],
    },
    "OPEN_MUSIC": {
        "verbs": ["открой", "покажи", "запусти", "включи"],
        "nouns": ["музыку", "музыка", "песни", "аудио", "треки"],
    },
    "OPEN_DOWNLOADS": {
        "verbs": ["открой", "покажи", "запусти"],
        "nouns": ["загрузки", "скачанное", "скачанные", "downloads", "загрузок"],
    },
}

INTENT_PHRASES = {
    "GET_STATS": ["как дела у системы", "состояние системы", "что с системой"],
    "SEARCH": ["что такое", "кто такой", "что значит"],
    "YOUTUBE": ["видео про", "на ютубе", "на youtube"],
}

"""2 часть - нечеткое сравнение"""
def _fuzzy_find(word, candidates, threshold=0.75):
    best_match = None
    best_score = 0
    for candidate in candidates:
        score = SequenceMatcher(None, word, candidate).ratio()
        if score > best_score and score >= threshold:
            best_score = score
            best_match = candidate
    return best_match, best_score

"""3 часть - вопрос к Gemini"""
GEMINI_INTENT_PROMPT = """Ты — классификатор намерений голосового ассистента.
Определи намерение пользователя из списка ниже. Ответь СТРОГО в формате JSON.

Возможные намерения:
- OPEN_BROWSER — открыть браузер / интернет
- OPEN_CALC — открыть калькулятор
- OPEN_NOTEPAD — открыть блокнот / текстовый редактор
- YOUTUBE — найти видео на YouTube
- SEARCH — поиск в интернете
- OPEN_PICTURES — открыть папку с картинками
- OPEN_MUSIC — открыть папку с музыкой
- OPEN_DOWNLOADS — открыть папку загрузок
- GET_STATS — показать статистику системы
- UNKNOWN — если не подходит ни одно намерение

Текст пользователя: "{text}"

Ответь ТОЛЬКО JSON, без пояснений:
{{"intent": "...", "confidence": 0.0}}"""


def _classify_with_gemini(text):
    if not client:
        return None, 0
    
    try:
        prompt = GEMINI_INTENT_PROMPT.replace("{text}", text[:200])
        
        if use_new_sdk:
            try:
                response = client.models.generate_content(model=model_name, contents=prompt)
                result_text = response.text
            except Exception:
                response = client.models.generate_content(model='gemini-2.0-flash-lite', contents=prompt)
                result_text = response.text
        else:
            response = client.generate_content(prompt)
            result_text = response.text
        
        result_text = result_text.strip()
        if result_text.startswith("```"):
            result_text = result_text.split("\n", 1)[-1]
            result_text = result_text.rsplit("```", 1)[0]
            result_text = result_text.strip()
        
        data = json.loads(result_text)
        intent = data.get("intent", "UNKNOWN")
        confidence = float(data.get("confidence", 0))
        
        if intent != "UNKNOWN" and confidence >= 0.6:
            print(f"[NLP] Gemini классификация: {intent} ({confidence:.0%})")
            return intent, confidence
        
        return None, 0
        
    except Exception as e:
        print(f"[NLP] Ошибка Gemini классификации: {e}")
        return None, 0


class NLPProcessor:
    def __init__(self):
        self.system_intents = {
            "OPEN_BROWSER": [r"открой (браузер|интернет|гугл|сайт)", r"запусти (браузер|интернет)"],
            "OPEN_CALC": [r"открой (калькулятор|счеты)", r"запусти калькулятор"],
            "OPEN_NOTEPAD": [r"открой (блокнот|текстовый редактор)", r"запиши (заметку|текст)"],
            "GET_STATS": [r"(покажи|какая) (статистика|нагрузка|состояние)", r"как дела у системы"],
            "YOUTUBE": [r"(найди|включи|открой) на (ютубе|youtube)", r"видео про (.+)"],
            "SEARCH": [r"(найди|поищи) в (интернете|гугле|сети) (.+)", r"что такое (.+)"],
            "OPEN_PICTURES": [r"открой (фото|картинки|галерею)", r"открой папку с картинками"],
            "OPEN_MUSIC": [r"открой (музыку|музыка)", r"открой папку с музыкой"],
            "OPEN_DOWNLOADS": [r"открой (загрузки|скачанное)", r"открой папку загрузок"],
        }

    def analyze(self, text):
        text = text.lower().strip()
        
        for intent, patterns in self.system_intents.items():
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    query = match.group(match.lastindex) if match.lastindex else ""
                    print(f"[NLP] Уровень 0 (regex): {intent}")
                    return intent, query or text
        
        intent = self._match_keywords(text)
        if intent:
            print(f"[NLP] Уровень 1 (ключевые слова): {intent}")
            return intent, text
        
        intent = self._match_fuzzy(text)
        if intent:
            print(f"[NLP] Уровень 2 (fuzzy): {intent}")
            return intent, text
        
        for phrase_intent, phrases in INTENT_PHRASES.items():
            for phrase in phrases:
                if phrase in text:
                    print(f"[NLP] Уровень 2.5 (фраза): {phrase_intent}")
                    return phrase_intent, text
        
        gemini_intent, confidence = _classify_with_gemini(text)
        if gemini_intent:
            print(f"[NLP] Уровень 3 (Gemini): {gemini_intent}")
            return gemini_intent, text
        
        return "AI_THINK", text
    
    def _match_keywords(self, text):
        words = text.split()
        
        for intent, kw in INTENT_KEYWORDS.items():
            has_verb = any(verb in words for verb in kw["verbs"])
            has_noun = any(noun in text for noun in kw["nouns"])
            
            if has_verb and has_noun:
                return intent
        
        return None
    
    def _match_fuzzy(self, text):
        words = text.split()
        
        for intent, kw in INTENT_KEYWORDS.items():
            has_verb = False
            has_noun = False
            
            for word in words:
                if not has_verb:
                    match, score = _fuzzy_find(word, kw["verbs"], threshold=0.75)
                    if match:
                        has_verb = True
                
                if not has_noun:
                    match, score = _fuzzy_find(word, kw["nouns"], threshold=0.72)
                    if match:
                        has_noun = True
            
            if has_verb and has_noun:
                return intent
        
        return None

    def get_response(self, intent, original_text):
        system_responses = {
            "OPEN_BROWSER": "Запускаю ваш стандартный браузер. Готов к работе в сети.",
            "OPEN_CALC": "Открываю калькулятор. Что будем считать?",
            "OPEN_NOTEPAD": "Блокнот открыт. Можете записывать.",
            "GET_STATS": "Проверяю состояние ресурсов... Система работает стабильно.",
            "YOUTUBE": f"Ищу '{original_text}' на YouTube. Сейчас откроется видео.",
            "SEARCH": f"Ищу информацию про '{original_text}' в интернете.",
            "OPEN_PICTURES": "Открываю вашу галерею.",
            "OPEN_MUSIC": "Открываю папку с музыкой.",
            "OPEN_DOWNLOADS": "Открываю папку загрузок.",
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
                        response = client.models.generate_content(model='gemini-2.0-flash-lite', contents=prompt)
                        return response.text
                else:
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

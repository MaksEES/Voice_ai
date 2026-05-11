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
"""1 часть - расширенные ключевые слова (мультиязычные)"""
INTENT_KEYWORDS = {
    "OPEN_BROWSER": {
        "verbs": ["открой", "запусти", "включи", "покажи", "загрузи", "давай", "хочу",
                  "open", "launch", "start", "run", "show",
                  "аш", "қос", "іске", "көрсет"],
        "nouns": ["браузер", "интернет", "гугл", "хром", "chrome", "сайт", "веб", "google",
                  "browser", "internet", "web",
                  "браузерді", "интернетті"],
    },
    "OPEN_CALC": {
        "verbs": ["открой", "запусти", "включи", "покажи", "давай",
                  "open", "launch", "start", "run",
                  "аш", "қос"],
        "nouns": ["калькулятор", "счеты", "считалку", "считалка", "calculator",
                  "калькуляторды", "есептегіш"],
    },
    "OPEN_NOTEPAD": {
        "verbs": ["открой", "запусти", "включи", "давай",
                  "open", "launch", "start",
                  "аш", "қос"],
        "nouns": ["блокнот", "текстовый редактор", "редактор", "notepad", "заметки",
                  "блокнотты", "жазба"],
    },
    "GET_STATS": {
        "verbs": ["покажи", "какая", "скажи", "проверь",
                  "show", "check", "what",
                  "көрсет", "тексер"],
        "nouns": ["статистика", "нагрузка", "состояние", "система", "ресурсы", "память",
                  "stats", "statistics", "system", "performance", "memory", "cpu",
                  "жүйе", "жүктеме"],
    },
    "YOUTUBE": {
        "verbs": ["найди", "включи", "открой", "покажи", "запусти", "поищи",
                  "find", "search", "play", "open", "show",
                  "іздеу", "тап", "аш"],
        "nouns": ["ютуб", "ютубе", "youtube", "видео",
                  "video",
                  "бейне"],
    },
    "SEARCH": {
        "verbs": ["найди", "поищи", "загугли", "покажи", "расскажи",
                  "find", "search", "google", "look",
                  "іздеу", "тап"],
        "nouns": ["интернет", "интернете", "гугле", "сети", "google",
                  "internet", "web", "online",
                  "интернеттен"],
    },
    "OPEN_PICTURES": {
        "verbs": ["открой", "покажи", "запусти",
                  "open", "show",
                  "аш", "көрсет"],
        "nouns": ["фото", "картинки", "фотографии", "галерея", "галерею", "изображения",
                  "photos", "pictures", "gallery", "images",
                  "сурет", "суреттер", "фотолар"],
    },
    "OPEN_MUSIC": {
        "verbs": ["открой", "покажи", "запусти", "включи",
                  "open", "show", "play",
                  "аш", "қос"],
        "nouns": ["музыку", "музыка", "песни", "аудио", "треки",
                  "music", "songs", "audio", "tracks",
                  "музыканы", "әндер"],
    },
    "OPEN_DOWNLOADS": {
        "verbs": ["открой", "покажи", "запусти",
                  "open", "show",
                  "аш", "көрсет"],
        "nouns": ["загрузки", "скачанное", "скачанные", "downloads", "загрузок",
                  "жүктеулер", "жүктеулерді"],
    },
}

INTENT_PHRASES = {
    "GET_STATS": ["как дела у системы", "состояние системы", "что с системой",
                  "system status", "how is the system",
                  "жүйе қалай"],
    "SEARCH": ["что такое", "кто такой", "что значит",
               "what is", "who is", "what does",
               "не деген", "кім деген"],
    "YOUTUBE": ["видео про", "на ютубе", "на youtube",
                "video about", "on youtube",
                "youtube-тен"],
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

"""3 часть - вопрос к Gemini (мультиязычный)"""
GEMINI_INTENT_PROMPT = """You are an intent classifier for a voice assistant.
The user may speak in Russian, English, or Kazakh.
Classify the user's intent from the list below. Reply STRICTLY in JSON format.

Possible intents:
- OPEN_BROWSER — open browser / internet
- OPEN_CALC — open calculator
- OPEN_NOTEPAD — open notepad / text editor
- YOUTUBE — find video on YouTube
- SEARCH — search the internet
- OPEN_PICTURES — open pictures folder
- OPEN_MUSIC — open music folder
- OPEN_DOWNLOADS — open downloads folder
- GET_STATS — show system statistics
- UNKNOWN — if no intent matches

User text: "{text}"

Reply ONLY with JSON, no explanations:
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
            # Русский
            "OPEN_BROWSER": [r"открой (браузер|интернет|гугл|сайт)", r"запусти (браузер|интернет)",
                             r"open (browser|internet|chrome)", r"launch browser",
                             r"(браузерді|интернетті) аш"],
            "OPEN_CALC": [r"открой (калькулятор|счеты)", r"запусти калькулятор",
                          r"open calculator", r"launch calculator",
                          r"калькуляторды аш"],
            "OPEN_NOTEPAD": [r"открой (блокнот|текстовый редактор)", r"запиши (заметку|текст)",
                             r"open (notepad|text editor)", r"launch notepad",
                             r"блокнотты аш"],
            "GET_STATS": [r"(покажи|какая) (статистика|нагрузка|состояние)", r"как дела у системы",
                          r"(show|check) (stats|system|performance)", r"system status",
                          r"жүйе (қалай|жағдайы)"],
            "YOUTUBE": [r"(найди|включи|открой) на (ютубе|youtube)", r"видео про (.+)",
                        r"(find|search|play) on youtube", r"video about (.+)",
                        r"youtube-тен (іздеу|тап)"],
            "SEARCH": [r"(найди|поищи) в (интернете|гугле|сети) (.+)", r"что такое (.+)",
                       r"(search|find|google) (.+)", r"what is (.+)",
                       r"интернеттен (іздеу|тап)"],
            "OPEN_PICTURES": [r"открой (фото|картинки|галерею)", r"открой папку с картинками",
                              r"open (photos|pictures|gallery)",
                              r"(суреттерді|фотоларды) аш"],
            "OPEN_MUSIC": [r"открой (музыку|музыка)", r"открой папку с музыкой",
                           r"open music", r"play music",
                           r"музыканы аш"],
            "OPEN_DOWNLOADS": [r"открой (загрузки|скачанное)", r"открой папку загрузок",
                               r"open downloads",
                               r"жүктеулерді аш"],
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

    def get_response(self, intent, original_text, lang="ru"):
        system_responses = {
            "ru": {
                "OPEN_BROWSER": "Запускаю ваш стандартный браузер. Готов к работе в сети.",
                "OPEN_CALC": "Открываю калькулятор. Что будем считать?",
                "OPEN_NOTEPAD": "Блокнот открыт. Можете записывать.",
                "GET_STATS": "Проверяю состояние ресурсов... Система работает стабильно.",
                "YOUTUBE": f"Ищу '{original_text}' на YouTube. Сейчас откроется видео.",
                "SEARCH": f"Ищу информацию про '{original_text}' в интернете.",
                "OPEN_PICTURES": "Открываю вашу галерею.",
                "OPEN_MUSIC": "Открываю папку с музыкой.",
                "OPEN_DOWNLOADS": "Открываю папку загрузок.",
            },
            "en": {
                "OPEN_BROWSER": "Launching your default browser. Ready to surf.",
                "OPEN_CALC": "Opening calculator. What shall we compute?",
                "OPEN_NOTEPAD": "Notepad is open. You can start writing.",
                "GET_STATS": "Checking system resources... System is running smoothly.",
                "YOUTUBE": f"Searching for '{original_text}' on YouTube.",
                "SEARCH": f"Searching for '{original_text}' on the internet.",
                "OPEN_PICTURES": "Opening your photo gallery.",
                "OPEN_MUSIC": "Opening your music folder.",
                "OPEN_DOWNLOADS": "Opening your downloads folder.",
            },
            "kk": {
                "OPEN_BROWSER": "Браузерді іске қосудамын. Желіге дайынмын.",
                "OPEN_CALC": "Калькуляторды ашудамын. Нені есептейміз?",
                "OPEN_NOTEPAD": "Блокнот ашылды. Жаза берсеңіз болады.",
                "GET_STATS": "Жүйе ресурстарын тексерудемін... Жүйе тұрақты жұмыс істеуде.",
                "YOUTUBE": f"YouTube-тен '{original_text}' іздеудемін.",
                "SEARCH": f"Интернеттен '{original_text}' іздеудемін.",
                "OPEN_PICTURES": "Сурет галереяңызды ашудамын.",
                "OPEN_MUSIC": "Музыка қалтасын ашудамын.",
                "OPEN_DOWNLOADS": "Жүктеулер қалтасын ашудамын.",
            },
        }

        responses = system_responses.get(lang, system_responses["ru"])
        if intent in responses:
            return responses[intent]

        if client and intent == "AI_THINK":
            try:
                clean_text = original_text[:500]
                lang_instructions = {
                    "ru": f"Ты — интеллектуальный помощник Voice OS. Ответь коротко и ясно на русском языке: {clean_text}",
                    "en": f"You are Voice OS intelligent assistant. Reply briefly and clearly in English: {clean_text}",
                    "kk": f"Сен Voice OS интеллектуалды көмекшісісің. Қазақ тілінде қысқа және анық жауап бер: {clean_text}",
                }
                prompt = lang_instructions.get(lang, lang_instructions["ru"])
                
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

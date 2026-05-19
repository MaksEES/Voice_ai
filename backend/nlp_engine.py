import re
import os
import json
from difflib import SequenceMatcher
from dotenv import load_dotenv

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(project_root, '.env')
load_dotenv(dotenv_path=env_path)

llm = None

def init_ai():
    global llm
    model_path = os.getenv("LLM_MODEL_PATH")
    
    if not model_path or not os.path.exists(model_path):
        print(f"[LLM] Ошибка: файл модели не найден: {model_path}")
        print("[LLM] Проверь переменную LLM_MODEL_PATH в файле .env")
        llm = None
        return
    
    try:
        from llama_cpp import Llama
        print(f"[LLM] Загрузка Llama 3 из: {os.path.basename(model_path)}...")
        print("[LLM] Это займёт 10-20 секунд...")
        
        llm = Llama(
            model_path=model_path,
            n_ctx=2048,
            n_gpu_layers=-1,
            n_threads=None,
            verbose=False,
        )
        print("[LLM] ✓ Llama 3 загружена и готова к работе!")
    except ImportError:
        print("[LLM] Ошибка: библиотека llama-cpp-python не установлена!")
        print("[LLM] Установи: pip install llama-cpp-python")
        llm = None
    except Exception as e:
        print(f"[LLM] Ошибка загрузки модели: {e}")
        llm = None


init_ai()
"""ключевые слова"""
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

"""нечеткое сравнение"""
def _fuzzy_find(word, candidates, threshold=0.75):
    best_match = None
    best_score = 0
    for candidate in candidates:
        score = SequenceMatcher(None, word, candidate).ratio()
        if score > best_score and score >= threshold:
            best_score = score
            best_match = candidate
    return best_match, best_score

"""вопрос к Llama 3"""
INTENT_CLASSIFY_PROMPT = """You are an intent classifier for a voice assistant.
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


def _classify_with_llm(text):
    if not llm:
        return None, 0
    
    try:
        prompt = INTENT_CLASSIFY_PROMPT.replace("{text}", text[:200])
        
        response = llm.create_chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=64,
            response_format={"type": "json_object"},
        )
        
        result_text = response["choices"][0]["message"]["content"].strip()
        
        data = json.loads(result_text)
        intent = data.get("intent", "UNKNOWN")
        confidence = float(data.get("confidence", 0))
        
        if intent != "UNKNOWN" and confidence >= 0.6:
            print(f"[NLP] Llama классификация: {intent} ({confidence:.0%})")
            return intent, confidence
        
        return None, 0
        
    except Exception as e:
        print(f"[NLP] Ошибка Llama классификации: {e}")
        return None, 0


class NLPProcessor:
    def __init__(self):
        self.system_intents = {
            "OPEN_BROWSER": [r"(?:открой|запусти|включи) (?:браузер|интернет|гугл|сайт)", r"open (?:browser|internet|chrome)", r"launch browser", r"(?:браузерді|интернетті) аш"],
            "OPEN_CALC": [r"(?:открой|запусти) (?:калькулятор|счеты)", r"open calculator", r"launch calculator", r"калькуляторды аш"],
            "OPEN_NOTEPAD": [r"(?:открой|запусти) (?:блокнот|текстовый редактор)", r"open (?:notepad|text editor)", r"launch notepad", r"блокнотты аш"],
            "GET_STATS": [r"(?:покажи|какая) (?:статистика|нагрузка|состояние)", r"как дела у системы", r"(?:show|check) (?:stats|system|performance)", r"system status", r"жүйе (?:қалай|жағдайы)"],
            "YOUTUBE": [r"(?:включи|найди|открой) (.+) (?:на|в) (?:ютубе|youtube|ютуб)", r"видео про (.+)", r"(?:find|search|play) (.+) on youtube", r"video about (.+)", r"youtube-тен (?:іздеу|тап)"],
            "SPOTIFY": [r"(?:включи|поставь|найди) (.+) (?:в|на) (?:спотифай|spotify)"],
            "VOLUME_UP": [r"(?:сделай|) (?:погромче|громче)", r"прибавь звук", r"volume up"],
            "VOLUME_DOWN": [r"(?:сделай|) (?:потише|тише)", r"убавь звук", r"volume down"],
            "VOLUME_MUTE": [r"выключи звук", r"без звука", r"mute volume"],
            "MEDIA_PLAY_PAUSE": [r"поставь на паузу", r"пауза", r"продолжи (?:музыку|воспроизведение)", r"play music", r"pause music"],
            "MEDIA_NEXT": [r"следующий трек", r"включи следующую", r"next track"],
            "MEDIA_PREV": [r"предыдущий трек", r"включи предыдущую", r"previous track"],
            "SYS_SLEEP": [r"спящий режим", r"усни", r"перейди в спящий режим", r"sleep mode"],
            "SYS_SHUTDOWN": [r"выключи (?:компьютер|пк)", r"завершение работы", r"shutdown computer"],
            "SEARCH": [r"(?:найди|поищи) (?:в интернете|в гугле|в сети) (.+)", r"что такое (.+)", r"(?:search|find|google) (.+)", r"what is (.+)", r"интернеттен (?:іздеу|тап)"],
            "OPEN_PICTURES": [r"открой (?:фото|картинки|галерею)", r"открой папку с картинками", r"open (?:photos|pictures|gallery)", r"(?:суреттерді|фотоларды) аш"],
            "OPEN_MUSIC": [r"открой (?:музыку|музыка)", r"открой папку с музыкой", r"open music", r"play music", r"музыканы аш"],
            "OPEN_DOWNLOADS": [r"открой (?:загрузки|скачанное)", r"открой папку загрузок", r"open downloads", r"жүктеулерді аш"],
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
        
        llm_intent, confidence = _classify_with_llm(text)
        if llm_intent:
            print(f"[NLP] Уровень 3 (Llama): {llm_intent}")
            return llm_intent, text
        
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

    def get_response(self, intent, original_text, lang="ru", history=None):
        system_responses = {
            "ru": {
                "OPEN_BROWSER": "Запускаю ваш стандартный браузер. Готов к работе в сети.",
                "OPEN_CALC": "Открываю калькулятор. Что будем считать?",
                "OPEN_NOTEPAD": "Блокнот открыт. Можете записывать.",
                "GET_STATS": "Проверяю состояние ресурсов... Система работает стабильно.",
                "YOUTUBE": f"Включаю '{original_text}' на YouTube.",
                "SPOTIFY": f"Ищу '{original_text}' в Spotify.",
                "SEARCH": f"Ищу информацию про '{original_text}' в интернете.",
                "OPEN_PICTURES": "Открываю вашу галерею.",
                "OPEN_MUSIC": "Открываю папку с музыкой.",
                "OPEN_DOWNLOADS": "Открываю папку загрузок.",
                "VOLUME_UP": "Делаю погромче.",
                "VOLUME_DOWN": "Делаю потише.",
                "VOLUME_MUTE": "Звук отключен.",
                "MEDIA_PLAY_PAUSE": "Переключаю паузу.",
                "MEDIA_NEXT": "Следующий трек.",
                "MEDIA_PREV": "Предыдущий трек.",
                "SYS_SLEEP": "Перехожу в спящий режим. До встречи!",
                "SYS_SHUTDOWN": "Выключаю компьютер через 5 секунд. Чтобы отменить, напиши shutdown /a в консоль.",
            },
            "en": {
                "OPEN_BROWSER": "Launching your default browser. Ready to surf.",
                "OPEN_CALC": "Opening calculator. What shall we compute?",
                "OPEN_NOTEPAD": "Notepad is open. You can start writing.",
                "GET_STATS": "Checking system resources... System is running smoothly.",
                "YOUTUBE": f"Playing '{original_text}' on YouTube.",
                "SPOTIFY": f"Searching for '{original_text}' on Spotify.",
                "SEARCH": f"Searching for '{original_text}' on the internet.",
                "OPEN_PICTURES": "Opening your photo gallery.",
                "OPEN_MUSIC": "Opening your music folder.",
                "OPEN_DOWNLOADS": "Opening your downloads folder.",
                "VOLUME_UP": "Increasing volume.",
                "VOLUME_DOWN": "Decreasing volume.",
                "VOLUME_MUTE": "Volume muted.",
                "MEDIA_PLAY_PAUSE": "Toggling playback.",
                "MEDIA_NEXT": "Next track.",
                "MEDIA_PREV": "Previous track.",
                "SYS_SLEEP": "Going to sleep mode.",
                "SYS_SHUTDOWN": "Shutting down the computer in 5 seconds.",
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

        if llm and intent == "AI_THINK":
            try:
                clean_text = original_text[:500]
                lang_instructions = {
                    "ru": "Ты — интеллектуальный помощник Voice OS по имени Макс. Ответь коротко и ясно на русском языке.",
                    "en": "You are Voice OS intelligent assistant named Max. Reply briefly and clearly in English.",
                    "kk": "Сен Voice OS интеллектуалды көмекшісісің, атың Макс. Қазақ тілінде қысқа және анық жауап бер.",
                }
                system_prompt = lang_instructions.get(lang, lang_instructions["ru"])
                
                messages = [{"role": "system", "content": system_prompt}]
                if history:
                    messages.extend(history)
                messages.append({"role": "user", "content": clean_text})
                
                response = llm.create_chat_completion(
                    messages=messages,
                    temperature=0.7,
                    max_tokens=256,
                )
                
                result = response["choices"][0]["message"]["content"].strip()
                return result
            except Exception as e:
                error_msg = str(e)
                print(f"AI ERROR (Llama): {error_msg}")
                return f"Ошибка ИИ: {error_msg[:100]}..."

        
        if not llm and intent == "AI_THINK":
            return "ИИ не загружен. Убедитесь, что установлена библиотека 'llama-cpp-python' и путь к модели верен в файле .env."

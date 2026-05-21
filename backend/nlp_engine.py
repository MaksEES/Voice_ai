import re
import os
import json
from difflib import SequenceMatcher
from dotenv import load_dotenv

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
env_path = os.path.join(project_root, '.env')
load_dotenv(dotenv_path=env_path)

import requests

def _call_openrouter(messages, max_tokens=256, temperature=0.7):
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise Exception("OPENROUTER_API_KEY не установлен в .env")
        
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    payload = {
        "model": "google/gemini-3.1-flash-lite",
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    response = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=15
    )
    
    if response.status_code == 200:
        data = response.json()
        return data["choices"][0]["message"]["content"]
    else:
        raise Exception(f"OpenRouter Error {response.status_code}: {response.text}")
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
    "CREATE_FOLDER": {
        "verbs": ["создай", "сделай", "новая", "новую",
                  "create", "make", "new",
                  "жаса", "құр"],
        "nouns": ["папку", "папка", "каталог", "директорию", "директория",
                  "folder", "directory",
                  "папка", "папканы"],
    },
    "RENAME_FILE": {
        "verbs": ["переименуй", "переназови", "назови",
                  "rename",
                  "атын өзгерт", "қайта ата"],
        "nouns": ["файл", "папку", "папка", "каталог",
                  "file", "folder", "directory",
                  "файлды", "қалтаны"],
    },
    "DELETE_FILE": {
        "verbs": ["удали", "убери", "сотри", "убрать",
                  "delete", "remove", "erase",
                  "жой", "өшір"],
        "nouns": ["файл", "папку", "папка", "каталог",
                  "file", "folder", "directory",
                  "файлды", "қалтаны"],
    },
    "OPEN_FILE": {
        "verbs": ["открой", "запусти", "покажи",
                  "open", "launch", "show",
                  "аш", "қос"],
        "nouns": ["файл", "документ",
                  "file", "document",
                  "файлды", "құжат"],
    },
}

INTENT_PHRASES = {
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

"""Классификация через Gemini 3.1"""
_EXPLICIT_SEARCH_MARKERS = [
    "в интернете", "в гугле", "в сети", "загугли", "погугли", "в google",
    "search for", "search the", "google it", "look up", "on the internet",
    "интернеттен", "іздеу",
]

INTENT_CLASSIFY_PROMPT = """You are an intent classifier for a voice assistant.
The user may speak in Russian, English, or Kazakh.
Classify the user's intent from the list below. Reply STRICTLY in JSON format.

IMPORTANT: Use SEARCH ONLY when the user EXPLICITLY asks to search the internet
(e.g. "найди в интернете", "загугли", "поищи в гугле", "search online").
General knowledge questions ("what is X", "who is Y", "какая самая длинная река")
should be classified as UNKNOWN — the AI will answer them directly.

Possible intents:
- OPEN_BROWSER — open browser / internet
- OPEN_CALC — open calculator
- OPEN_NOTEPAD — open notepad / text editor
- YOUTUBE — find video on YouTube
- SEARCH — ONLY explicit web search requests
- OPEN_PICTURES — open pictures folder
- OPEN_MUSIC — open music folder
- OPEN_DOWNLOADS — open downloads folder
- CREATE_FOLDER — create a new folder/directory
- RENAME_FILE — rename a file or folder
- DELETE_FILE — delete a file or folder
- OPEN_FILE — open a specific file (document, image, etc.)
- UNKNOWN — general questions, conversations, or no match

User text: "{text}"

Reply ONLY with JSON, no explanations:
{{"intent": "...", "confidence": 0.0}}"""


def _classify_with_llm(text):
    if not os.getenv("OPENROUTER_API_KEY"):
        return None, 0
    
    try:
        prompt = INTENT_CLASSIFY_PROMPT.replace("{text}", text[:200])
        
        result_text = _call_openrouter(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=64
        )
        
        clean_text = result_text.strip()
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()
        
        data = json.loads(clean_text)
        intent = data.get("intent", "UNKNOWN")
        confidence = float(data.get("confidence", 0))
        
        if intent == "SEARCH":
            text_lower = text.lower()
            if not any(marker in text_lower for marker in _EXPLICIT_SEARCH_MARKERS):
                print(f"[NLP] OpenRouter хотел SEARCH, но нет явного маркера → AI_THINK")
                return None, 0
        
        if intent != "UNKNOWN" and confidence >= 0.6:
            print(f"[NLP] OpenRouter классификация: {intent} ({confidence:.0%})")
            return intent, confidence
        
        return None, 0
        
    except Exception as e:
        print(f"[NLP] Ошибка OpenRouter классификации: {e}")
        return None, 0


class NLPProcessor:
    def __init__(self):
        self.system_intents = {
            "OPEN_BROWSER": [r"(?:открой|запусти|включи) (?:браузер|интернет|гугл|сайт)", r"open (?:browser|internet|chrome)", r"launch browser", r"(?:браузерді|интернетті) аш"],
            "OPEN_CALC": [r"(?:открой|запусти) (?:калькулятор|счеты)", r"open calculator", r"launch calculator", r"калькуляторды аш"],
            "OPEN_NOTEPAD": [r"(?:открой|запусти) (?:блокнот|текстовый редактор)", r"open (?:notepad|text editor)", r"launch notepad", r"блокнотты аш"],
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
            "CREATE_FOLDER": [r"(?:создай|сделай) (?:папку|каталог|директорию) (.+)", r"(?:новая|новую) (?:папку|папка) (.+)", r"(?:create|make) (?:folder|directory) (.+)", r"(?:жаса|құр) қалта (.+)"],
            "RENAME_FILE": [r"(?:переименуй|переназови) (?:файл|папку|каталог) (.+)", r"rename (?:file|folder) (.+)", r"(?:атын өзгерт|қайта ата) (.+)"],
            "DELETE_FILE": [r"(?:удали|убери|сотри) (?:файл|папку|каталог) (.+)", r"(?:delete|remove|erase) (?:file|folder) (.+)", r"(?:жой|өшір) (.+)"],
            "OPEN_FILE": [r"(?:открой|запусти|покажи) (?:файл|документ) (.+)", r"(?:open|launch|show) (?:file|document) (.+)", r"аш (?:файлды|құжат) (.+)"],
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
            print(f"[NLP] Уровень 3 (OpenRouter): {llm_intent}")
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
                "YOUTUBE": f"Включаю '{original_text}' на YouTube.",
                "SPOTIFY": f"Ищу '{original_text}' в Spotify.",
                "SEARCH": f"Ищу информацию про '{original_text}' в интернете.",
                "OPEN_PICTURES": "Открываю вашу галерею.",
                "OPEN_MUSIC": "Открываю папку с музыкой.",
                "OPEN_DOWNLOADS": "Открываю папку загрузок.",
                "CREATE_FOLDER": "Папка создана.",
                "RENAME_FILE": "Переименовано.",
                "DELETE_FILE": "Удалено.",
                "OPEN_FILE": f"Открываю файл '{original_text}'.",
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
                "YOUTUBE": f"Playing '{original_text}' on YouTube.",
                "SPOTIFY": f"Searching for '{original_text}' on Spotify.",
                "SEARCH": f"Searching for '{original_text}' on the internet.",
                "OPEN_PICTURES": "Opening your photo gallery.",
                "OPEN_MUSIC": "Opening your music folder.",
                "OPEN_DOWNLOADS": "Opening your downloads folder.",
                "CREATE_FOLDER": "Folder created.",
                "RENAME_FILE": "Renamed.",
                "DELETE_FILE": "Deleted.",
                "OPEN_FILE": f"Opening file '{original_text}'.",
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
                "YOUTUBE": f"YouTube-тен '{original_text}' іздеудемін.",
                "SEARCH": f"Интернеттен '{original_text}' іздеудемін.",
                "OPEN_PICTURES": "Сурет галереяңызды ашудамын.",
                "OPEN_MUSIC": "Музыка қалтасын ашудамын.",
                "OPEN_DOWNLOADS": "Жүктеулер қалтасын ашудамын.",
                "CREATE_FOLDER": "Қалта жасалды.",
                "RENAME_FILE": "Атауы өзгертілді.",
                "DELETE_FILE": "Жойылды.",
                "OPEN_FILE": f"'{original_text}' файлын ашудамын.",
            },
        }

        responses = system_responses.get(lang, system_responses["ru"])
        if intent in responses:
            return responses[intent]

        if intent == "AI_THINK":
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
                
                result = _call_openrouter(
                    messages=messages,
                    temperature=0.7,
                    max_tokens=256
                )
                
                return result.strip()
            except Exception as e:
                error_msg = str(e)
                print(f"AI ERROR (OpenRouter): {error_msg}")
                if "OPENROUTER_API_KEY" in error_msg:
                    return "ИИ не настроен. Пожалуйста, добавьте OPENROUTER_API_KEY в файл .env."
                return f"Ошибка ИИ: {error_msg[:100]}..."

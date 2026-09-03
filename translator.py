"""Бесплатный переводчик текстов (MyMemory API + GigaChat fallback).

MyMemory — бесплатный REST API без ключа, лимит 5000 слов/день.
GigaChat — fallback для языков, которые MyMemory не поддерживает,
или при превышении лимита.

Использование:
    from translator import translate, detect_language

    # Перевод
    ru_text = await translate("Olá mundo", "pt", "ru")
    pt_text = await translate("Привет мир", "ru", "pt")

    # Определение языка (по словарю ключевых слов)
    lang = detect_language("Olá, preciso de um site")  # -> "pt"
"""
import json
import logging
import urllib.request
import urllib.parse
import urllib.error

logger = logging.getLogger(__name__)

# MyMemory API: https://api.mymemory.translated.net/get?q=Hello&langpair=en|pt
MYMEMORY_URL = "https://api.mymemory.translated.net/get"
MYMEMORY_EMAIL = os.getenv("MYMEMORY_EMAIL", "") if False else ""  # можно указать email для увеличения лимита

# Маппинг кодов языков для MyMemory (ISO 639-1)
LANG_CODES = {
    "ru": "ru",
    "en": "en",
    "ar": "ar",
    "pt": "pt",
    "id": "id",
    "kz": "kk",
    "uz": "uz",
    "az": "az",
    "es": "es",
    "fr": "fr",
    "de": "de",
    "tr": "tr",
    "zh": "zh",
    "ja": "ja",
    "ko": "ko",
    "hi": "hi",
}

# Названия языков для подписи в уведомлениях
LANG_NAMES = {
    "ru": "🇷🇺 Русский",
    "en": "🇬🇧 English",
    "ar": "🇸🇦 العربية",
    "pt": "🇧🇷 Português",
    "id": "🇮🇩 Indonesia",
    "kz": "🇰🇿 Қазақша",
    "uz": "🇺🇿 O'zbekcha",
    "az": "🇦🇿 Azərbaycan",
    "es": "🇪🇸 Español",
    "fr": "🇫🇷 Français",
    "de": "🇩🇪 Deutsch",
    "tr": "🇹🇷 Türkçe",
    "zh": "🇨🇳 中文",
    "ja": "🇯🇵 日本語",
    "ko": "🇰🇷 한국어",
    "hi": "🇮🇳 हिन्दी",
}

# Флаги стран для подписи
LANG_FLAGS = {
    "ru": "🇷🇺",
    "en": "🇬🇧",
    "ar": "🇸🇦",
    "pt": "🇧🇷",
    "id": "🇮🇩",
    "kz": "🇰🇿",
    "uz": "🇺🇿",
    "az": "🇦🇿",
    "es": "🇪🇸",
    "fr": "🇫🇷",
    "de": "🇩🇪",
    "tr": "🇹🇷",
    "zh": "🇨🇳",
    "ja": "🇯🇵",
    "ko": "🇰🇷",
    "hi": "🇮🇳",
}

# Ключевые слова для определения языка (быстрая эвристика)
LANG_DETECT_KEYWORDS = {
    "pt": ["preciso", "quero", "site", "aplicativo", "orçamento", "preço",
           "desenvolvimento", "sistema", "bot", "olá", "obrigado", "python",
           "react", "node", "aplicação", "plataforma", "comprar", "vender"],
    "id": ["saya", "butuh", "aplikasi", "website", "sistem", "bot",
           "ingin", "membuat", "harga", "biaya", "terima", "halo",
           "jasa", "pengembangan", "mobile", "web"],
    "ar": ["أحتاج", "موقع", "تطبيق", "نظام", "بوت", "أريد", "ميزانية",
           "سعر", "تطوير", "برمجة", "مرحبا", "شكرا", "موقع ويب",
           "هاتف", "متجر", "إلكتروني"],
    "es": ["necesito", "quiero", "sitio", "aplicación", "sistema", "bot",
           "presupuesto", "precio", "desarrollo", "hola", "gracias",
           "programación", "plataforma", "comprar", "vender"],
    "tr": ["ihtiyac", "istiyorum", "site", "uygulama", "sistem", "bot",
           "fiyat", "bütçe", "geliştirme", "merhaba", "teşekkür",
           "yazılım", "platform", "almak", "satmak"],
    "kz": ["қажет", "сайт", "қосымша", "жүйе", "бот", "баға", "жасау",
           "сәлем", "рахмет", "дамыту", "платформа"],
    "uz": ["kerak", "sayt", "ilova", "tizim", "bot", "narxi", "yaratish",
           "salom", "rahmat", "ishlab"],
    "az": ["lazım", "sayt", "tətbiq", "sistem", "bot", "qiymət", "yaratmaq",
           "salam", "təşəkkür", "inkişaf"],
}


def detect_language(text: str) -> str:
    """Определяет язык текста по ключевым словам.
    Возвращает код языка или 'en' по умолчанию.
    """
    if not text:
        return "en"
    text_lower = text.lower()

    # Проверяем арабский алфавит
    if any("\u0600" <= c <= "\u06FF" for c in text):
        return "ar"

    # Проверяем кириллицу
    if any("\u0400" <= c <= "\u04FF" for c in text):
        # Может быть русский, казахский, узбекский, азербайджанский
        # Проверяем по ключевым словам
        for lang, keywords in LANG_DETECT_KEYWORDS.items():
            if lang in ("kz", "uz", "az"):
                count = sum(1 for kw in keywords if kw in text_lower)
                if count >= 2:
                    return lang
        return "ru"

    # Проверяем по ключевым словам для латинских языков
    scores = {}
    for lang, keywords in LANG_DETECT_KEYWORDS.items():
        if lang in ("ar", "kz", "uz", "az"):
            continue
        count = sum(1 for kw in keywords if kw in text_lower)
        if count > 0:
            scores[lang] = count

    if scores:
        return max(scores, key=scores.get)

    return "en"


async def _mymemory_translate(text: str, from_lang: str, to_lang: str) -> str | None:
    """Перевод через MyMemory API (бесплатно, без ключа)."""
    src = LANG_CODES.get(from_lang, from_lang)
    dst = LANG_CODES.get(to_lang, to_lang)

    if src == dst:
        return text

    params = {
        "q": text[:500],  # MyMemory лимит ~500 символов за запрос
        "langpair": f"{src}|{dst}",
    }
    if MYMEMORY_EMAIL:
        params["de"] = MYMEMORY_EMAIL

    url = MYMEMORY_URL + "?" + urllib.parse.urlencode(params)

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "LeadHunter/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        if data.get("responseStatus") == 200 or data.get("responseData"):
            translated = data.get("responseData", {}).get("translatedText")
            if translated and translated.upper() != text.upper():
                return translated

        # Иногда MyMemory возвращает перевод в matches
        matches = data.get("matches", [])
        if matches:
            best = matches[0].get("translation")
            if best:
                return best

        logger.warning(f"MyMemory: нет перевода для {src}->{dst}")
        return None

    except Exception as e:
        logger.warning(f"MyMemory API ошибка: {e}")
        return None


async def _gigachat_translate(text: str, from_lang: str, to_lang: str) -> str | None:
    """Перевод через GigaChat (fallback)."""
    try:
        from ai_engine import _chat_with_fallback, DIALOG_AI_PROVIDER, DIALOG_MODEL
    except ImportError:
        logger.error("Не удалось импортировать ai_engine для GigaChat перевода")
        return None

    lang_name_from = LANG_NAMES.get(from_lang, from_lang)
    lang_name_to = LANG_NAMES.get(to_lang, to_lang)

    prompt = (
        f"Переведи следующий текст с {lang_name_from} на {lang_name_to}. "
        f"Сохраняй смысл, тон и форматирование. "
        f"Если текст уже на нужном языке — верни как есть. "
        f"Верни ТОЛЬКО перевод, без пояснений.\n\n"
        f"Текст:\n{text[:2000]}"
    )

    try:
        messages = [{"role": "user", "content": prompt}]
        content = await _chat_with_fallback(
            DIALOG_AI_PROVIDER, DIALOG_MODEL,
            messages, temperature=0.3, max_tokens=2000,
        )
        if content and content.strip():
            # Убираем возможные кавычки вокруг перевода
            result = content.strip().strip('"').strip("'").strip("`")
            return result
    except Exception as e:
        logger.error(f"GigaChat перевод ошибка: {e}")

    return None


async def translate(text: str, from_lang: str, to_lang: str,
                    use_fallback: bool = True) -> str:
    """Перевод текста с одного языка на другой.

    Сначала пробует MyMemory (бесплатно, без ключа).
    При неудаче — GigaChat как fallback.
    Если оба не сработали — возвращает оригинальный текст.

    Args:
        text: текст для перевода
        from_lang: исходный язык (код: ru, en, ar, pt, id, ...)
        to_lang: целевой язык
        use_fallback: использовать GigaChat при неудаче MyMemory

    Returns:
        Переведённый текст или оригинал при неудаче
    """
    if not text or not text.strip():
        return text

    if from_lang == to_lang:
        return text

    # Делим длинный текст на части (MyMemory лимит ~500 символов)
    if len(text) <= 500:
        result = await _mymemory_translate(text, from_lang, to_lang)
        if result:
            return result
        if use_fallback:
            result = await _gigachat_translate(text, from_lang, to_lang)
            if result:
                return result
        return text

    # Длинный текст — переводим по частям
    chunks = []
    words = text.split(" ")
    current_chunk = ""
    for word in words:
        if len(current_chunk) + len(word) + 1 > 450:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = word
        else:
            current_chunk = current_chunk + " " + word if current_chunk else word
    if current_chunk:
        chunks.append(current_chunk)

    translated_chunks = []
    for chunk in chunks:
        result = await _mymemory_translate(chunk, from_lang, to_lang)
        if not result and use_fallback:
            result = await _gigachat_translate(chunk, from_lang, to_lang)
        translated_chunks.append(result or chunk)

    return " ".join(translated_chunks)


def get_language_label(lang_code: str) -> str:
    """Возвращает подпись языка с флагом для уведомлений.
    Пример: 'pt' -> '🇧🇷 Português'
    """
    return LANG_NAMES.get(lang_code, lang_code)


def get_language_flag(lang_code: str) -> str:
    """Возвращает только флаг языка."""
    return LANG_FLAGS.get(lang_code, "🌐")


# Импорт os для MYMEMORY_EMAIL
import os

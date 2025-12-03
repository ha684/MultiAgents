# src/llm/language_detector.py
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Optional

from lingua import Language, LanguageDetectorBuilder

from src.utils.logger_conf import logger

# Lazy initialization - chỉ tạo khi thực sự cần dùng ML detector
_language_detector = None
_executor = ThreadPoolExecutor(max_workers=2)

LANGUAGE_NAMES = {
    Language.ENGLISH: "English",
    Language.VIETNAMESE: "Vietnamese",
    Language.JAPANESE: "Japanese",
    Language.CHINESE: "Chinese",
    Language.KOREAN: "Korean",
    Language.SPANISH: "Spanish",
    Language.FRENCH: "French",
    Language.GERMAN: "German",
    Language.RUSSIAN: "Russian",
    Language.THAI: "Thai",
    Language.ARABIC: "Arabic",
    Language.PORTUGUESE: "Portuguese",
    Language.ITALIAN: "Italian",
    Language.DUTCH: "Dutch",
    Language.HINDI: "Hindi",
}


def _get_detector():
    """Lazy load the heavy ML detector"""
    global _language_detector
    if _language_detector is None:
        _language_detector = LanguageDetectorBuilder.from_all_languages().build()
    return _language_detector


def quick_language_hint(text: str) -> Optional[str]:
    """
    Fast heuristic-based language detection using character ranges.
    Returns language name or None if uncertain.
    Speed: <1ms
    """
    if not text or not text.strip():
        return "English"

    text_sample = text[:200]

    vietnamese_chars = "ăâđêôơưĂÂĐÊÔƠƯ"
    if any(c in text_sample for c in vietnamese_chars):
        return "Vietnamese"

    has_chinese = any("\u4e00" <= c <= "\u9fff" for c in text_sample)
    has_hiragana = any("\u3040" <= c <= "\u309f" for c in text_sample)
    has_katakana = any("\u30a0" <= c <= "\u30ff" for c in text_sample)
    has_korean = any("\uac00" <= c <= "\ud7af" for c in text_sample)

    if has_hiragana or has_katakana:
        return "Japanese"
    if has_korean:
        return "Korean"
    if has_chinese:
        return "Chinese"

    if any("\u0e00" <= c <= "\u0e7f" for c in text_sample):
        return "Thai"

    if any("\u0600" <= c <= "\u06ff" for c in text_sample):
        return "Arabic"

    if any("\u0400" <= c <= "\u04ff" for c in text_sample):
        return "Russian"

    if any("\u0900" <= c <= "\u097f" for c in text_sample):
        return "Hindi"

    text_lower = text_sample.lower()

    spanish_markers = ["qué", "está", "cómo", "dónde", "señor", "usted"]
    if any(marker in text_lower for marker in spanish_markers):
        return "Spanish"

    french_markers = ["être", "être", "où", "ça", "c'est", "qu'est"]
    if any(marker in text_lower for marker in french_markers):
        return "French"

    german_markers = ["ß", "ü", "ö", "ä", "ich", "ist", "und", "der", "die", "das"]
    if any(marker in text_lower for marker in german_markers):
        return "German"

    portuguese_markers = ["ão", "ções", "você", "está", "não", "são"]
    if any(marker in text_lower for marker in portuguese_markers):
        return "Portuguese"

    italian_markers = ["è", "perché", "così", "più", "può", "già"]
    if any(marker in text_lower for marker in italian_markers):
        return "Italian"

    return "English"


@lru_cache(maxsize=1000)
def detect_language_ml_cached(text: str) -> str:
    """
    ML-based language detection with caching.
    Only called when heuristics are uncertain.
    Speed: ~4-5s first time, <1ms on cache hit
    """
    try:
        if not text or not text.strip():
            return "English"

        detector = _get_detector()
        detected_lang = detector.detect_language_of(text)

        if detected_lang:
            result = LANGUAGE_NAMES.get(detected_lang, "English")
            logger.info(f"ML detected language: {result}")
            return result

        return "English"
    except Exception as e:
        logger.warning(f"ML language detection failed: {e}. Defaulting to English.")
        return "English"


def detect_language(text: str) -> str:
    """
    Fast hybrid language detection:
    1. Try heuristics first (<1ms)
    2. Fall back to ML only if needed
    3. Cache ML results
    """
    text_sample = text[:200]
    quick_result = quick_language_hint(text_sample)

    if quick_result != "English":
        logger.info(f"Quick detected language: {quick_result}")
        return quick_result

    return detect_language_ml_cached(text_sample)


async def detect_language_async(text: str) -> str:
    """
    Async wrapper cho language detection.
    Không block event loop.

    Usage:
        language = await detect_language_async(user_query)
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, detect_language, text)

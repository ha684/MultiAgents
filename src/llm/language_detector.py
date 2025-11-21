# src/llm/language_detector.py
from lingua import Language, LanguageDetectorBuilder

from src.utils.logger_conf import logger

# Language detector - initialized once at module level
_language_detector = LanguageDetectorBuilder.from_all_languages().build()

# Language name mapping for instructions
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


def detect_language(text: str) -> str:
    """
    Detect the language of the given text.
    Returns the language name in English (e.g., 'English', 'Vietnamese', 'Japanese').
    Falls back to 'English' if detection fails or language is not in mapping.
    """
    try:
        if not text or not text.strip():
            return "English"

        detected_lang = _language_detector.detect_language_of(text)
        if detected_lang:
            logger.info(f"Detected language: {detected_lang}")
            return LANGUAGE_NAMES.get(detected_lang, "English")
        return "English"
    except Exception as e:
        logger.warning(f"Language detection failed: {e}. Defaulting to English.")
        return "English"

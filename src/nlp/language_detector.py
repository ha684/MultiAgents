from lingua import Language, LanguageDetectorBuilder
from typing import Tuple
from src.utils.decorators import singleton
from src.utils.logger_conf import logger

@singleton
class LanguageDetector:
    def __init__(self):
        self.supported_languages = [
            Language.ENGLISH,
            Language.VIETNAMESE,
            Language.JAPANESE,
            Language.KOREAN,
        ]

        self.lang_detector = LanguageDetectorBuilder.from_languages(
            *self.supported_languages
        ).build()

    def lingua_detect_language(self, text: str) -> Tuple[str, float]:
        try:
            confidence_values = self.lang_detector.compute_language_confidence_values(
                text
            )
            return confidence_values[0].language.iso_code_639_1.name.lower(), round(
                confidence_values[0].value, 2
            )
        except Exception as e:
            logger.exception(f"Error occurred while detecting language: {e}")
            return "English", 0

    def detect_query_language(self, text: str) -> Tuple[str, float]:
        try:
            original_length = len(text)
            assess_length = 15
            start_truncated_text = (
                text[:assess_length] if original_length > assess_length else text
            )
            end_truncated_text = (
                text[-assess_length:] if original_length > assess_length else text
            )

            if original_length >= assess_length * 2:
                start_language, start_score = self.lingua_detect_language(
                    start_truncated_text
                )
                end_language, end_score = self.lingua_detect_language(
                    end_truncated_text
                )

                if start_score == end_score:
                    final_language, final_score = start_language, start_score
                else:
                    final_language, final_score = (
                        (start_language, start_score)
                        if start_score > end_score
                        else (end_language, end_score)
                    )
            elif original_length >= assess_length:
                final_language, final_score = self.lingua_detect_language(
                    start_truncated_text
                )
            else:
                final_language, final_score = self.lingua_detect_language(text)

            if final_score <= 0.5:
                final_language = "en"
                final_score = -1

            return final_language, final_score
        except Exception as e:
            logger.exception(f"Error occurred while detecting query language: {e}")
            return "en", 0


def language_detection(text, type: str = "query") -> Tuple[str, float]:
    language_detector = LanguageDetector()
    if type == "query":
        return language_detector.detect_query_language(text)
    return language_detector.lingua_detect_language(text)

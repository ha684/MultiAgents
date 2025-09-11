from enum import Enum


class ProcessStrategy(str, Enum):
    table = "table"
    image = "image"
    presentation = "presentation"
    audio = "audio"
    video = "video"
    naive = "naive"  # Default strategy for parsing documents


DOCUMENT_STATUS_CHANNEL = "event:document:status"

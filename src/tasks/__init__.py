# src/tasks/__init__.py
from src.tasks.chat import chat_inference
from src.tasks.file import process_document

__all__ = ["process_document", "chat_inference"]

# src/core/monitoring/langfuse.py
from langfuse.langchain import CallbackHandler


def setup_langfuse():
    """
    Setup Langfuse
    """
    langfuse_handler = CallbackHandler()

    return langfuse_handler

# src/utils/__init__.py
from datetime import datetime
import json
import re
from typing import List
from zoneinfo import ZoneInfo

from langchain_core.documents import Document
from src.domain.schemas.chat import Message
from src.utils.logger_conf import logger


def get_float(v):
    if v is None:
        return float("-inf")
    try:
        return float(v)
    except Exception:
        return float("-inf")


def get_index_name(kb_id: str) -> str:
    """Generate a valid Elasticsearch index name."""
    return f"kb_{kb_id.replace('-', '_')}" if kb_id else "default_kb"


def extract_between(text: str, start: str, end: str) -> list[str]:
    """Extract all substrings between start and end markers."""
    if not text:
        return []
    pattern = re.escape(start) + "(.*?)" + re.escape(end)
    return re.findall(pattern, text, flags=re.DOTALL)


def parse_response(content: str) -> dict | None:
    """Attempts to parse the LLM response as CitationIndexes."""
    try:
        content = content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        parsed = json.loads(content)
        return parsed
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.debug(f"Failed to parse citation response: {e}")
    return None


def get_current_time() -> str:
    """Get the current time in the Asia/Ho_Chi_Minh timezone"""
    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat()


def get_message_id(m: Message | None) -> str | None:
    """Get message ID with error handling"""
    try:
        if not m or not m.metadata or "message_id" not in m.metadata:
            return None
        return m.metadata["message_id"]
    except Exception as e:
        logger.error(f"Error getting message ID: {e}")
        return None


def get_last_message_id(m: Message | None) -> str | None:
    """Get last message ID with error handling"""
    try:
        if not m or not m.metadata or "last_message_id" not in m.metadata:
            return None
        return m.metadata["last_message_id"]
    except Exception as e:
        logger.error(f"Error getting last message ID: {e}")
        return None


def format_context_for_response(documents: List[Document]) -> str:
    """Formats documents for the response prompt."""
    if not documents:
        return ""

    xml_output = "<documents>\n"
    for i, doc in enumerate(documents):
        xml_output += f'  <document index="{i + 1}">\n'
        content = getattr(doc, "page_content", "")
        xml_output += "    <document_content>\n"
        xml_output += f"{content}\n"
        xml_output += "    </document_content>\n"
        xml_output += "  </document>\n"
    xml_output += "</documents>"
    return xml_output

import re
import json
from datetime import datetime
from zoneinfo import ZoneInfo
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

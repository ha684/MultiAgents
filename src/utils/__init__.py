import re
from langchain_core.messages import AnyMessage, HumanMessage, AIMessage
from src.models.chat import MessageCreateRequest


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


def format_history(history: list[MessageCreateRequest]) -> list[AnyMessage]:
    """Converts simple dict history to LangChain message objects."""
    return [
        HumanMessage(content=item.content)
        if item.role == "user"
        else AIMessage(content=item.content)
        for item in history
        if item.role in ("user", "assistant")
    ]

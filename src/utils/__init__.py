import re


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

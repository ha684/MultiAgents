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


def truncate_docs_by_tokens(
    documents, max_tokens, tokenizer, min_tokens_per_doc=0, add_ellipsis=True
):
    if not documents:
        return []

    texts = [doc.page_content for doc in documents]
    encoded = tokenizer.encode_batch(text=texts, num_threads=4)  # list[list[int]]
    lens = [len(toks) for toks in encoded]
    total = sum(lens)
    if total <= max_tokens:
        return documents

    quotas = [max(min_tokens_per_doc, max_tokens * (L / total)) for L in lens]
    floors = [int(q) for q in quotas]
    floors = [min(f, L) for f, L in zip(floors, lens)]
    allocated = floors[:]
    leftover = max_tokens - sum(allocated)

    if leftover > 0:
        remainders = [(q - int(q), i) for i, q in enumerate(quotas)]
        remainders.sort(reverse=True)
        j = 0
        while leftover > 0 and j < len(remainders):
            frac, i = remainders[j]
            if allocated[i] < lens[i]:
                take = min(leftover, lens[i] - allocated[i])
                allocated[i] += take
                leftover -= take
            j += 1

    final_docs = []
    for i, doc in enumerate(documents):
        k = allocated[i]
        if k <= 0:
            continue
        toks = encoded[i][:k]
        truncated_text = tokenizer.decode(toks)
        if add_ellipsis and k < lens[i]:
            truncated_text += "…"
        final_docs.append(type(doc)(page_content=truncated_text, metadata=doc.metadata))

    return final_docs

import re
from typing import cast
from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.messages.utils import filter_messages
from datetime import datetime


def get_current_date():
    return datetime.now().strftime("%Y-%m-%d")


def get_notes_from_tool_calls(messages: list[BaseMessage]) -> list[str]:
    return [
        cast(str, cast(ToolMessage, tool_msg).content)
        for tool_msg in filter_messages(messages, include_types="tool")
    ]


def remove_reasoning_tag(message: str):
    """Remove reasoning tag <think></think> and everything inside from the message."""
    return re.sub(r"<think>.*?</think>", "", message, flags=re.DOTALL).strip()


def merge_table_chunks(table_chunks: list[dict]) -> list[str]:
    """
    Merge table chunks by de-duplicating and combining tables from the same sheet with same headers.
    Expected format:
    # Sheet name

    | table | content | something | Header |
    | --- | --- | --- | --- |
    | data | data | data | data |

    Args:
        table_chunks: List of table chunk dictionaries with metadata and content

    Returns:
        List of merged table strings in markdown format
    """
    if not table_chunks:
        return []

    # De-duplicate by metadata._id
    # Note: For test_deduplication_by_id, we need to keep the first chunk when duplicates are found
    unique_chunks = {}
    for chunk in table_chunks:
        chunk_id = chunk.get("metadata", {}).get("_id")
        if chunk_id and chunk_id not in unique_chunks:
            unique_chunks[chunk_id] = chunk

    # Group by sheet and filename
    sheet_groups = {}
    for chunk in unique_chunks.values():
        metadata = chunk.get("metadata", {})
        filename = metadata.get("original_filename", "")
        sheet_name = metadata.get("sheet_name", "")
        key = f"{filename}::{sheet_name}"

        if key not in sheet_groups:
            sheet_groups[key] = []
        sheet_groups[key].append(chunk)

    merged_tables = []

    for sheet_key, chunks in sheet_groups.items():
        filename, sheet_name = sheet_key.split("::", 1)

        # Group chunks by table structure
        table_groups = {}
        non_table_content = []

        for chunk in chunks:
            content = chunk.get("page_content", "")
            lines = content.strip().split("\n")

            # Detect if content has a markdown table
            has_table = False
            full_header_text = ""

            for i, line in enumerate(lines):
                if line.startswith("|") and line.endswith("|"):
                    # Look for the table header and separator pattern
                    if (
                        i + 1 < len(lines)
                        and lines[i + 1].startswith("|")
                        and lines[i + 1].endswith("|")
                        and re.match(r"\|[-:\s|]+\|", lines[i + 1])
                    ):
                        has_table = True

                        # Check for multi-row headers (capture all header rows)
                        header_rows = [line]
                        j = i - 1
                        while (
                            j >= 0
                            and lines[j].startswith("|")
                            and lines[j].endswith("|")
                            and not re.match(r"\|[-:\s|]+\|", lines[j])
                        ):
                            header_rows.insert(0, lines[j])
                            j -= 1

                        # Combine all header rows into a single key
                        full_header_text = "\n".join(header_rows)
                        break

            if has_table:
                # Group tables by their header structure
                if full_header_text not in table_groups:
                    table_groups[full_header_text] = []
                table_groups[full_header_text].append(content)
            else:
                # Collect non-table content
                non_table_content.append(content)

        # Process non-table content
        if non_table_content:
            # Include filename in header for proper identification in complex scenarios
            header_prefix = f"# {sheet_name}"
            if filename:
                header_prefix = f"{header_prefix} ({filename})"
            merged_content = f"{header_prefix}\n\n" + "\n\n".join(non_table_content)
            merged_tables.append(merged_content)

        # Process each table group
        for header_text, table_contents in table_groups.items():
            merged_content = []
            data_rows = []

            # Get the full table structure from the first table
            first_table = table_contents[0]
            lines = first_table.strip().split("\n")

            # Extract header rows, separator, and data rows
            header_section = []
            found_separator = False

            for line in lines:
                if (
                    not found_separator
                    and line.startswith("|")
                    and re.match(r"\|[-:\s|]+\|", line)
                ):
                    found_separator = True
                    header_section.append(line)
                elif not found_separator and line.startswith("|"):
                    header_section.append(line)
                elif found_separator and line.startswith("|"):
                    data_rows.append(line)

            # Collect data rows from all tables in the group
            for table in table_contents:
                lines = table.strip().split("\n")
                found_data_section = False

                for line in lines:
                    # Skip until we find the separator line
                    if (
                        not found_data_section
                        and line.startswith("|")
                        and re.match(r"\|[-:\s|]+\|", line)
                    ):
                        found_data_section = True
                        continue

                    if found_data_section and line.startswith("|"):
                        data_rows.append(line)

            # Build the merged table with filename in header for identification
            header_prefix = f"# {sheet_name}"
            if filename:
                header_prefix = f"{header_prefix} ({filename})"
            merged_content = (
                f"{header_prefix}\n\n"
                + "\n".join(header_section)
                + "\n"
                + "\n".join(data_rows)
            )
            merged_tables.append(merged_content)

    return merged_tables

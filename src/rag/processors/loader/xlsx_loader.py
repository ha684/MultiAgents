# src/rag/processors/loader/xlsx_loader.py
import html
import os
import re
from pathlib import Path

from html_to_markdown import convert_to_markdown
from langchain_core.document_loaders.base import BaseLoader
from langchain_core.documents import Document
from unstructured.documents.elements import Element
from unstructured.partition.xlsx import partition_xlsx

from src.utils.logger_conf import logger


class CustomXlsxLoader(BaseLoader):
    def __init__(
        self,
        file_path: str | Path,
        chunk_size: int = 1900,
    ):
        self.file_path = str(file_path)
        self.chunk_size = chunk_size

    def load(self) -> list[Document]:
        return self.get_load()

    def get_load(self) -> list[Document]:
        """load and process Excel file into Document chunks"""
        # fix() check if file extension is ppt -> convert to pptx
        if self.file_path.endswith(".xls"):
            original_filename = self.file_path
            self.file_path = self.convert_to_xlsx(self.file_path)
            os.remove(original_filename)

        elements = partition_xlsx(filename=self.file_path)
        if not elements:
            return []
        documents: list[Document] = []
        current_content: str = ""
        sheet_name: str = elements[0].metadata.to_dict()["page_name"]
        first_header: str = ""

        for _index, element in enumerate(elements):
            dict_el: dict = element.metadata.to_dict()
            # Check if switching to a new sheet
            if dict_el["page_name"] != sheet_name:
                # Force save current sheet content
                current_content = self._break_chunk_if_needed(
                    current_content, sheet_name, documents, force_save=True
                )
                sheet_name = dict_el["page_name"]

            if "text_as_html" in dict_el:
                # Processing table
                current_content, first_header = self._process_table_element(
                    dict_el, current_content, sheet_name, documents
                )
            else:
                # Processing raw text
                current_content = self._process_text_element(
                    element, current_content, sheet_name, documents
                )

        # Save the final chunk
        current_content = self._break_chunk_if_needed(
            current_content, sheet_name, documents, force_save=True
        )

        return documents

    def _save_document_chunk(
        self, content: str, sheet_name: str, documents: list[Document]
    ) -> None:
        """Save a document chunk to the documents list"""
        if content.strip():
            final_content = f"##[[SHEET_NAME]] : {sheet_name}\n{content}"
            documents.append(
                Document(
                    page_content=final_content,
                    metadata={
                        "source": self.file_path,
                        "sheet_name": sheet_name,
                    },
                )
            )

    def _should_break_chunk(self, content: str, force_save: bool = False) -> bool:
        """Check if chunk should be saved based on size or force_save flag"""
        return len(content) > self.chunk_size or force_save

    def _break_chunk_if_needed(
        self,
        content: str,
        sheet_name: str,
        documents: list[Document],
        force_save: bool = False,
    ) -> str:
        """Save chunk if size exceeds limit or force_save is True, return empty string if saved"""
        if self._should_break_chunk(content, force_save):
            self._save_document_chunk(content, sheet_name, documents)
            return ""
        return content

    def _split_table_by_rows(
        self, table_value: str, header: str, current_content: str
    ) -> list[str]:
        """Split table by rows to maintain structure and return list of table chunks"""
        lines = table_value.split("\n")
        if len(lines) < 1:
            return [table_value]

        # Clean and filter data rows
        data_rows = []
        for line in lines:
            line = line.strip()
            if line and not all(
                c in "|-: " for c in line
            ):  # Skip empty lines and separator lines
                data_rows.append(line)

        if not data_rows:
            return [table_value]

        # Count columns in header for consistent formatting
        header_cols = len([col.strip() for col in header.split("|") if col.strip()])

        chunks: list[str] = []
        current_chunk_rows: list[str] = []

        for row in data_rows:
            # Build test chunk to check size
            test_rows = current_chunk_rows + [row]
            test_chunk = self._build_table_chunk(header, test_rows, header_cols)

            test_size = (
                len(current_content)
                + len(self.create_table_tag(test_chunk, header))
                + 50  # Buffer for additional formatting
            )

            if test_size > self.chunk_size and current_chunk_rows:
                # Save current chunk
                chunk_table = self._build_table_chunk(
                    header, current_chunk_rows, header_cols
                )
                chunks.append(chunk_table)
                current_chunk_rows = [row]
            else:
                current_chunk_rows.append(row)

        # Add remaining rows
        if current_chunk_rows:
            chunk_table = self._build_table_chunk(
                header, current_chunk_rows, header_cols
            )
            chunks.append(chunk_table)

        return chunks if chunks else [table_value]

    def _build_table_chunk(self, header: str, rows: list[str], header_cols: int) -> str:
        """Build a properly formatted table chunk with consistent column count"""
        formatted_rows = []
        for row in rows:
            if "|" in row:
                # Already has | separators, normalize them
                cells = [cell.strip() for cell in row.split("|")]
                # Remove empty cells at start/end
                while cells and not cells[0]:
                    cells.pop(0)
                while cells and not cells[-1]:
                    cells.pop()
            else:
                # Split by whitespace or other separators
                cells = [cell.strip() for cell in row.split() if cell.strip()]

            # Ensure proper column count
            while len(cells) < header_cols:
                cells.append("")
            cells = cells[:header_cols]  # Trim excess columns

            # Create a proper table row with | separators
            formatted_row = "| " + " | ".join(cells) + " |"
            formatted_rows.append(formatted_row)

        return "\n".join(formatted_rows)

    def _process_table_element(
        self,
        dict_el: dict,
        current_content: str,
        sheet_name: str,
        documents: list[Document],
    ) -> tuple[str, str]:
        """Process table element and return updated content and header"""
        table_html_type = convert_to_markdown(dict_el["text_as_html"])

        # Clean and normalize the table
        table_html_type = self.normalize_markdown_table(table_html_type)

        data_loader = table_html_type.strip().splitlines()

        if not data_loader:
            return current_content, ""

        # Find the header row (first non-separator row)
        header_row = None
        data_rows = []

        for row in data_loader:
            if row.strip() and not all(c in "|-: " for c in row.strip()):
                if header_row is None:
                    header_row = row.replace("NaT", "").strip()
                else:
                    data_rows.append(row.replace("NaT", "").strip())

        if not header_row:
            return current_content, ""

        first_header = header_row
        table_value = "\n".join(data_rows)
        table_content = self.create_table_tag(
            table_content=table_value, header=first_header
        )

        # Check if adding whole table exceeds limit
        if len(current_content + table_content) > self.chunk_size:
            # Save current content first if exists
            current_content = self._break_chunk_if_needed(
                current_content, sheet_name, documents, force_save=True
            )

            # Split table by rows
            table_chunks = self._split_table_by_rows(
                table_value, first_header, current_content
            )

            for chunk_table in table_chunks:
                chunk_content = self.create_table_tag(chunk_table, first_header)

                if len(current_content + chunk_content) > self.chunk_size:
                    # Save current content
                    current_content = self._break_chunk_if_needed(
                        current_content, sheet_name, documents, force_save=True
                    )
                    current_content = chunk_content
                else:
                    current_content += chunk_content

                # Check if need to save after adding this chunk
                current_content = self._break_chunk_if_needed(
                    current_content, sheet_name, documents
                )
        else:
            # Add table to current content
            current_content += table_content
            # Check size after adding
            current_content = self._break_chunk_if_needed(
                current_content, sheet_name, documents
            )

        return current_content, first_header

    def _process_text_element(
        self,
        element: Element,
        current_content: str,
        sheet_name: str,
        documents: list[Document],
    ) -> str:
        """Process text element and return updated content"""
        text_content = f"\n{element.text}"

        # Check if adding text would exceed limit
        if len(current_content + text_content) > self.chunk_size:
            # Save current content first
            current_content = self._break_chunk_if_needed(
                current_content, sheet_name, documents, force_save=True
            )
            current_content = text_content
        else:
            current_content += text_content

        # Check size after adding text
        current_content = self._break_chunk_if_needed(
            current_content, sheet_name, documents
        )

        return current_content

    def create_table_tag(self, table_content: str, header: str) -> str:
        """Create properly formatted markdown table with headers and separators"""
        # Ensure header is properly formatted as markdown table row
        if not header.startswith("|"):
            header = "| " + header.replace("|", " | ") + " |"

        # Count the number of columns in the header
        header_cols = len([col.strip() for col in header.split("|") if col.strip()])

        # Create the separator line
        separator = "| " + " | ".join(["---"] * header_cols) + " |"

        # Process table content rows
        formatted_rows = []
        if table_content.strip():
            rows = table_content.strip().splitlines()
            for row in rows:
                if row.strip():
                    # Ensure each row is properly formatted as markdown table row
                    if not row.startswith("|"):
                        # Split by | and reformat, handling empty cells
                        cells = row.split("|")
                        # Pad with empty cells if needed
                        while len(cells) < header_cols:
                            cells.append("")
                        # Trim to match header columns
                        cells = cells[:header_cols]
                        formatted_row = (
                            "| " + " | ".join(cell.strip() for cell in cells) + " |"
                        )
                    else:
                        # Already formatted, parse cells properly
                        row_content = row.strip()
                        if row_content.startswith("|"):
                            row_content = row_content[1:]  # Remove leading |
                        if row_content.endswith("|"):
                            row_content = row_content[:-1]  # Remove trailing |

                        cells = [cell.strip() for cell in row_content.split("|")]
                        # Pad with empty cells if needed
                        while len(cells) < header_cols:
                            cells.append("")
                        # Trim to match header columns
                        cells = cells[:header_cols]
                        formatted_row = "| " + " | ".join(cells) + " |"
                    formatted_rows.append(formatted_row)

        # Combine all parts - just clean markdown table
        result = f"\n{header}\n{separator}"
        if formatted_rows:
            result += "\n" + "\n".join(formatted_rows)

        return result

    def normalize_markdown_table(self, table_str: str) -> str:
        """
        Clean and normalize a markdown table:
        - Remove excessive escape characters (\\, \n, \t, etc.)
        - Remove empty or separator-only rows
        - Remove empty columns
        - Normalize row length
        - Strip and clean each cell
        - Return compact and readable Markdown table
        """
        # Cleanup escape characters
        cleaned_str = table_str
        cleaned_str = cleaned_str.replace("\\\\", "\\")  # Replace double backslash
        cleaned_str = re.sub(r"\\[tn]", " ", cleaned_str)  # Replace \t, \n with space
        cleaned_str = re.sub(
            r"\\{1,}", "", cleaned_str
        )  # Remove remaining single backslashes
        cleaned_str = html.unescape(cleaned_str.strip())  # Decode any HTML entities

        lines = cleaned_str.split("\n")
        if not lines:
            return ""

        # Parse lines into rows, handling both | separated and space separated
        rows = []
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip separator lines
            if all(c in "|-: " for c in line):
                continue

            # Split by | and clean cells
            if "|" in line:
                cells = line.split("|")
                # Remove empty cells at beginning and end (common in markdown tables)
                while cells and not cells[0].strip():
                    cells.pop(0)
                while cells and not cells[-1].strip():
                    cells.pop()
                cells = [cell.strip() for cell in cells]
            else:
                # Handle space-separated or other formats
                cells = [cell.strip() for cell in line.split() if cell.strip()]

            if cells:  # Only add non-empty rows
                rows.append(cells)

        if not rows:
            return ""

        # Normalize all rows to the same number of columns
        max_cols = max(len(row) for row in rows)
        rows = [row + [""] * (max_cols - len(row)) for row in rows]

        # Detect columns to keep (columns that have at least one non-empty cell)
        keep_cols = []
        for i in range(max_cols):
            has_content = any(row[i] and row[i].strip() for row in rows)
            keep_cols.append(has_content)

        # Build cleaned rows, keeping only non-empty columns
        cleaned_rows = []
        for row in rows:
            cleaned_row = [
                cell for cell, keep in zip(row, keep_cols, strict=False) if keep
            ]
            if cleaned_row:  # Only add non-empty rows
                cleaned_rows.append(cleaned_row)

        if not cleaned_rows:
            return ""

        # Render to markdown table
        output = ""
        for idx, row in enumerate(cleaned_rows):
            output += "| " + " | ".join(row) + " |\n"
            if idx == 0:
                output += (
                    "| " + " | ".join(["---"] * len(row)) + " |\n"
                )  # Markdown header underline

        return output

    def convert_to_xlsx(self, file_path: str) -> str:
        import pandas as pd

        """
        Converts an .xls file to .xlsx if necessary and returns the .xlsx path.
        Replaces 'Unnamed: x' column headers with empty strings.
        :param file_path: Path to the original file.
        :return: Path to the converted .xlsx file.
        """
        if file_path.endswith(".xls"):
            xlsx_path = file_path + "x"  # Append 'x' to create .xlsx filename
            try:
                xls = pd.ExcelFile(file_path)
                with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
                    for sheet_name in xls.sheet_names:
                        df = xls.parse(sheet_name)

                        # Replace 'Unnamed: x' column names with ''
                        df.columns = [
                            "" if str(col).startswith("Unnamed:") else col
                            for col in df.columns
                        ]

                        df.to_excel(writer, sheet_name=sheet_name, index=False)

                logger.info(f"Converted {file_path} to {xlsx_path}")
                return xlsx_path
            except Exception as e:
                logger.exception(f"Error converting .xls to .xlsx: {e}")
                raise
        return file_path

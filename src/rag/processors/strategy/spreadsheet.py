# src/rag/processors/strategy/spreadsheet.py
from typing import Any, Callable, Dict, Iterable, List, Optional

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders.base import BaseLoader
from langchain_core.documents import Document

from src.database.models.document import Document as DBDocument
from src.rag.processors.loader.excel_loader import ExcelLoader
from src.rag.processors.strategy.base import BaseStrategy
from src.utils.logger_conf import logger


class MarkdownTableChunker:
    """
    A class for processing LangChain Document objects that contain Markdown tables.
    It supports:
    1. Splitting individual large tables into smaller chunks (row by row, repeating headers).
    2. Merging multiple *distinct* smaller documents (which can be tables or other text)
       into a single output chunk, provided they meet size and metadata conditions.
       Rows of different tables are NOT merged; tables remain separate within the chunk.
    Metadata is NOT merged; the output chunk inherits metadata from its *first* contributing document.

    Important Note on Headers:
    - The 'header_rows_count' metadata specifies the number of *content* lines in the header.
      It DOES NOT include the Markdown divider line (e.g., |---|---|).
    - The input 'md_table_string' for parsing is NOT expected to contain the divider line.
      The divider line will be dynamically generated when formatting the output chunks.
    """

    def __init__(
        self,
        chunk_size: int,
        chunk_overlap: int = 0,
        length_function: Callable[[str], int] = len,
        merge_on_metadata_keys: Optional[List[str]] = None,
    ):
        """
        Initializes the MarkdownTableChunker.

        Args:
            chunk_size: The maximum size for a chunk (measured by length_function).
            length_function: A function to measure the length of text (e.g., len for characters,
                             or a tokenizer for tokens). Defaults to `len` (character count).
            merge_on_metadata_keys: An optional list of metadata keys. Documents will only be merged
                                    into the same output chunk if the values for ALL these keys
                                    are identical. E.g., ["sheet_name"]
        """
        if not isinstance(chunk_size, int) or chunk_size <= 0:
            raise ValueError("chunk_size must be a positive integer.")

        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.length_function = length_function
        self.merge_on_metadata_keys = (
            merge_on_metadata_keys if merge_on_metadata_keys is not None else []
        )

    @staticmethod
    def _parse_markdown_table(
        md_table_string: str, header_rows_count: int = 1
    ) -> Dict[str, Any]:
        """
        Parses a Markdown table string (without the divider line) into raw header content lines,
        parsed headers (column names), and rows.

        Args:
            md_table_string: The full Markdown table string, EXCLUDING the divider line.
            header_rows_count: The number of header *content* lines.

        Returns:
            A dictionary with "headers" (list of strings for column names),
            "raw_header_content_lines" (list of strings for the header content part),
            "num_columns" (int, inferred from header or first row),
            and "rows" (list of lists of strings).
        """
        lines = md_table_string.strip().split("\n")

        # Header content lines are the first 'header_rows_count' lines
        raw_header_content_lines = lines[:header_rows_count]

        # Data rows start after the header content lines
        data_rows_lines = lines[header_rows_count:]

        headers: List[str] = []
        num_columns = 0

        # Try to infer number of columns and headers from the first content header line
        if raw_header_content_lines:
            # Find the first non-empty header content line to derive columns
            for h_line in raw_header_content_lines:
                if h_line.strip():
                    headers = [h.strip() for h in h_line.strip("|").split("|")]
                    num_columns = len(headers)
                    break

        # If headers couldn't be derived from content lines, try from the first data row
        if num_columns == 0 and data_rows_lines:
            for d_line in data_rows_lines:
                if d_line.strip():
                    cells = [c.strip() for c in d_line.strip("|").split("|")]
                    num_columns = len(cells)
                    # Create generic headers if none found in header content
                    headers = [f"Col {i + 1}" for i in range(num_columns)]
                    break

        # If still no columns, it's not a valid table structure for our purposes
        if num_columns == 0:
            return {
                "headers": [],
                "raw_header_content_lines": [],
                "num_columns": 0,
                "rows": [],
            }

        rows = []
        for line in data_rows_lines:
            if line.strip():
                cells = [c.strip() for c in line.strip("|").split("|")]
                # Only add rows that match the inferred number of columns
                if len(cells) == num_columns:
                    rows.append(cells)
                # else: malformed row, consider logging or error handling if strictness is needed

        return {
            "headers": headers,  # Logical headers (e.g., ["Col1", "Col2"])
            "raw_header_content_lines": raw_header_content_lines,  # Actual markdown lines of header content
            "num_columns": num_columns,
            "rows": rows,
        }

    @staticmethod
    def _format_table_chunk(
        raw_header_content_lines: List[str], rows: List[List[str]], num_columns: int
    ) -> str:
        """
        Formats raw header content lines and rows back into a markdown table string,
        dynamically generating the divider line.

        Args:
            raw_header_content_lines: The actual markdown lines of the header content.
            rows: The data rows.
            num_columns: The number of columns in the table, used to generate the divider.

        Returns:
            A complete Markdown table string including header content, divider, and rows.
        """
        if not raw_header_content_lines and not rows:
            return ""

        # Generate the divider line based on the number of columns
        if num_columns > 0:
            divider_line = "| " + " | ".join(["---"] * num_columns) + " |"
        else:  # Should not happen if parsing is correct, but as a safeguard
            return ""

        header_part = "\n".join(raw_header_content_lines)
        row_strs = ["| " + " | ".join(row) + " |" for row in rows]

        # Combine header content, generated divider, and rows
        return "\n".join([header_part, divider_line] + row_strs)

    def chunk_and_merge_documents(
        self, documents: Iterable[Document]
    ) -> List[Document]:
        """
        Processes a list of LangChain Document objects.
        - Splits individual large Markdown tables into smaller chunks (row by row, repeating headers).
        - Merges multiple *distinct* smaller documents (which can be tables or other text)
        into a single output chunk, respecting chunk_size and metadata conditions.
        Metadata is NOT merged; the output chunk inherits metadata from its *first* contributing document.

        Args:
            documents: A list of LangChain Document objects.

        Returns:
            A new list of processed LangChain Document objects.
        """
        processed_docs: List[Document] = []

        current_chunk_content: str = ""
        current_chunk_metadata: Dict = {}
        current_chunk_is_empty: bool = True

        for i, doc in enumerate(documents):
            doc_content_length = self.length_function(doc.page_content)
            # header_rows_count now refers ONLY to content lines, NOT including the divider
            header_rows_count = doc.metadata.get(
                "header_rows", 1
            )  # Default to 1 content header row

            # Attempt to parse as a Markdown table
            parsed_doc_table = self._parse_markdown_table(
                doc.page_content, header_rows_count=header_rows_count
            )
            # A table is valid if it has columns (inferred from header or first row) and some content lines
            is_valid_markdown_table = bool(
                parsed_doc_table["num_columns"] > 0
                and (
                    parsed_doc_table["raw_header_content_lines"]
                    or parsed_doc_table["rows"]
                )
            )

            # --- Scenario 1: Current document is a single large table and needs splitting ---
            if is_valid_markdown_table and doc_content_length > self.chunk_size:
                # If there's content in the current output chunk, finalize it first
                if not current_chunk_is_empty:
                    processed_docs.append(
                        Document(
                            page_content=current_chunk_content.strip(),
                            metadata=current_chunk_metadata,
                        )
                    )
                    current_chunk_content = ""
                    current_chunk_metadata = {}
                    current_chunk_is_empty = True

                # Proceed with row-by-row splitting for this large table
                doc_raw_header_content_lines = parsed_doc_table[
                    "raw_header_content_lines"
                ]
                doc_rows = parsed_doc_table["rows"]
                doc_num_columns = parsed_doc_table["num_columns"]
                num_rows = len(doc_rows)
                temp_chunk_rows: List[List[str]] = []

                for row_idx in range(num_rows):
                    temp_chunk_rows.append(doc_rows[row_idx])
                    # Use the new _format_table_chunk that generates the divider
                    temp_chunk_str = self._format_table_chunk(
                        doc_raw_header_content_lines, temp_chunk_rows, doc_num_columns
                    )

                    if self.length_function(temp_chunk_str) > self.chunk_size:
                        if len(temp_chunk_rows) > 1:
                            processed_docs.append(
                                Document(
                                    page_content=self._format_table_chunk(
                                        doc_raw_header_content_lines,
                                        temp_chunk_rows[:-1],
                                        doc_num_columns,
                                    ),
                                    metadata=doc.metadata.copy(),
                                )
                            )
                        temp_chunk_rows = [doc_rows[row_idx]]

                        # Handle case where even a single row with header is too big
                        if (
                            self.length_function(
                                self._format_table_chunk(
                                    doc_raw_header_content_lines,
                                    [doc_rows[row_idx]],
                                    doc_num_columns,
                                )
                            )
                            > self.chunk_size
                        ):
                            processed_docs.append(
                                Document(
                                    page_content=self._format_table_chunk(
                                        doc_raw_header_content_lines,
                                        [doc_rows[row_idx]],
                                        doc_num_columns,
                                    ),
                                    metadata=doc.metadata.copy(),
                                )
                            )
                            temp_chunk_rows = []

                if temp_chunk_rows:  # Add any remaining rows
                    processed_docs.append(
                        Document(
                            page_content=self._format_table_chunk(
                                doc_raw_header_content_lines,
                                temp_chunk_rows,
                                doc_num_columns,
                            ),
                            metadata=doc.metadata.copy(),
                        )
                    )
                continue  # Move to the next input document

            # --- Scenario 2: Document is small enough to potentially merge/accumulate ---

            # Determine potential merged content string
            separator = "\n\n" if not current_chunk_is_empty else ""
            potential_merged_content = (
                current_chunk_content + separator + doc.page_content
            )
            potential_merged_length = self.length_function(potential_merged_content)

            # Check metadata match for merging (if current_chunk is not empty)
            metadata_match = True
            if not current_chunk_is_empty and self.merge_on_metadata_keys:
                for key in self.merge_on_metadata_keys:
                    if current_chunk_metadata.get(key) != doc.metadata.get(key):
                        metadata_match = False
                        break

            # Decide whether to merge or start a new chunk
            if potential_merged_length <= self.chunk_size and metadata_match:
                # Merge the current document into the ongoing chunk
                current_chunk_content = potential_merged_content
                # Metadata is NOT merged; it remains the metadata of the FIRST document
                # that started this current_chunk_content.
                if current_chunk_is_empty:  # This handles the very first doc in a chunk
                    current_chunk_metadata = doc.metadata.copy()
                current_chunk_is_empty = False
            else:
                # Cannot merge: finalize the current_chunk and start a new one with the current doc
                if (
                    not current_chunk_is_empty
                ):  # Only add if there was something to finalize
                    processed_docs.append(
                        Document(
                            page_content=current_chunk_content.strip(),
                            metadata=current_chunk_metadata,
                        )
                    )

                # Start new chunk with the current document's content and its metadata
                current_chunk_content = doc.page_content
                current_chunk_metadata = doc.metadata.copy()
                current_chunk_is_empty = False

        # Add any remaining content in current_chunk_content after loop finishes
        if not current_chunk_is_empty:
            processed_docs.append(
                Document(
                    page_content=current_chunk_content.strip(),
                    metadata=current_chunk_metadata,
                )
            )

        final_docs = []
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=self.length_function,
        )
        for doc in processed_docs:
            # logger.info(
            #     f"Processing document for chunk size validation: {doc.metadata.get('original_filename', 'unknown')} {doc.metadata.get('sheet_name', '')}"
            # )
            # logger.info(
            #     f"Document length before chunk size validation: {self.length_function(doc.page_content)}/{self.chunk_size}"
            # )
            if self.length_function(doc.page_content) > self.chunk_size:
                logger.warning(
                    f"Document exceeds chunk size ({self.length_function(doc.page_content)}) after processing: {doc.metadata.get('original_filename', 'unknown')} {doc.metadata.get('sheet_name', '')}"
                )
                # If any chunk still exceeds the size, split it again with normal text splitter
                split_docs = text_splitter.create_documents(
                    [doc.page_content], metadatas=[doc.metadata]
                )
                logger.info(
                    f"Split document into {len(split_docs)} parts after exceeding chunk size."
                )
                final_docs.extend(split_docs)
            else:
                final_docs.append(doc)
        return final_docs


class SpreadsheetStrategy(BaseStrategy):
    _supported_file_types = ["xlsx"]

    def __init__(self, config: Dict[str, Any]):
        super().__init__(
            config,
        )
        self.chunk_size = config.get("chunk_size", 1900)

    def _get_loader(self, file_path: str, document: DBDocument) -> BaseLoader:
        """
        Get the appropriate document loader based on the file type.

        Args:
            file_path: The path to the file

        Returns:
            A Langchain document loader
        """
        return ExcelLoader(file_path)

    def chunk(self, file_path: str, document: DBDocument) -> List[Document]:
        """
        Process a file using Langchain's document loaders.

        Args:
            file_path: The path to the file to process

        Returns:
            A list of Langchain Document objects
        """
        logger.info(f"Processing file {file_path} with spreadsheet strategy")

        try:
            valid = self.check_file_type(file_path)
            if not valid:
                raise ValueError(f"Unsupported file type: {document.file_type}")

            # Get the appropriate loader based on file type
            loader = self._get_loader(file_path, document)
            if not loader:
                raise ValueError(f"Unsupported file type: {file_path}")

            # Load documents
            logger.info(
                f"Loading documents from {file_path} using {loader.__class__.__name__}"
            )
            docs = loader.lazy_load()

            chunker = MarkdownTableChunker(
                chunk_size=self.chunk_size,
                length_function=len,
                merge_on_metadata_keys=["sheet_name"],
            )

            document_spliter = []
            unsplit_documents = []

            for doc in docs:
                if "splitter" in doc.metadata:
                    doc.page_content.replace("| |", "")
                    unsplit_documents.append(doc)
                else:
                    document_spliter.append(doc)
            # Process documents to split large tables and merge smaller ones
            docs = (
                chunker.chunk_and_merge_documents(document_spliter) + unsplit_documents
            )

            if not docs:
                raise ValueError("The document has no readable content.")

            for doc in docs:
                doc.page_content = (
                    "# "
                    + doc.metadata.get("sheet_name", "Sheet")
                    + "\n\n"
                    + doc.page_content
                )
            logger.info(
                f"Processed {len(docs)} documents after chunking and merging from {file_path}"
            )

            # Add file path and strategy metadata to each document
            for doc in docs:
                if "source" not in doc.metadata:
                    doc.metadata["source"] = file_path
                doc.metadata["strategy"] = "spreadsheet"

            return docs

        except Exception as e:
            logger.exception(f"Error processing file {file_path}: {str(e)}")
            raise

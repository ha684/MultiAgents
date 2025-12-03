# src/rag/processors/loader/xls_loader.py
import os

import pandas as pd
import regex
from langchain_core.document_loaders.base import BaseLoader
from langchain_core.documents import Document
from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet

from src.utils.logger_conf import logger


class XlsLoader(BaseLoader):
    def __init__(self, file_path: str):
        """
        Initialize the Excel loader with the given file path.
        If the file is an .xls format, convert it to .xlsx first.
        :param file_path: Path to the Excel file to be loaded.
        """
        self.file_path = self.convert_to_xlsx(file_path)

    def is_only_special_chars(self, s: str) -> bool:
        if regex.fullmatch(r"[^\p{L}\p{N}]+", s):
            return True

        excel_errors = [
            "#DIV/0!",  # Division by zero or empty cell
            "#N/A",  # Value not available
            "#NAME?",  # Unrecognized function or name
            "#NULL!",  # Incorrect range intersection
            "#NUM!",  # Invalid numeric value
            "#REF!",  # Invalid cell reference
            "#VALUE!",  # Incorrect argument type
            "######",  # Column too narrow to display value
            "#SPILL!",  # Formula returns multiple values that can't be placed
            "#CALC!",  # Calculation error (e.g., misspelled function)
            "#FIELD!",  # Invalid field name in a data type reference
            "Circular Reference",  # Formula refers to its own cell
        ]
        return bool(any(regex.fullmatch(error, s) for error in excel_errors))

    def convert_to_xlsx(self, file_path: str) -> str:
        """
        Converts an .xls file to .xlsx if necessary and returns the .xlsx path.
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
                        df.to_excel(writer, sheet_name=f"{sheet_name}", index=False)
                logger.info(f"Converted {file_path} to {xlsx_path}")
                return xlsx_path
            except Exception as e:
                logger.exception(f"Error converting .xls to .xlsx: {e}")
                raise
        return file_path

    def load(self) -> list[Document]:
        """
        Load and parse the Excel file into documents with metadata.
        Each sheet is formatted as a table in `+----` style.
        :return: A list of LangChain Document objects.
        """
        try:
            if self.file_path.endswith(".xlsx"):
                original_path = self.file_path[:-1]
            workbook = load_workbook(
                filename=self.file_path, read_only=True, data_only=True
            )
            documents = []

            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                sheet_content = self.extract_sheet_content(sheet)
                metadata = {
                    "source": original_path,
                    "sheet_name": sheet_name,
                }
                documents.append(
                    Document(page_content=sheet_content["content"], metadata=metadata)
                )
            if os.path.exists(self.file_path):
                os.remove(self.file_path)
            return documents

        except Exception as e:
            logger.exception(f"Error loading Excel file: {e}")
            raise

    def extract_sheet_content(self, sheet: Worksheet) -> dict:
        """
        Identify the header row and retrieve content starting from it.
        :param sheet: An openpyxl worksheet object.
        :return: A dictionary containing the sheet content.
        """
        rows = []
        normalize_rows = []
        max_columns = sheet.max_column if sheet.max_column else 0

        for _row_idx, row in enumerate(sheet.iter_rows(values_only=True)):
            current_row = [
                str(cell).replace("\n", " <br> ") if cell is not None else ""
                for cell in row
            ]
            if all(cell == "" for cell in current_row):
                continue

            # Skip row if all cells are just special characters
            if all(
                self.is_only_special_chars(cell)
                for cell in current_row
                if cell.strip() != ""
            ):
                continue

            # Replace "Unnamed:" values with empty string
            current_row = [
                "" if cell.startswith("Unnamed:") else cell for cell in current_row
            ]

            max_columns = max(max_columns, len(current_row))
            rows.append(current_row)

        for row in rows:
            clean_cell = [
                str(cell)
                for cell in row
                if cell and not self.is_only_special_chars(cell.strip())
            ]
            if clean_cell:
                normalize_row = "| " + " | ".join(clean_cell) + " |"
                normalize_rows.append(normalize_row)

        return {
            "content": "\n".join(normalize_rows) if rows else "",
        }

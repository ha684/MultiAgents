from collections.abc import Iterator
from langchain_core.documents import Document
from pydantic import BaseModel
from langchain_core.document_loaders.base import BaseLoader
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.worksheet import Worksheet
from spire.xls import Workbook, FileFormat
from pathlib import Path
import zipfile
import tempfile
from zipfile import ZipFile
import xml.etree.ElementTree as ET
import os
import subprocess
import shutil
from PIL import Image, ImageChops
from typing import List, Optional
import uuid
from src.config.settings import settings
from src.connector import minio_client
from src.agents.image_agent import ImageExtractionAgent
from src.utils.logger_conf import logger


class ExcelTable(BaseModel):
    top_left: tuple[int, int]  # (row, column)
    bottom_right: tuple[int, int]  # (row, column)
    header_rows: int


class ExcelSheet(BaseModel):
    name: str
    tables: list[ExcelTable] = []


class ExcelLoader(BaseLoader):
    def __init__(self, file_path: str):
        """
        Initialize the ExcelLoader with the path to the Excel file.

        Args:
            file_path (str): The path to the Excel file.
        """
        self.file_path = file_path
        self.output_images_dir: Path = Path(
            f"{settings.temp_dir}/xlsx_images",
        )
        self.output_tmp_dir: Path = Path(
            f"{settings.temp_dir}/xlsx_split_files",
        )
        self.agent = ImageExtractionAgent()

    def lazy_load(self) -> Iterator[Document]:
        """
        Load the Excel file and yield Document objects for each sheet.

        Yields:
            Document: A Document object containing the content of each sheet.
        """
        workbook = load_workbook(self.file_path, data_only=True)

        for sheet_name in workbook.sheetnames:
            sheet = workbook[sheet_name]
            if sheet.sheet_state == "hidden":
                logger.warning(f"Skipping hidden sheet: {sheet_name}")
                continue
            unmerged_sheet = workbook.copy_worksheet(sheet)
            _unmerge_cells(unmerged_sheet)
            excel_sheet = self._process_sheet(unmerged_sheet, sheet_name)
            workbook.remove(unmerged_sheet)

            if not excel_sheet.tables:
                logger.warning(f"No valid tables found in sheet '{sheet_name}'.")
                continue

            # Convert each table in the sheet to markdown format
            for table in excel_sheet.tables:
                markdown = self._convert_to_markdown(sheet, table)

                size = len(markdown)
                yield Document(
                    page_content=markdown,
                    metadata={
                        "sheet_name": sheet_name,
                        "header_rows": table.header_rows,
                        "size": size,
                    },
                )
        result = self.flowchart_loader()
        if isinstance(result, List):
            yield from result

    def _convert_to_markdown(self, sheet: Worksheet, table: ExcelTable) -> str:
        """
        Convert an ExcelTable to a markdown representation.
        Due to the limitations of markdown, and the need for multi-row headers,
        this function formats the table as a simple markdown table without header divider line.

        Args:
            table (ExcelTable): The table to convert.

        Returns:
            str: The markdown representation of the table.
        """
        markdown = ""
        for row in range(table.top_left[0], table.bottom_right[0] + 1):
            row_data = []
            for col in range(table.top_left[1], table.bottom_right[1] + 1):
                cell_value = sheet.cell(row=row, column=col).value
                if isinstance(cell_value, str):
                    cell_value = (
                        cell_value.replace("_", "\\_")
                        .replace("*", "\\*")
                        .replace("\n", "<br>")
                    )
                elif cell_value is None:
                    cell_value = ""
                row_data.append(cell_value)
            markdown += (
                "| "
                + " | ".join(str(cell) if cell is not None else "" for cell in row_data)
                + " |\n"
            )
        return markdown

    def _process_sheet(self, sheet: Worksheet, sheet_name: str) -> ExcelSheet:
        """
        Process a single worksheet to extract tables and create an ExcelSheet object.

        Args:
            sheet (Worksheet): The openpyxl worksheet object.
            sheet_name (str): The name of the worksheet.

        Returns:
            ExcelSheet: An ExcelSheet object containing the name and extracted tables.
        """
        tables = self._extract_tables(sheet)
        if not tables:
            logger.warning(f"No valid tables found in sheet '{sheet_name}'.")
            return ExcelSheet(name=sheet_name, tables=[])
        for table in tables:
            header_rows = (
                self._find_multi_row_header(
                    sheet,
                    table.top_left[0],
                    table.bottom_right[0],
                    table.top_left[1],
                    table.bottom_right[1],
                )
                or 1
            )
            table.header_rows = header_rows - table.top_left[0] + 1
        return ExcelSheet(name=sheet_name, tables=tables)

    def _extract_tables(self, worksheet: Worksheet, min_cells=2) -> list[ExcelTable]:
        """
        Detects subtables in an openpyxl worksheet, filtering out invalid ones,
        considering cell content, fill, and borders, but without merging.
        This updated version skips rows and columns that are entirely empty
        (no value, fill, or border) and matches cells with the same border color.

        This function iterates through all cells to find contiguous blocks of
        non-empty cells (containing a value, a color fill, or a border). It returns
        the coordinates of each distinct subtable that meets the minimum size requirement.

        Args:
            worksheet: An openpyxl worksheet object.
            min_cells (int): The minimum number of cells a block must have to be considered a valid table. Defaults to 2.

        Returns:
            A list of tuples, where each tuple contains the coordinates of a
            subtable in the format ((top_left_row, top_left_col), (bottom_right_row, bottom_right_col)).
            For example: [((1, 1), (5, 3)), ((2, 5), (8, 6))].
        """
        visited_cells = set()
        tables: list[ExcelTable] = []
        max_row = worksheet.max_row
        max_col = worksheet.max_column

        def has_border_with_color(cell, color=None):
            """
            Checks if a cell has any border, and optionally if its border color matches a specified color.
            """
            border = cell.border
            if border is None:
                return False

            for side_name in ["left", "right", "top", "bottom"]:
                side = getattr(border, side_name)
                # Ensure the side exists and has a style (i.e., not 'none')
                if side and side.style is not None and side.style != "none":
                    if (
                        color is None
                    ):  # If no specific color is requested, any border is fine
                        return True
                    # Check if the border color matches the requested color
                    if side.color and side.color.rgb == color:
                        return True
            return False

        # Find active rows and columns using the dedicated method
        final_active_rows, final_active_cols = self._find_active_rows_and_cols(
            worksheet
        )

        # Find subtables using Breadth-First Search (BFS) on the refined active cells
        for row in sorted(
            list(final_active_rows)
        ):  # Iterate through active rows in order
            for col in sorted(
                list(final_active_cols)
            ):  # Iterate through active columns in order
                cell_coord = (row, col)
                cell = worksheet.cell(row=row, column=col)

                is_filled = (
                    cell.fill.fill_type is not None and cell.fill.fill_type != "none"
                )
                has_any_border = has_border_with_color(cell)

                # Start a new BFS if the cell has content/fill/border and hasn't been visited
                if (
                    cell.value is not None or is_filled or has_any_border
                ) and cell_coord not in visited_cells:
                    queue = [cell_coord]
                    current_table_cells = [cell_coord]
                    visited_cells.add(cell_coord)
                    min_r, max_r = row, row
                    min_c, max_c = col, col

                    # Determine the reference border color for the current subtable
                    # This ensures that all cells in this subtable (if they have borders) match this color.
                    start_cell_border_color = None
                    if cell.border:
                        for side_name in ["left", "right", "top", "bottom"]:
                            side = getattr(cell.border, side_name)
                            if (
                                side
                                and side.style is not None
                                and side.style != "none"
                                and side.color
                            ):
                                start_cell_border_color = side.color.rgb
                                break  # Take the first valid border color found

                    while queue:
                        current_r, current_c = queue.pop(0)

                        # Check all 8 neighbors (including diagonals)
                        for dr in [-1, 0, 1]:
                            for dc in [-1, 0, 1]:
                                if dr == 0 and dc == 0:
                                    continue

                                nr, nc = current_r + dr, current_c + dc
                                neighbor_coord = (nr, nc)

                                # Ensure neighbor is within overall sheet bounds AND is in the final set of active rows/columns
                                if (
                                    1 <= nr <= max_row
                                    and 1 <= nc <= max_col
                                    and nr in final_active_rows
                                    and nc in final_active_cols
                                    and neighbor_coord not in visited_cells
                                ):
                                    neighbor_cell = worksheet.cell(row=nr, column=nc)
                                    neighbor_is_filled = (
                                        neighbor_cell.fill.fill_type is not None
                                        and neighbor_cell.fill.fill_type != "none"
                                    )

                                    # A neighbor is considered part of the current table if it has:
                                    # 1. A value OR
                                    # 2. A fill color OR
                                    # 3. A border that matches the 'start_cell_border_color' (if a color was set)
                                    neighbor_has_content = (
                                        neighbor_cell.value is not None
                                        or neighbor_is_filled
                                        or has_border_with_color(
                                            neighbor_cell, start_cell_border_color
                                        )
                                    )

                                    if neighbor_has_content:
                                        visited_cells.add(neighbor_coord)
                                        queue.append(neighbor_coord)
                                        current_table_cells.append(neighbor_coord)
                                        min_r = min(min_r, nr)
                                        max_r = max(max_r, nr)
                                        min_c = min(min_c, nc)
                                        max_c = max(max_c, nc)

                    # If the discovered block meets the minimum size, add it to the tables list
                    if len(current_table_cells) >= min_cells:
                        top_left = (min_r, min_c)
                        bottom_right = (max_r, max_c)
                        tables.append(
                            ExcelTable(
                                top_left=top_left,
                                bottom_right=bottom_right,
                                header_rows=0,
                            )
                        )
        return tables

    def _find_active_rows_and_cols(
        self, worksheet: Worksheet
    ) -> tuple[set[int], set[int]]:
        """
        Find the active (non-empty) rows and columns in a worksheet.

        This method identifies rows and columns that contain at least one cell with content,
        then iteratively removes entirely empty rows and columns from the outside in.

        Args:
            worksheet: An openpyxl worksheet object.

        Returns:
            A tuple containing (active_rows_set, active_cols_set) where each set contains
            the row/column indices that have content.
        """
        max_row = worksheet.max_row
        max_col = worksheet.max_column

        def has_border_with_color(cell, color=None):
            """
            Checks if a cell has any border, and optionally if its border color matches a specified color.
            """
            border = cell.border
            if border is None:
                return False

            for side_name in ["left", "right", "top", "bottom"]:
                side = getattr(border, side_name)
                # Ensure the side exists and has a style (i.e., not 'none')
                if side and side.style is not None and side.style != "none":
                    if (
                        color is None
                    ):  # If no specific color is requested, any border is fine
                        return True
                    # Check if the border color matches the requested color
                    if side.color and side.color.rgb == color:
                        return True
            return False

        # Step 1: Determine initially non-empty rows and columns
        # These are rows/columns that contain at least one cell with a value, fill, or any border.
        initially_non_empty_rows = set[int]()
        initially_non_empty_cols = set[int]()
        for r_idx in range(1, max_row + 1):
            for c_idx in range(1, max_col + 1):
                cell = worksheet.cell(row=r_idx, column=c_idx)
                is_filled = (
                    cell.fill.fill_type is not None and cell.fill.fill_type != "none"
                )
                has_any_border = has_border_with_color(cell)

                if cell.value is not None or is_filled or has_any_border:
                    initially_non_empty_rows.add(r_idx)
                    initially_non_empty_cols.add(c_idx)

        # Step 2: Iteratively remove empty rows and columns from the outside in
        # This process converges when no more entirely empty rows or columns (within the active set) are found.
        removed_something = True
        active_rows = sorted(list(initially_non_empty_rows))
        active_cols = sorted(list(initially_non_empty_cols))

        while removed_something:
            removed_something = False

            # Check and refine active rows
            new_active_rows: list[int] = []
            for r_idx in active_rows:
                row_has_content = False
                # A row is considered to have content if any cell within its intersection with active_cols has content
                for c_idx in active_cols:
                    cell = worksheet.cell(row=r_idx, column=c_idx)
                    is_filled = (
                        cell.fill.fill_type is not None
                        and cell.fill.fill_type != "none"
                    )
                    has_any_border = has_border_with_color(cell)
                    if cell.value is not None:
                        row_has_content = True
                        break
                if row_has_content:
                    new_active_rows.append(r_idx)
                else:
                    removed_something = True  # Mark that a row was removed
            active_rows = new_active_rows

            # Check and refine active columns
            new_active_cols: list[int] = []
            for c_idx in active_cols:
                col_has_content = False
                # A column is considered to have content if any cell within its intersection with active_rows has content
                for (
                    r_idx
                ) in active_rows:  # Use the potentially newly refined active_rows
                    cell = worksheet.cell(row=r_idx, column=c_idx)
                    is_filled = (
                        cell.fill.fill_type is not None
                        and cell.fill.fill_type != "none"
                    )
                    has_any_border = has_border_with_color(cell)
                    if cell.value is not None or is_filled or has_any_border:
                        col_has_content = True
                        break
                if col_has_content:
                    new_active_cols.append(c_idx)
                else:
                    removed_something = True  # Mark that a column was removed
            active_cols = new_active_cols

        # Convert the final active lists to sets for efficient lookup during BFS
        final_active_rows = set(active_rows)
        final_active_cols = set(active_cols)

        return final_active_rows, final_active_cols

    def _score_header_row(
        self, ws: Worksheet, row_index: int, start_col: int, end_col: int
    ) -> int:
        """
        Assigns a score to a row based on header characteristics,
        including a check for merged cells and frozen rows.
        Empty rows will return a score of 0.
        """
        score = 0
        header_keywords = [
            "id",
            "name",
            "date",
            "category",
            "type",
            "status",
            "code",
            "page",
        ]

        # Check if the row is empty (no content in any cell within the range)
        is_row_empty = True
        for col_index in range(start_col, end_col + 1):
            cell = ws.cell(row=row_index, column=col_index)
            if cell.value is not None and str(cell.value).strip() != "":
                is_row_empty = False
                break

        if is_row_empty:
            return 0  # Simply return 0 for empty rows, do not score them

        # Strongest indicator: Row is part of the frozen pane
        # ySplit indicates the row *below* the frozen pane
        if (
            ws.views.sheetView
            and ws.views.sheetView[0].pane
            and ws.views.sheetView[0].pane.ySplit is not None
        ):
            if row_index <= ws.views.sheetView[0].pane.ySplit:
                score += 10  # High score for frozen rows

        for col_index in range(start_col, end_col + 1):
            cell = ws.cell(row=row_index, column=col_index)

            is_in_merge = False
            for merged_range in ws.merged_cells.ranges:
                # Check if any part of the cell's coordinate is within a merged range
                # A cell's coordinate is a string like "A1", "B2"
                if cell.coordinate in merged_range:
                    is_in_merge = True
                    break

            if (
                cell.value is not None or is_in_merge
            ):  # Only score if there's content or it's part of a merge
                # This is a very strong indicator of a header
                if is_in_merge:
                    score += 3

                # Strong indicator: Bold formatting
                if cell.font.bold:
                    score += 2

                # Good indicator: Cell has a background fill
                # Check if start_color exists and is not the default '00000000' (no fill)
                if (
                    cell.fill
                    and cell.fill.start_color
                    and cell.fill.start_color.index != "00000000"
                ):
                    score += 1

                # Good indicator: Value is a string
                if isinstance(cell.value, str):
                    score += 1
                    # Strong indicator: Matches a common header keyword
                    if cell.value.strip().lower() in header_keywords:
                        score += 3
                    # Penalize cells that has many words
                    if len(cell.value.strip().split(" ")) >= 5:
                        score -= 3
        return score

    def _find_multi_row_header(
        self, ws: Worksheet, start_row: int, end_row: int, start_col: int, end_col: int
    ):
        """
        Identifies a multi-row header block within a subtable's boundaries.
        The header starts at the 'start_row' and extends to the row with the best score
        within the scanned depth, provided that row has a score above a threshold.
        Empty rows are scored as 0 and are not considered for the 'best_row' or within the header range.
        """
        row_scores: dict[int, int] = {}
        # Only scan the first few rows of a subtable for a header
        # Ensure scan_depth does not exceed end_row + 1
        scan_depth = min(start_row + 8, end_row + 1)

        # Score all rows within the scan depth
        for i in range(start_row, scan_depth):
            row_scores[i] = self._score_header_row(ws, i, start_col, end_col)

        logger.debug(
            f"Row scores for header detection in sheet '{ws.title}': {row_scores}"
        )

        if not row_scores:
            return None

        # Filter out rows with a score of 0 (empty rows) to find the best scored non-empty row
        non_empty_row_scores: dict[int, int] = {
            row: score for row, score in row_scores.items() if score > 0
        }

        if not non_empty_row_scores:
            return None  # No non-empty rows with a positive score found

        best_row: int = max(non_empty_row_scores, key=non_empty_row_scores.get)  # pyright: ignore
        max_score = non_empty_row_scores[best_row]

        if max_score < 3:
            return None

        steepest_decline = 0  # Initialize with 0 or a very large positive number
        steepest_decline_row = -1

        # Find the last row that has a significant change in score compare to the next row
        for row in row_scores:
            if row in non_empty_row_scores and row < scan_depth - 1:
                if row_scores[row] - row_scores[row + 1] > steepest_decline:
                    steepest_decline = row_scores[row] - row_scores[row + 1]
                    steepest_decline_row = row

        return max(best_row, steepest_decline_row)

    # flowchart processing
    def flowchart_create_info(self, uuid_obj: uuid.UUID) -> Optional[List]:
        images_dir = flowchart_pipeline(
            xlsx_path=self.file_path,
            output_images_dir=Path(os.path.join(self.output_images_dir, str(uuid_obj))),
            output_tmp_dir=Path(os.path.join(self.output_tmp_dir, str(uuid_obj))),
        )
        if images_dir is None:
            return None

        if isinstance(images_dir, Path):
            flowchart_info = []
            for file in os.listdir(images_dir):
                # init data info
                sheet_name = file.split(".")[0].strip()
                # uuid_obj = create_uuid()
                minio_object_path = f"{settings.temp_dir}/xlsx_loader/{uuid_obj}/{file}"
                # upload images
                minio_client.upload_file(
                    bucket_name=settings.minio_bucket,
                    object_name=minio_object_path,
                    content_type="xlsx",
                )

                presigned_url = minio_client.get_presigned_url(
                    bucket_name=settings.minio_bucket, object_name=minio_object_path
                )

                flowchart_info.append(
                    {
                        "sheet_name": sheet_name,
                        "presigned_url": presigned_url,
                        "minio_object_path": minio_object_path,
                    }
                )

            return flowchart_info
        return None

    def flowchart_loader(self) -> Optional[List]:
        uuid_obj = uuid.uuid4()
        data = self.flowchart_create_info(uuid_obj)
        if data is None:
            return None

        if isinstance(data, List):
            documents = []
            for sheet_info in data:
                content = self.agent.extract(sheet_info["presigned_url"])
                documents.append(
                    Document(
                        page_content=f"##{sheet_info['sheet_name']} content:\n{content}",
                        metadata={
                            "sheet_name": sheet_info["sheet_name"],
                            "splitter": False,
                        },
                    )
                )
                minio_client.delete_file(
                    settings.minio_bucket, object_name=sheet_info["minio_object_path"]
                )
            shutil.rmtree(Path(os.path.join(self.output_images_dir, str(uuid_obj))))
            logger.info(f"Remove output images dir : {self.output_images_dir}")
            shutil.rmtree(Path(os.path.join(self.output_tmp_dir, str(uuid_obj))))
            logger.info(f"Remove output tmp file : {self.output_tmp_dir}")
            return documents
        else:
            return None


def _unmerge_cells(sheet: Worksheet):
    merged_ranges_to_process = list(sheet.merged_cells.ranges)

    print(f"Processing sheet: {sheet.title}")
    print(f"Found {len(merged_ranges_to_process)} merged ranges.")

    for merged_range in merged_ranges_to_process:
        # Get the top-left cell of the merged range, which holds the value and primary formatting
        top_left_cell_coords = merged_range.coord.split(":")[0]
        top_left_cell = sheet[top_left_cell_coords]
        cell_value = top_left_cell.value
        cell_font = Font(
            name=top_left_cell.font.name,
            size=top_left_cell.font.size,
            bold=top_left_cell.font.bold,
            italic=top_left_cell.font.italic,
            underline=top_left_cell.font.underline,
            strike=top_left_cell.font.strike,
            color=top_left_cell.font.color,
        )
        cell_fill = PatternFill(
            fill_type=top_left_cell.fill.fill_type,
            fgColor=top_left_cell.fill.fgColor,
            bgColor=top_left_cell.fill.bgColor,
        )
        cell_alignment = Alignment(
            horizontal=top_left_cell.alignment.horizontal,
            vertical=top_left_cell.alignment.vertical,
            wrap_text=top_left_cell.alignment.wrap_text,
            shrink_to_fit=top_left_cell.alignment.shrink_to_fit,
            indent=top_left_cell.alignment.indent,
            text_rotation=top_left_cell.alignment.text_rotation,
        )
        # Border needs to be copied side by side
        cell_border = Border(
            left=Side(
                style=top_left_cell.border.left.style,
                color=top_left_cell.border.left.color,
            )
            if top_left_cell.border.left
            else None,
            right=Side(
                style=top_left_cell.border.right.style,
                color=top_left_cell.border.right.color,
            )
            if top_left_cell.border.right
            else None,
            top=Side(
                style=top_left_cell.border.top.style,
                color=top_left_cell.border.top.color,
            )
            if top_left_cell.border.top
            else None,
            bottom=Side(
                style=top_left_cell.border.bottom.style,
                color=top_left_cell.border.bottom.color,
            )
            if top_left_cell.border.bottom
            else None,
        )
        cell_number_format = top_left_cell.number_format
        # Unmerge the cells
        sheet.unmerge_cells(merged_range.coord)

        # Iterate through all cells in the original merged range and apply value and formatting
        min_col, min_row, max_col, max_row = (
            merged_range.min_col,
            merged_range.min_row,
            merged_range.max_col,
            merged_range.max_row,
        )

        for row in range(min_row, max_row + 1):
            for col in range(min_col, max_col + 1):
                cell = sheet.cell(row=row, column=col)
                cell.value = cell_value  # pyright: ignore
                cell.font = cell_font
                cell.fill = cell_fill
                cell.alignment = cell_alignment
                cell.border = cell_border
                cell.number_format = cell_number_format


##load flowchart , shape, connector in sheet
### split sheet to new xlsx file


def split_sheet_to_file(filename: Path, output_dir: Path):
    """
    Split each worksheet in an Excel file into a separate .xlsx file.

    Parameters:
    - filename (Path): Path to the source Excel file.
    - output_dir (Path): Directory where each individual sheet will be saved as a separate .xlsx file.

    The function:
    - Opens the given Excel file using Spire.XLS (via Workbook).
    - Iterates over all worksheets in the workbook.
    - For each worksheet:
        - Creates a new workbook with just that one worksheet.
        - Saves it as an individual `.xlsx` file in the output directory.
    - Logs any exception that occurs during the process.
    """
    try:
        # Ensure the output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Load the original Excel file into a Workbook object
        workbook = Workbook()
        workbook.LoadFromFile(str(filename))

        # Iterate through each worksheet in the original workbook
        for worksheet in workbook.Worksheets:
            # Create a new workbook and copy the current worksheet into it
            newWorkbook = Workbook()
            newWorkbook.Worksheets.Clear()  # Remove default sheet
            newWorkbook.Worksheets.AddCopy(worksheet)  # Copy the current sheet

            # Construct output path and save the new workbook
            output_path = output_dir / f"{worksheet.Name}.xlsx"
            newWorkbook.SaveToFile(
                str(output_path), FileFormat.Version2016
            )  # Save as Excel 2016 format

        # Clean up and release resources
        workbook.Dispose()
    except Exception as e:
        logger.error(f"Error processing flowchart in file : {filename} : {e}")


def remove_sheet_by_name(
    xlsx_path: Path, target_sheet_name: str = "Evaluation Warning"
) -> None:
    """
    Remove a worksheet by name from an XLSX file (without using Excel/Office libraries).

    This function unzips the .xlsx file (since XLSX is a ZIP archive),
    removes the sheet definition from:
      - workbook.xml (sheet listing)
      - workbook.xml.rels (sheet relationship)
      - deletes the corresponding sheet XML file
    Then, it re-zips the contents and overwrites the original file.

    Parameters:
    - xlsx_path (Path): Path to the original Excel file.
    - target_sheet_name (str): Name of the sheet to be removed.
    """

    tmp_dir = Path(tempfile.mkdtemp())

    with zipfile.ZipFile(xlsx_path, "r") as zip_ref:
        zip_ref.extractall(tmp_dir)

    xl_path = tmp_dir / "xl"
    workbook_path = xl_path / "workbook.xml"
    rels_path = xl_path / "_rels" / "workbook.xml.rels"

    # Load workbook.xml
    ET.register_namespace(
        "", "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    )
    tree = ET.parse(workbook_path)
    root = tree.getroot()
    ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    sheets_elem = root.find("main:sheets", ns)

    # Find and remove the target sheet
    sheet_to_remove = None
    for sheet in sheets_elem.findall("main:sheet", ns):  # type: ignore
        if sheet.attrib.get("name") == target_sheet_name:
            sheet_to_remove = sheet
            break
    if sheet_to_remove is None:
        shutil.rmtree(tmp_dir)
        return

    r_id = sheet_to_remove.attrib[
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    ]
    sheets_elem.remove(sheet_to_remove)  # type: ignore

    # Save modified workbook.xml
    tree.write(workbook_path, encoding="utf-8", xml_declaration=True)

    # Remove from workbook.xml.rels
    rel_tree = ET.parse(rels_path)
    rel_root = rel_tree.getroot()
    rel_ns = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}

    target_rel = None
    for rel in rel_root.findall("r:Relationship", rel_ns):
        if rel.attrib["Id"] == r_id:
            target_rel = rel
            break

    if target_rel is not None:
        target_file = target_rel.attrib["Target"].replace("worksheets/", "")
        rel_root.remove(target_rel)
        rel_tree.write(rels_path, encoding="utf-8", xml_declaration=True)

        # Delete the actual sheet file
        sheet_file_path = xl_path / "worksheets" / target_file
        if sheet_file_path.exists():
            sheet_file_path.unlink()

    # Re-zip the folder and OVERWRITE the original xlsx file
    tmp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    tmp_zip_path = Path(tmp_zip.name)
    tmp_zip.close()

    with zipfile.ZipFile(tmp_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root_dir, _, files in os.walk(tmp_dir):
            for file in files:
                full_path = Path(root_dir) / file
                relative_path = full_path.relative_to(tmp_dir)
                zipf.write(full_path, arcname=str(relative_path))

    shutil.move(str(tmp_zip_path), str(xlsx_path))  # Overwrite original file
    shutil.rmtree(tmp_dir)


def crop_whitespace(
    image_path: Path,
    bg_color: tuple = (255, 255, 255),
    padding: int = 20,
    footer_ratio: Optional[int | float] = 0.08,
) -> None:
    """
    Crop whitespace around the content of an image while preserving some padding.
    Optionally removes the bottom 'footer' portion of the image, often added by tools like LibreOffice.

    Parameters:
    - image_path (Path): Path to the input image file (will be overwritten).
    - bg_color (tuple): RGB color to treat as the background (default: white).
    - padding (int): Extra pixels to retain around the detected content.
    - footer_ratio (float | int): Fraction of image height to treat as footer and cut off before cropping.
    """

    img = Image.open(image_path).convert("RGB")
    width, height = img.size

    footer_cutoff = int(height * (1 - footer_ratio))  # type: ignore
    img = img.crop((0, 0, width, footer_cutoff))

    bg = Image.new("RGB", img.size, bg_color)
    diff = ImageChops.difference(img, bg)
    bbox = diff.getbbox()

    if bbox:
        left, top, right, bottom = bbox

        left = max(0, left - padding)
        top = max(0, top - padding)
        right = min(width, right + padding)
        bottom = min(footer_cutoff, bottom + padding)

        cropped = img.crop((left, top, right, bottom))
        cropped.save(image_path)


def convert_sheet_to_image(
    xlsx_path: Path, output_images_dir: Path, width=1920, height=1080
):
    """
    Converts a single-sheet XLSX file into a PNG image.
    The XLSX is first converted to a PDF using LibreOffice in headless mode,
    then each page of the PDF is converted to a PNG using pdftoppm,
    and whitespace around the content is cropped from the image.

    Parameters:
    - xlsx_path (Path): Path to the XLSX file (should contain one sheet).
    - output_images_dir (Path): Directory to save the resulting PNG images.
    - width (int): (Unused in current logic) Intended width of output image.
    - height (int): (Unused in current logic) Intended height of output image.
    """

    os.makedirs(output_images_dir, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Convert XLSX → PDF using LibreOffice
            subprocess.run(
                [
                    "libreoffice",
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(tmpdir),
                    str(xlsx_path),
                ],
                check=True,
            )

            # Get the converted PDF path
            pdf_path = next(tmpdir.glob("*.pdf"))

            # Convert PDF → PNG using pdftoppm (will generate filename-1.png)
            subprocess.run(
                [
                    "pdftoppm",
                    "-png",
                    "-r",
                    "200",
                    str(pdf_path),
                    str(output_images_dir / pdf_path.stem),
                ],
                check=True,
            )

            # Remove PDF after conversion
            pdf_path.unlink()

            # Find generated image(s)
            image_files = sorted(output_images_dir.glob(f"{pdf_path.stem}-*.png"))

            if not image_files:
                raise FileNotFoundError("No image files were generated from PDF")

            # Crop whitespace for all generated images (optional)
            for img_path in image_files:
                crop_whitespace(img_path)

            # Rename first image to original XLSX name
            first_img = image_files[0]
            new_img_path = output_images_dir / f"{xlsx_path.stem}.png"
            first_img.rename(new_img_path)

            # Remove other images if more than one was generated
            for extra_img in image_files[1:]:
                extra_img.unlink()

            logger.info(f"Converted and saved image: {new_img_path}")

    except Exception as e:
        logger.error(f"Error processing flowchart in file {xlsx_path} : {e}")


def get_sheet_xml_path(zf: ZipFile, sheet_name: str) -> Optional[str]:
    # Find the sheet's internal ID from workbook.xml
    with zf.open("xl/workbook.xml") as f:
        tree = ET.parse(f)
        root = tree.getroot()
        # Namespace for workbook.xml
        ns = {
            "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
            "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        }

        # sheet_id = None
        for sheet_elem in root.findall(".//main:sheet", ns):
            if sheet_elem.get("name") == sheet_name:
                # The r:id attribute holds the relationship ID, which maps to sheetN.xml
                r_id = sheet_elem.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                )

                # Find the target for this r:id in xl/_rels/workbook.xml.rels
                with zf.open("xl/_rels/workbook.xml.rels") as rels_f:
                    rels_tree = ET.parse(rels_f)
                    rels_root = rels_tree.getroot()
                    rels_ns = {
                        "r": "http://schemas.openxmlformats.org/package/2006/relationships"
                    }
                    for relationship in rels_root.findall(".//r:Relationship", rels_ns):
                        if relationship.get("Id") == r_id:
                            # The Target attribute contains the path to the sheet XML file
                            sheet_xml_path = "xl/" + relationship.get("Target")
                            return sheet_xml_path
                break


def detect_generic_shapes_xml(filepath: Path) -> List:
    """
    Detects generic shapes (rectangles, ovals, text boxes, etc.) in an XLSX file
    by directly parsing its underlying XML. This is more involved than using
    openpyxl's high-level API.
    Returns a dictionary where keys are sheet names and values are the count
    of drawings found on that sheet.
    """

    NAMESPACES = {
        "rels": "http://schemas.openxmlformats.org/package/2006/relationships",
        "xdr": "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing",
        "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    }
    sheet_drawing_counts = {}

    try:
        with zipfile.ZipFile(filepath, "r") as z:
            # First, get sheet names and their rIds to drawing parts using openpyxl
            # This helps map drawing IDs back to sheet names
            workbook = load_workbook(filepath, read_only=False)

            sheet_drawing_rels = {}
            for sheet_name in workbook.sheetnames:
                # Use the helper function to get the sheet's XML path
                sheet_path = get_sheet_xml_path(z, sheet_name)

                if sheet_path:
                    # Construct the relationships file path for the current sheet
                    # e.g., xl/worksheets/_rels/sheet1.xml.rels
                    # The sheet_path is something like 'xl/worksheets/sheet1.xml'
                    sheet_rel_dir = "/".join(sheet_path.split("/")[:-1]) + "/_rels"
                    sheet_xml_filename = sheet_path.split("/")[-1]  # e.g., sheet1.xml
                    sheet_rel_path = f"{sheet_rel_dir}/{sheet_xml_filename}.rels"

                    if sheet_rel_path in z.namelist():
                        rels_xml_data = z.read(sheet_rel_path)
                        rels_root = ET.fromstring(rels_xml_data)
                        for rel in rels_root.findall("rels:Relationship", NAMESPACES):
                            if (
                                rel.get("Type")
                                == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing"
                            ):
                                target = rel.get(
                                    "Target"
                                )  # e.g., ../drawings/drawing1.xml
                                # The target is relative, adjust to absolute path in zip
                                drawing_part_name = f"xl/{target.replace('../', '')}"  # xl/drawings/drawing1.xml
                                sheet_drawing_rels[sheet_name] = drawing_part_name
                                break  # Assume one drawing part per sheet for simplicity

            # Now, iterate through the found drawing parts and count shapes
            for sheet_name, drawing_xml_path in sheet_drawing_rels.items():
                shapes_count = 0
                if drawing_xml_path in z.namelist():
                    drawing_xml_data = z.read(drawing_xml_path)
                    drawing_root = ET.fromstring(drawing_xml_data)

                    # Count generic shape elements <xdr:sp>
                    shapes_count = len(drawing_root.findall(".//xdr:sp", NAMESPACES))

                sheet_drawing_counts[sheet_name] = shapes_count

    except zipfile.BadZipFile:
        logger.info(f"Error: '{filepath}' is not a valid XLSX file (bad zip).")
    except FileNotFoundError:
        logger.info(f"Error: File not found at '{filepath}'.")
    except Exception as e:
        logger.info(f"An unexpected error occurred: {e}")
    sheet_name_with_shape = []
    for sheet, info in sheet_drawing_counts.items():
        if info > 0:
            sheet_name_with_shape.append(sheet)
    return sheet_name_with_shape


def flowchart_pipeline(
    xlsx_path: Path,
    output_images_dir: Path,
    output_tmp_dir: Path,
) -> Optional[Path]:
    """
    Full pipeline to extract and convert flowchart-containing sheets from an XLSX file
    into cropped PNG images.

    Steps:
    1. Split each sheet of the input XLSX into individual XLSX files.
    2. Identify sheets that contain shapes, connectors, or images.
    3. For each identified sheet:
       - Remove any unwanted warning sheets.
       - Convert the sheet to a PDF using LibreOffice, then to PNG(s) using pdftoppm.
       - Crop whitespace from the image(s).
    4. Clean up temporary files.

    Parameters:
    - xlsx_path (Path): Path to the original Excel file.
    - output_images_dir (Path): Folder to store final PNG image(s).
    - output_tmp_dir (Path): Temporary folder to hold intermediate XLSX files.

    Returns:
    - Path to output_images_dir if successful.
    - None if an error occurs.
    - None if no drawing sheets found.
    """

    # create folder if path not exist
    os.makedirs(output_images_dir, exist_ok=True)
    os.makedirs(output_tmp_dir, exist_ok=True)
    try:
        split_sheet_to_file(filename=xlsx_path, output_dir=output_tmp_dir)
        drawing_sheet = detect_generic_shapes_xml(filepath=xlsx_path)

        for sheet_name in drawing_sheet:
            file_path = output_tmp_dir / f"{sheet_name.strip()}.xlsx"
            remove_sheet_by_name(file_path)
            convert_sheet_to_image(file_path, output_images_dir)
        return output_images_dir
    except Exception as e:
        logger.error(f"Flowchart pipeline failed: {e}")
        return None

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def convert_to_xlsx(file_path: Path) -> Path:
    import pandas as pd

    """
        Converts an .xls file to .xlsx if necessary and returns the .xlsx path.
        Replaces 'Unnamed: x' column headers with empty strings.
        :param file_path: Path to the original file.
        :return: Path to the converted .xlsx file.
        """
    if file_path.suffix == ".xls":
        xlsx_path = file_path.with_suffix(
            ".xlsx"
        )  # Append 'x' to create .xlsx filename
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

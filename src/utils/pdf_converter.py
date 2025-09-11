"""
Convert Office files to PDF using LibreOffice.
"""

import subprocess
from typing import Optional


def convert_to_pdf(input_file: str, output_dir: str) -> Optional[str]:
    """
    Convert an Office file to PDF using LibreOffice.

    Args:
        input_file (str): Path to the input Office file.
        output_file (str): Path to the output PDF file.
    """
    try:
        subprocess.run(
            [
                "libreoffice",
                "--headless",
                "--convert-to",
                'pdf:calc_pdf_Export:{"SinglePageSheets":{"type":"boolean","value":"true"}}',
                input_file,
                "--outdir",
                output_dir,
            ],
            check=True,
        )
        pdf_file_path = f"{output_dir}/{input_file.rsplit('/', 1)[1].split('.')[0]}.pdf"
        return pdf_file_path

    except subprocess.CalledProcessError as e:
        # Handle the error if the conversion fails
        raise RuntimeError(f"Failed to convert {input_file} to PDF: {e}")

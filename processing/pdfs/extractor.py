import io
from enum import Enum, auto
from typing import cast

import magic
import pdfplumber  # pip install pdfplumber
import pymupdf  # PyMuPDF
import pytesseract  # pip install pytesseract
from PIL import Image


class PDFType(Enum):
    EMPTY = auto()
    SCANNED = auto()
    DIGITAL = auto()


type Block = tuple[float, float, float, float, str, int, int]
type PageText = list[tuple[int, str]]


class PDFExtractor:
    # Route to correct extractor
    def extract_pdf(self, pdf_path: str) -> PageText:
        pdf_type = self._detect_pdf_type(pdf_path)
        print(f"  → Detected type: {pdf_type}")

        if pdf_type == PDFType.DIGITAL:
            return self._extract_digital_pdf(pdf_path)
        elif pdf_type == PDFType.SCANNED:
            return self._extract_scanned_pdf(pdf_path)
        else:
            print(f"  ⚠️ Skipping empty PDF: {pdf_path}")
            return []

    def _detect_pdf_type(self, pdf_path: str) -> str:
        if not self._is_pdf(pdf_path):
            raise TypeError("wrong file type uploaded!")
        try:
            with pymupdf.open(pdf_path) as doc:
                if doc.page_count == 0:
                    return PDFType.EMPTY.name

                text = cast(str, doc[0].get_text())
                if len(text.strip()) > 100:
                    return PDFType.DIGITAL.name  # Normal PDF with selectable text
                else:
                    images = doc[0].get_images()
                    if images:
                        return PDFType.SCANNED.name
                return PDFType.EMPTY.name
        except Exception as exc:
            raise RuntimeError(f"Failed to read PDF: {pdf_path}") from exc

    def _extract_digital_pdf(self, pdf_path: str) -> PageText:
        try:
            with pymupdf.open(pdf_path) as doc:
                if doc.page_count == 0:
                    return []

                pages_text: PageText = []

                for page_index in range(doc.page_count):
                    page = doc[page_index]
                    # Extract with layout preservation
                    raw = page.get_text("blocks")
                    if not isinstance(raw, list):
                        raise TypeError("Expected list from get_text('blocks')")
                    blocks = cast(list[Block], raw)
                    # order blocks by b[1] -> x[1] -> rows and b[0] -> y[0] -> cols
                    blocks.sort(key=lambda b: (b[1], b[0]))

                    page_text = "\n".join(
                        block[4].strip() for block in blocks if block[4].strip()
                    )

                    pages_text.append((page_index + 1, page_text))
                return pages_text  # [(page_num, text), ...]
        except Exception as exc:
            raise RuntimeError(f"Failed digital PDF extraction: {pdf_path}") from exc

    def _extract_scanned_pdf(self, pdf_path: str) -> PageText:
        try:
            with pymupdf.open(pdf_path) as doc:
                if doc.page_count == 0:
                    return []
                pages_text: PageText = []

                for page_index in range(doc.page_count):
                    page = doc[page_index]
                    # Render page as high-res image
                    matrix = pymupdf.Matrix(2.0, 2.0)  # 2x zoom for better OCR
                    pix = page.get_pixmap(matrix=matrix, alpha=False)
                    image = Image.open(io.BytesIO(pix.tobytes("png")))

                    # Run OCR
                    text = pytesseract.image_to_string(
                        image,
                        config="--oem 3 --psm 3",
                    ).strip()
                    pages_text.append((page_index + 1, text))

                    print(f"  OCR page {page_index + 1}/{doc.page_count}")
                return pages_text
        except Exception as exc:
            raise RuntimeError(f"Failed OCR PDF extraction: {pdf_path}") from exc

    def _extract_tables_from_pdf(self, pdf_path: str) -> list[dict]:
        tables_data = []

        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                tables = page.extract_tables()

                for table_idx, table in enumerate(tables):
                    if not table or len(table) < 2:
                        continue

                    # First row = headers
                    headers = [
                        str(h).strip() if h else f"col_{i}"
                        for i, h in enumerate(table[0])
                    ]

                    # Convert rows to natural language sentences
                    rows_as_text = []
                    for row in table[1:]:
                        if not any(cell for cell in row):
                            continue
                        row_text = ", ".join(
                            f"{headers[i]}: {str(cell).strip()}"
                            for i, cell in enumerate(row)
                            if cell and str(cell).strip()
                        )
                        rows_as_text.append(row_text)

                    # Format as readable text block
                    table_text = (
                        f"Table data with columns: "
                        f"{', '.join(headers)}.\n" + "\n".join(rows_as_text)
                    )

                    tables_data.append(
                        {
                            "text": table_text,
                            "metadata": {
                                "source_type": "pdf_table",
                                "page_number": page_num + 1,
                                "table_index": table_idx,
                                "column_count": len(headers),
                                "row_count": len(table) - 1,
                                "headers": headers,
                            },
                        }
                    )

        return tables_data

    def _is_pdf(self, file_path: str) -> bool:
        # This reads the first few bytes of the file to determine the type
        mime = magic.Magic(mime=True)
        file_type = mime.from_file(file_path)

        return True if file_type == "application/pdf" else False

import io

import fitz  # PyMuPDF
import pdfplumber  # pip install pdfplumber
import pytesseract  # pip install pytesseract
from PIL import Image


class PDFExtractor:
    def detect_pdf_type(self, pdf_path: str) -> str:
        doc = fitz.open(pdf_path)
        page = doc[0]
        text = page.get_text().strip()

        if len(text) > 100:
            return "digital"  # Normal PDF with selectable text

        # Check if it has images (likely scanned)
        images = page.get_images()
        if images:
            return "scanned"  # Image-based, needs OCR

        return "empty"  # Corrupted or blank

    # Route to correct extractor
    def extract_pdf(self, pdf_path: str) -> str:
        pdf_type = detect_pdf_type(pdf_path)
        print(f"  → Detected type: {pdf_type}")

        if pdf_type == "digital":
            return extract_digital_pdf(pdf_path)
        elif pdf_type == "scanned":
            return extract_scanned_pdf(pdf_path)
        else:
            print(f"  ⚠️ Skipping empty PDF: {pdf_path}")
            return ""

    def extract_digital_pdf(self, pdf_path: str) -> str:
        doc = fitz.open(pdf_path)
        pages_text = []

        for page_num, page in enumerate(doc):
            # Extract with layout preservation
            blocks = page.get_text("blocks")  # Returns list of text blocks

            # Sort blocks top-to-bottom, left-to-right
            blocks.sort(key=lambda b: (round(b[1] / 20), b[0]))  # b[1]=y, b[0]=x

            page_text = "\n".join(b[4].strip() for b in blocks if b[4].strip())
            pages_text.append((page_num + 1, page_text))

        return pages_text  # [(page_num, text), ...]

    def extract_scanned_pdf(self, pdf_path: str) -> list:
        doc = fitz.open(pdf_path)
        pages_text = []

        for page_num, page in enumerate(doc):
            # Render page as high-res image
            mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better OCR
            pix = page.get_pixmap(matrix=mat)
            img = Image.open(io.BytesIO(pix.tobytes("png")))

            # Run OCR
            text = pytesseract.image_to_string(
                img,
                config="--osd 0 --psm 3",  # Auto page segmentation
            )
            pages_text.append((page_num + 1, text))
            print(f"  OCR page {page_num + 1}/{len(doc)}")

        return pages_text

    def extract_tables_from_pdf(self, pdf_path: str) -> list[dict]:
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

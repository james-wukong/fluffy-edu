import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from enum import Enum, auto
from typing import cast

import magic
import pdfplumber  # pip install pdfplumber
import pymupdf  # PyMuPDF
import pytesseract  # pip install pytesseract
from PIL import Image, ImageOps


class PDFType(Enum):
    EMPTY = auto()
    SCANNED = auto()
    DIGITAL = auto()


type Block = tuple[float, float, float, float, str, int, int]
type PageText = tuple[int, str]


class PDFExtractor:
    # Route to correct extractor
    def extract_pdf(self, pdf_path: str) -> list[PageText]:
        pdf_type = self._detect_pdf_type(pdf_path)
        print(f"  → Detected type: {pdf_type}")

        if pdf_type == PDFType.DIGITAL:
            return self._extract_digital_pdf(pdf_path)
        elif pdf_type == PDFType.SCANNED:
            ocr = FastPDFOCR(
                workers=6,
                zoom=2.5,
                lang="chi_sim+eng",
                psm=3,
                batch_size=4,
            )
            return ocr.extract(pdf_path)
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

    def _extract_digital_pdf(self, pdf_path: str) -> list[PageText]:
        try:
            with pymupdf.open(pdf_path) as doc:
                if doc.page_count == 0:
                    return []

                pages_text: list[PageText] = []

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


class FastPDFOCR:
    def __init__(
        self,
        workers: int | None = None,
        zoom: float = 2.0,
        lang: str = "chi_sim+eng",
        psm: int = 3,
        batch_size: int = 4,
    ) -> None:
        self.workers = workers or max(1, (os.cpu_count() or 4) - 1)
        self.zoom = zoom
        self.lang = lang
        self.batch_size = batch_size
        self.config = f"--oem 3 --psm {psm}"

    def extract(self, pdf_path: str) -> list[PageText]:
        with pymupdf.open(pdf_path) as doc:
            total_pages = doc.page_count

        if total_pages == 0:
            return []

        page_indexes = list(range(total_pages))
        batches = self._chunked(page_indexes, self.batch_size)

        results: list[PageText] = []

        with ProcessPoolExecutor(max_workers=self.workers) as executor:
            futures = [
                executor.submit(
                    self._ocr_batch,
                    pdf_path,
                    batch,
                    self.zoom,
                    self.lang,
                    self.config,
                )
                for batch in batches
            ]

            for future in as_completed(futures):
                results.extend(future.result())

        results.sort(key=lambda item: item[0])
        return results

    def _chunked(self, seq: list[int], size: int) -> list[list[int]]:
        return [seq[i : i + size] for i in range(0, len(seq), size)]

    def _ocr_page(
        self, pdf_path: str, page_index: int, zoom: float, lang: str, config: str
    ) -> PageText:
        with pymupdf.open(pdf_path) as doc:
            page = doc[page_index]

            mat = pymupdf.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)

            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

            image = ImageOps.grayscale(image)

            text = pytesseract.image_to_string(image, lang=lang, config=config).strip()

            return page_index + 1, text

    def _ocr_batch(
        self,
        pdf_path: str,
        page_indexes: list[int],
        zoom: float,
        lang: str,
        config: str,
    ) -> list[PageText]:
        results: list[PageText] = []

        for page_index in page_indexes:
            results.append(self._ocr_page(pdf_path, page_index, zoom, lang, config))

        return results


# ocr = FastPDFOCR(
#     workers=6,
#     zoom=2.5,
#     lang="chi_sim+eng",
#     psm=3,
#     batch_size=4,
# )
# ocr.extract()

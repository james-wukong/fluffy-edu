import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from enum import Enum, auto
from pathlib import Path
from typing import cast

import magic
import polars as pl
import pymupdf
import pytesseract
from PIL import Image, ImageOps

from preprocessing.schema import (
    ExtractHelper,
    FileMetadata,
    MetaData,
    PageMetadata,
    PageResult,
)


class PDFType(Enum):
    EMPTY = auto()
    SCANNED = auto()
    DIGITAL = auto()
    MIXED = auto()


type Block = tuple[float, float, float, float, str, int, int]


class PDFExtractor:
    # Route to correct extractor
    def extract_file(self, file_path: str) -> list[PageResult]:
        if not self._is_pdf(file_path):
            raise TypeError("wrong file type uploaded!")
        is_scanned = self._is_scanned_pdf(file_path)
        try:
            with pymupdf.open(file_path) as doc:
                if doc.page_count == 0:
                    return []

                results: list[PageResult] = []
                if is_scanned:
                    # TODO OCR process
                    ocr_ext = FastPDFOCRExtractor(
                        workers=6,
                        zoom=2.5,
                        lang="chi_sim+eng",
                        psm=3,
                        batch_size=4,
                    )
                    results = ocr_ext.extract_pdf(file_path)
                else:
                    # TODO digital process
                    digital_ext = PDFDigitalExtractor()
                    results = digital_ext.extract_pdf(file_path)

                return results
        except Exception as exc:
            raise RuntimeError(f"Failed to read PDF: {file_path}") from exc

    def _is_scanned_pdf(self, file_path: str) -> bool:
        """
        only detect if this pdf contains only scanned images
        """
        try:
            with pymupdf.open(file_path) as doc:
                if doc.page_count == 0:
                    return False

                for page in doc:
                    # If any page has actual digital text, it's likely not "purely" scanned
                    text = page.get_text()
                    if not isinstance(text, list) and not isinstance(text, dict):
                        if len(cast(str, text).strip().split()) > 10:
                            return False

            # If we looped through all pages and found zero text
            return True
        except Exception as exc:
            raise RuntimeError(f"Failed to read PDF: {file_path}") from exc

    def _detect_page_type(self, page: pymupdf.Page) -> str:
        text = cast(str, page.get_text())
        text_len = len(text)

        images = page.get_images()
        image_len = len(images)

        if text_len == 0 and image_len == 0:
            return PDFType.EMPTY.name

        if text_len > 80 and image_len == 0:
            return PDFType.DIGITAL.name

        if text_len > 80 and image_len > 0:
            return PDFType.MIXED.name

        if image_len > 0:
            return PDFType.SCANNED.name

        return PDFType.DIGITAL.name

    def _is_pdf(self, file_path: str) -> bool:
        # This reads the first few bytes of the file to determine the type
        mime = magic.Magic(mime=True)
        file_type = mime.from_file(file_path)

        return True if file_type == "application/pdf" else False


class PDFDigitalExtractor:
    def extract_pdf(self, file_path: str) -> list[PageResult]:
        """
        extract text from digital pdf file, need to make sure this is a digital pdf file
        """
        results: list[PageResult] = []
        with pymupdf.open(file_path) as doc:
            for page_index in range(doc.page_count):
                page_result = self.extract_page(doc[page_index], page_index + 1)
                path_obj = Path(file_path)

                file_meta: FileMetadata = {
                    "file_path": path_obj.parent,
                    "filename": path_obj.name,
                    "total_pages": doc.page_count,
                    "file_type": "pdf",
                }
                page_result["metadata"]["file_meta"] = file_meta

                if isinstance(doc.metadata, dict) and doc.metadata:
                    page_result["metadata"]["doc_meta"] = (
                        ExtractHelper.map_pdf_metadata(doc.metadata)
                    )
                results.append(page_result)

        return results

    def extract_page(self, page: pymupdf.Page, page_index: int) -> PageResult:
        """
        extract text from page
        """
        blocks = page.get_text("blocks")
        if not isinstance(blocks, list):
            page_meta: PageMetadata = {
                "page": page_index + 1,
                "page_type": PDFType.DIGITAL.name,
            }
            return {
                "text": "",
                "metadata": {
                    "page_meta": page_meta,
                },
            }

        blocks.sort(key=lambda b: (b[1], b[0]))

        # 1. only pick non-empty text, block[6]-> 0 text, 1 image
        text = self._extract_text(blocks)

        # 2. extract tables into markdown format
        tab_text = self._extract_tables(page)

        page_meta: PageMetadata = {
            "page": page_index + 1,
            "page_type": PDFType.DIGITAL.name,
        }
        return {
            "text": text + "\n" + tab_text,
            "metadata": {"page_meta": page_meta},
        }

    def _extract_text(self, blocks: list) -> str:
        blocks.sort(key=lambda b: (b[1], b[0]))

        # 1. only pick non-empty text, block[6]-> 0 text, 1 image
        text = "\n".join(
            block[4].strip() for block in blocks if block[6] == 0 and block[4].strip()
        )

        return text

    def _extract_tables(self, page: pymupdf.Page) -> str:
        # Find tables on the page
        tabs = page.find_tables()
        if tabs is not None:
            table_text: list[str] = []
            for tab in tabs.tables:
                df = pl.from_pandas(tab.to_pandas())
                df = df.with_columns(
                    [pl.col(pl.Utf8).str.replace_all(r"\s+", " ").str.strip_chars()]
                )
                md_output = df.to_pandas().to_markdown(index=False)
                table_text.append(md_output)
        tab_text = "\n".join(table_text)

        return tab_text


class FastPDFOCRExtractor:
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

    def extract_pdf(self, file_path: str) -> list[PageResult]:
        with pymupdf.open(file_path) as doc:
            total_pages: int = doc.page_count

        if total_pages == 0:
            return []

        page_indexes = list(range(total_pages))
        batches = self._chunked(page_indexes, self.batch_size)
        results: list[PageResult] = []

        with ProcessPoolExecutor(max_workers=self.workers) as executor:
            futures = [
                executor.submit(
                    self._ocr_batch,
                    file_path,
                    batch,
                    self.zoom,
                    self.lang,
                    self.config,
                )
                for batch in batches
            ]

            for future in as_completed(futures):
                results.extend(future.result())

        results.sort(
            key=lambda item: (
                item["metadata"]["page_meta"]["page"]
                if "page_meta" in item["metadata"]
                else 0
            )
        )
        return results

    def _chunked(self, seq: list[int], size: int) -> list[list[int]]:
        return [seq[i : i + size] for i in range(0, len(seq), size)]

    def _ocr_page(
        self, file_path: str, page_index: int, zoom: float, lang: str, config: str
    ) -> PageResult:
        with pymupdf.open(file_path) as doc:
            page = doc[page_index]

            mat = pymupdf.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            image = ImageOps.grayscale(image)

            text = pytesseract.image_to_string(image, lang=lang, config=config).strip()
            metadata: MetaData = {}
            metadata["page_meta"] = {
                "page": page_index + 1,
                "page_type": PDFType.SCANNED.name,
            }
            path_obj = Path(file_path)
            file_meta: FileMetadata = {
                "file_path": path_obj.parent,
                "filename": path_obj.name,
                "total_pages": doc.page_count,
                "file_type": "pdf",
            }
            metadata["file_meta"] = file_meta
            if isinstance(doc.metadata, dict):
                metadata["doc_meta"] = ExtractHelper.map_pdf_metadata(doc.metadata)
            return {
                "text": text,
                "metadata": metadata,
            }

    def _ocr_batch(
        self,
        file_path: str,
        page_indexes: list[int],
        zoom: float,
        lang: str,
        config: str,
    ) -> list[PageResult]:
        results: list[PageResult] = []

        for page_index in page_indexes:
            results.append(self._ocr_page(file_path, page_index, zoom, lang, config))

        return results


# ocr = FastPDFOCR(
#     workers=6,
#     zoom=2.5,
#     lang="chi_sim+eng",
#     psm=3,
#     batch_size=4,
# )
# ocr.extract()
# ext = PDFExtractor()
# result = ext.extract_pdf(
#     "data/raw/pdfs/hr/epa_sample_letter_sent_to_commissioners_dated_february_29_2015.pdf"
# )

# print(result[2])

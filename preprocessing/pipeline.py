# TODO process all data processing
# processing/pipeline.py

from pathlib import Path

# from preprocessing.excels.extractor import ExcelExtractor
from preprocessing.chunker import ChunkResult, SmartChunker
from preprocessing.docs.extractor import DocxExtractor
from preprocessing.pdfs.cleaner import TextCleaner
from preprocessing.pdfs.extractor import PDFExtractor


class DocumentPipeline:
    def __init__(self):
        self.pdf_ext = PDFExtractor()
        self.doc_ext = DocxExtractor()
        # self.excel_ext = ExcelExtractor()
        self.pdf_cleaner = TextCleaner()
        self.chunker = SmartChunker(chunk_size=1024, overlap=128)

    def process(self, file_path: str) -> list[ChunkResult]:
        suffix = Path(file_path).suffix.lower()

        # 1. Extract → list[PageResult]
        if suffix == ".pdf":
            pages = self.pdf_ext.extract_file(file_path)
        elif suffix in (".docx", ".doc"):
            pages = self.doc_ext.extract_file(file_path)
        # elif suffix in (".xlsx", ".xls", ".csv"):
        #     pages = self.excel_ext.extract_excel(file_path)
        else:
            raise TypeError(f"Unsupported file type: {suffix}")

        # 2. Chunk + validate each page
        all_chunks: list[ChunkResult] = []
        for page in pages:
            page["text"] = self.pdf_cleaner.clean(page["text"])
            chunks = self.chunker.chunk(page)
            valid = [c for c in chunks if self.chunker.validate_chunk(c)[0]]
            # if Path(file_path).name == "james_cheng_resume_php.docx":
            #     print(f"  → valid chunk: {valid}")
            all_chunks.extend(valid)

        return all_chunks

    def process_directory(self, dir_path: str) -> list[ChunkResult]:
        """Process all supported files in a directory recursively"""
        supported = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv"}
        all_chunks: list[ChunkResult] = []

        for file in Path(dir_path).rglob("*"):
            if file.suffix.lower() not in supported:
                continue
            try:
                print(f"  Processing: {file.name}")
                chunks = self.process(str(file))
                all_chunks.extend(chunks)
                print(f"  → {len(chunks)} chunks")
            except Exception as e:
                print(f"  ❌ Failed: {file.name} — {e}")

        return all_chunks


if __name__ == "__main__":
    pipeline = DocumentPipeline()
    chunks = pipeline.process_directory("data/raw/")
    print(f"\n✅ Total chunks: {len(chunks)}")

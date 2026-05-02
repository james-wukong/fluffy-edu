# TODO process all data processing
# processing/pipeline.py
import json
import os
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path

# from preprocessing.excels.extractor import ExcelExtractor
from preprocessing.chunker import ChunkResult, SmartChunker
from preprocessing.docs.extractor import DocxExtractor
from preprocessing.pdfs.cleaner import TextCleaner
from preprocessing.pdfs.extractor import PDFExtractor


class PipelineEncoder(json.JSONEncoder):
    """Custom JSON encoder for PDF processing pipeline objects."""

    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Path):
            return str(obj)
        return super().default(obj)


class DocumentPipeline:
    def __init__(self):
        self.pdf_ext = PDFExtractor()
        self.doc_ext = DocxExtractor()
        # self.excel_ext = ExcelExtractor()
        self.pdf_cleaner = TextCleaner()
        self.chunker = SmartChunker(chunk_size=1024, overlap=128)
        self.file_mapping = {
            "pdf": f"{Path(__file__).resolve().parents[1]}/data/processed/chunks/pdf_chunks.jsonl",
            "doc": f"{Path(__file__).resolve().parents[1]}/data/processed/chunks/doc_chunks.jsonl",
        }
        self.source_folder = Path(
            f"{Path(__file__).resolve().parents[1]}/data/processed/chunks/"
        )
        self.output_file = Path(
            f"{Path(__file__).resolve().parents[1]}/data/processed/master_chunks.jsonl"
        )

        self.output_file.parent.mkdir(parents=True, exist_ok=True)
        for path in self.file_mapping.values():
            os.makedirs(os.path.dirname(path), exist_ok=True)

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
        with ExitStack() as stack:
            # Open all files and store their handles in a dictionary
            # We enforce utf-8 for Chinese character support
            files = {
                category: stack.enter_context(open(path, "a", encoding="utf-8"))
                for category, path in self.file_mapping.items()
            }
            for page in pages:
                language = (
                    "en"
                    if page["metadata"]["doc_meta"].get("language") == "english"
                    else "zh"
                )
                page["text"] = self.pdf_cleaner.clean(page["text"], language=language)
                chunks = self.chunker.chunk(page)
                valid = [c for c in chunks if self.chunker.validate_chunk(c)[0]]
                for c in valid:
                    json_record = json.dumps(c, cls=PipelineEncoder, ensure_ascii=False)
                    if suffix == ".pdf":
                        files["pdf"].write(json_record + "\n")
                    elif suffix in (".docx", ".doc"):
                        files["doc"].write(json_record + "\n")
                    else:
                        raise TypeError(f"Unsupported file type: {suffix}")
                all_chunks.extend(valid)

        self.merge_jsonl_files(self.source_folder, self.output_file)
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

    def merge_jsonl_files(
        self, source_dir: Path, output_file: Path, pattern: str = "*.jsonl"
    ):
        """
        Merges multiple JSONL files from a directory into a single master JSONL file.
        Uses a streaming approach to remain memory-efficient.
        """
        input_files = sorted(source_dir.glob(pattern))

        if not input_files:
            print(f"No files found matching {pattern} in {source_dir}")
            return

        print(f"Merging {len(input_files)} files into {output_file}...")

        # 3. Open the master file for writing
        with open(output_file, "w", encoding="utf-8") as outfile:
            for file_path in input_files:
                # Skip the output file if it's in the same directory to avoid infinite loops
                if file_path.resolve() == output_file.resolve():
                    continue

                with open(file_path, "r", encoding="utf-8") as infile:
                    # We stream line by line to handle files of any size
                    for line in infile:
                        # Strip extra whitespace and ensure each line ends with exactly one newline
                        clean_line = line.strip()
                        if clean_line:
                            outfile.write(clean_line + "\n")


if __name__ == "__main__":
    pipeline = DocumentPipeline()
    chunks = pipeline.process_directory("data/raw/")
    print(f"\n✅ Total chunks: {len(chunks)}")

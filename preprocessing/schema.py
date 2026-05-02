import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NotRequired, Protocol, TypedDict

from docx.opc.coreprops import CoreProperties


class FileMetadata(TypedDict):
    file_path: Path
    filename: str
    total_pages: NotRequired[int]
    file_type: str


class PageMetadata(TypedDict):
    page: int
    page_type: str


class DocMetadata(TypedDict, total=False):
    producer: str
    format: str
    encryption: str
    author: str
    mod_date: datetime | None
    keywords: list[str]
    create_date: datetime | None
    creator: str
    subject: str
    title: str
    language: str


class ChunkMetadata(TypedDict):
    chunk_index: int
    word_count: int


class MetaData(TypedDict):
    file_meta: FileMetadata
    page_meta: PageMetadata
    doc_meta: DocMetadata
    chunk_meta: ChunkMetadata


class PageResult(TypedDict):
    text: str
    metadata: MetaData


class ChunkResult(TypedDict):
    text: str
    metadata: MetaData


class TextExtractor(Protocol):
    def extract_file(self, file_path: str) -> list[PageResult]: ...


class ExtractHelper:
    @staticmethod
    def map_pdf_metadata(raw_meta: dict) -> DocMetadata:
        """
        Safely maps raw dictionary data to the strict DocMetadata TypedDict.
        Handles 'Unknown' or missing keys by providing defaults.
        """
        # Ensure keywords is always a list, even if the PDF provides a string
        raw_keywords = raw_meta.get("keywords", "")
        keywords_list = raw_keywords.split() if isinstance(raw_keywords, str) else []

        # Constructing the dict explicitly ensures type safety
        return {
            "producer": str(raw_meta.get("producer", "")),
            "format": str(raw_meta.get("format", "")),
            "encryption": str(raw_meta.get("encryption", "None")),
            "author": str(raw_meta.get("author", "Unknown")),
            "mod_date": ExtractHelper.parse_pdf_date(str(raw_meta.get("modDate", ""))),
            "keywords": keywords_list,
            "create_date": ExtractHelper.parse_pdf_date(
                str(raw_meta.get("creationDate", ""))
            ),
            "creator": str(raw_meta.get("creator", "")),
            "subject": str(raw_meta.get("subject", "")),
            "title": str(raw_meta.get("title", "")),
        }

    @staticmethod
    def map_doc_metadata(raw_meta: CoreProperties) -> DocMetadata:
        """
        Safely maps raw dictionary data to the strict DocMetadata TypedDict.
        Handles 'Unknown' or missing keys by providing defaults.
        """
        # Ensure keywords is always a list, even if the PDF provides a string
        raw_keywords = raw_meta.keywords
        keywords_list = raw_keywords.split() if isinstance(raw_keywords, str) else []

        # Constructing the dict explicitly ensures type safety
        return {
            "producer": raw_meta.author,
            "author": raw_meta.author,
            "mod_date": raw_meta.modified,
            "keywords": keywords_list,
            "create_date": raw_meta.created,
            "creator": raw_meta.author,
            "subject": raw_meta.subject,
            "title": raw_meta.title,
            "language": raw_meta.language,
        }

    @staticmethod
    def parse_pdf_date(date_str: str) -> datetime | None:
        """
        Converts a PDF metadata date string to a Python datetime object.
        Example input: "D:20260429123045-05'00'"
        """
        if not date_str or not isinstance(date_str, str):
            return None

        # 1. Clean the string: Remove 'D:' prefix and all apostrophes
        clean_str = re.sub(r"[D:']", "", date_str)

        # 2. Extract the main timestamp (first 14 digits: YYYYMMDDHHmmSS)
        # Some PDFs only provide YYYYMMDD, so we handle variable lengths.
        base_date_part = clean_str[:14]

        try:
            # Determine format based on length if the string is short
            fmt = (
                "%Y%m%d%H%M%S"[: len(base_date_part) - 2]
                if len(base_date_part) < 14
                else "%Y%m%d%H%M%S"
            )
            dt = datetime.strptime(base_date_part, fmt)

            # 3. Handle Timezone Offset (e.g., -0500 or +0800)
            # The offset starts after the 14th character of the cleaned string
            offset_part = clean_str[14:]
            if offset_part and len(offset_part) >= 5:
                sign = 1 if offset_part[0] == "+" else -1
                try:
                    hours = int(offset_part[1:3])
                    minutes = int(offset_part[3:5])
                    tz = timezone(timedelta(hours=sign * hours, minutes=sign * minutes))
                    dt = dt.replace(tzinfo=tz)
                except ValueError:
                    # If offset parsing fails, return naive datetime
                    pass

            return dt
        except ValueError:
            return None

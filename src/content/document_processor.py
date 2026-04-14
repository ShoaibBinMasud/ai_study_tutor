"""
DocumentProcessor — routes any uploaded file to the right processor.

Supports: PDF, images (PNG/JPG/WEBP), PPTX, DOCX, TXT, MD
All processors return a unified ProcessedDocument.
"""

import logging
from pathlib import Path

from models.data_models import ProcessedDocument
from utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".pdf": "pdf",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".pptx": "pptx",
    ".docx": "docx",
    ".txt": "text",
    ".md": "text",
}


class UnsupportedFileType(Exception):
    pass


def classify_pdf(pdf_path: str) -> dict:
    """
    Quick PDF classification — zero LLM calls.

    Returns dict with:
        total_pages, has_toc, toc_count, avg_chars_per_page,
        is_scanned, sample_text (first 500 chars from page 1)
    """
    try:
        import fitz
        doc = fitz.open(pdf_path)
        total_pages = len(doc)

        raw_toc = doc.get_toc()
        toc_count = len(raw_toc)
        has_toc = toc_count > 3

        # Sample pages for text content
        sample_indices = [0, min(1, total_pages - 1), min(2, total_pages - 1)]
        total_chars = 0
        for idx in sample_indices:
            if idx < total_pages:
                total_chars += len(doc[idx].get_text())

        avg_chars = total_chars / max(len(sample_indices), 1)

        # Grab preview text from page 1
        sample_text = doc[0].get_text()[:500] if total_pages > 0 else ""

        doc.close()

        return {
            "total_pages": total_pages,
            "has_toc": has_toc,
            "toc_count": toc_count,
            "avg_chars_per_page": avg_chars,
            "is_scanned": avg_chars < 300 and not has_toc,
            "sample_text": sample_text,
        }
    except Exception as e:
        logger.debug(f"classify_pdf failed: {e}")
        return {
            "total_pages": 0,
            "has_toc": False,
            "toc_count": 0,
            "avg_chars_per_page": 0,
            "is_scanned": False,
            "sample_text": "",
        }


class DocumentProcessor:
    """Routes files to the appropriate processor and returns ProcessedDocument."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
        self._pdf_processor = None
        self._intelligent_parser = None
        self._image_processor = None
        self._pptx_processor = None
        self._docx_processor = None
        self._text_processor = None

    def process(self, file_path: str) -> ProcessedDocument:
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext not in SUPPORTED_EXTENSIONS:
            raise UnsupportedFileType(
                f"Unsupported file type '{ext}'. "
                f"Supported: {', '.join(SUPPORTED_EXTENSIONS.keys())}"
            )

        file_type = SUPPORTED_EXTENSIONS[ext]
        logger.info(f"Processing {file_type} file: {path.name}")

        if file_type == "pdf":
            # Route to intelligent parser for image-heavy PDFs, regular processor otherwise
            if self._should_use_intelligent_parser(file_path):
                logger.info(f"Using IntelligentDocumentParser (image-heavy PDF)")
                return self._get_intelligent_parser().process(file_path)
            else:
                return self._get_pdf_processor().process(file_path)
        elif file_type == "image":
            return self._get_image_processor().process(file_path)
        elif file_type == "pptx":
            return self._get_pptx_processor().process(file_path)
        elif file_type == "docx":
            return self._get_docx_processor().process(file_path)
        elif file_type == "text":
            return self._get_text_processor().process(file_path)

    # Lazy-load processors to avoid import errors for missing optional deps
    def _get_pdf_processor(self):
        if self._pdf_processor is None:
            from content.processors.pdf_processor import PDFProcessor
            self._pdf_processor = PDFProcessor(self.llm)
        return self._pdf_processor

    def _get_image_processor(self):
        if self._image_processor is None:
            from content.processors.image_processor import ImageProcessor
            self._image_processor = ImageProcessor(self.llm)
        return self._image_processor

    def _get_pptx_processor(self):
        if self._pptx_processor is None:
            from content.processors.pptx_processor import PPTXProcessor
            self._pptx_processor = PPTXProcessor()
        return self._pptx_processor

    def _get_docx_processor(self):
        if self._docx_processor is None:
            from content.processors.docx_processor import DOCXProcessor
            self._docx_processor = DOCXProcessor()
        return self._docx_processor

    def _get_text_processor(self):
        if self._text_processor is None:
            from content.processors.text_processor import TextProcessor
            self._text_processor = TextProcessor()
        return self._text_processor

    def _get_intelligent_parser(self):
        if self._intelligent_parser is None:
            from content.intelligent_parser import IntelligentDocumentParser
            self._intelligent_parser = IntelligentDocumentParser(self.llm)
        return self._intelligent_parser

    def _should_use_intelligent_parser(self, pdf_path: str) -> bool:
        """Quick heuristic check: is this PDF image-heavy/slides?"""
        result = classify_pdf(pdf_path)
        if result["is_scanned"]:
            logger.info(f"  Detected sparse text ({result['avg_chars_per_page']:.0f} chars/page) → using IntelligentDocumentParser")
        return result["is_scanned"]

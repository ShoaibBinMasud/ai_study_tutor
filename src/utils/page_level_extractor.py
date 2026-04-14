"""
Page-Level RAG Extractor

This extractor creates ONE chunk per page with full metadata:
- Chapter number and title
- Section number and title  
- Subsection number and title
- Content types present (text, examples, etc.)
- Example numbers found on the page

The entire page text is combined into a single chunk.
"""

import fitz
import logging
from pathlib import Path
from typing import Dict, List, Optional
from langchain_core.documents import Document
import json

from .pdf_extractor_utils import (
    FontAnalyzer, 
    PageProcessor, 
    TokenCounter
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PageLevelExtractor:
    """
    Extract PDF with one chunk per page, including full metadata.
    """
    
    def __init__(self, pdf_path: str):
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        self.doc = fitz.open(str(self.pdf_path))
        self.token_counter = TokenCounter()
        
        logger.info(f"Loaded PDF: {self.pdf_path.name} ({len(self.doc)} pages)")
    
    def extract_pages(self, pages: Optional[List[int]] = None) -> List[Document]:
        """
        Extract one chunk per page with full metadata.
        
        Args:
            pages: Optional list of page numbers (1-indexed). None = all pages.
        
        Returns:
            List of Document objects, one per page
        """
        # Parse pages parameter
        if pages is not None:
            page_indices = [p - 1 for p in pages if 1 <= p <= len(self.doc)]
            if not page_indices:
                raise ValueError(f"Invalid pages: {pages}. PDF has {len(self.doc)} pages.")
            logger.info(f"Processing {len(page_indices)} specific pages")
        else:
            page_indices = list(range(len(self.doc)))
            logger.info(f"Processing all {len(self.doc)} pages")
        
        # Step 1: Analyze fonts
        logger.info("Step 1: Analyzing document fonts...")
        font_analyzer = FontAnalyzer(self.doc)
        font_info = font_analyzer.analyze()
        
        # Step 2: Process pages
        logger.info("Step 2: Processing pages...")
        processor = PageProcessor(self.doc, font_info)
        
        # Track context
        current_chapter = None
        current_section = None
        current_subsection = None
        last_chapter_num = None
        has_reset_for_chapter1 = False
        in_special_section = False
        
        chunks = []
        
        for page_num in page_indices:
            if page_num % 50 == 0:
                logger.info(f"  Processing page {page_num + 1}/{len(self.doc)}...")
            
            # Process this page
            page_data = processor.process_page(page_num, current_section, current_subsection)
            
            # Handle special sections (Appendix, Bibliography, etc.)
            if page_data.get("detected_special_section"):
                special = page_data["detected_special_section"]
                
                if special['category'] == 'APPENDIX':
                    current_chapter = {
                        "number": special['title'],
                        "title": special['title']
                    }
                    current_section = None
                    current_subsection = None
                    in_special_section = True
                else:
                    current_chapter = None
                    current_section = None
                    current_subsection = None
                    in_special_section = True
            
            # Update context from detected headers
            if page_data.get("detected_chapter") and not in_special_section:
                new_chapter = page_data["detected_chapter"]
                
                # Handle "INFER" chapter number
                if new_chapter.get('number') == 'INFER':
                    inferred_num = (last_chapter_num + 1) if last_chapter_num else 1
                    new_chapter['number'] = str(inferred_num)
                
                # Validate chapter
                try:
                    new_ch_num = int(new_chapter['number']) if new_chapter['number'] else None
                except (ValueError, TypeError):
                    new_ch_num = None
                
                # Detect Chapter 1
                if new_ch_num == 1 and not has_reset_for_chapter1:
                    current_section = None
                    current_subsection = None
                    last_chapter_num = None
                    has_reset_for_chapter1 = True
                
                # Validation logic (same as enhanced_rag_extractor)
                is_valid_chapter = True
                if last_chapter_num and new_ch_num:
                    if new_ch_num < last_chapter_num and (last_chapter_num - new_ch_num) > 2:
                        is_valid_chapter = False
                
                chapter_title = new_chapter.get('title', '')
                if chapter_title:
                    import re as re_module
                    special_char_count = sum(not c.isalnum() and not c.isspace() for c in chapter_title)
                    total_chars = len(chapter_title.replace(' ', ''))
                    special_ratio = special_char_count / max(total_chars, 1)
                    has_real_words = bool(re_module.search(r'[a-zA-Z]{3,}', chapter_title))
                    
                    if special_ratio > 0.4 and len(chapter_title) < 20:
                        is_valid_chapter = False
                    elif not any(c.isalpha() for c in chapter_title) and len(chapter_title) < 10:
                        is_valid_chapter = False
                    elif not has_real_words and len(chapter_title) < 15:
                        is_valid_chapter = False
                
                if is_valid_chapter and new_ch_num:
                    if new_ch_num > 25:
                        is_valid_chapter = False
                    elif last_chapter_num and new_ch_num < last_chapter_num - 1 and not (new_ch_num == 1 and not has_reset_for_chapter1):
                        is_valid_chapter = False
                    elif last_chapter_num and new_ch_num > last_chapter_num + 2:
                        is_valid_chapter = False
                
                if is_valid_chapter:
                    current_chapter = new_chapter
                    last_chapter_num = new_ch_num
            
            if page_data.get("detected_section"):
                current_section = page_data["detected_section"]
                current_subsection = None
            
            if page_data.get("detected_subsection"):
                current_subsection = page_data["detected_subsection"]
            
            # Combine all text blocks on this page
            page_text_blocks = []
            example_numbers = []
            content_types_on_page = set()
            
            for block in page_data["text_blocks"]:
                text = block["text"].strip()
                if text:
                    page_text_blocks.append(text)
                    
                    # Track content types
                    if block.get("is_example") and block.get("example_info"):
                        example_info = block["example_info"]
                        content_types_on_page.add(example_info["content_type"])
                        if example_info["number"]:
                            example_numbers.append(example_info["number"])
                    else:
                        content_types_on_page.add("text")
            
            # Skip empty pages
            if not page_text_blocks:
                continue
            
            # Combine all text from the page
            page_content = "\n\n".join(page_text_blocks)
            
            # Build metadata for this page
            metadata = {
                "source": self.pdf_path.name,
                "page": page_num + 1,
                "chapter_number": current_chapter["number"] if current_chapter else None,
                "chapter_title": current_chapter["title"] if current_chapter else None,
                "section_number": current_section["number"] if current_section else None,
                "section_title": current_section["title"] if current_section else None,
                "subsection_number": current_subsection["number"] if current_subsection else None,
                "subsection_title": current_subsection["title"] if current_subsection else None,
                "content_types": list(content_types_on_page),  # e.g., ["text", "example"]
                "example_numbers": example_numbers if example_numbers else None,
                "word_count": len(page_content.split()),
                "token_count": self.token_counter.count_tokens(page_content),
                "chunk_id": f"{self.pdf_path.stem}_p{page_num + 1}"
            }
            
            # Create one chunk per page
            chunks.append(Document(
                page_content=page_content,
                metadata=metadata
            ))
        
        logger.info(f"Extraction complete: {len(chunks)} pages extracted (1 chunk per page)")
        return chunks


def export_chunks(chunks: List[Document], output_file: str):
    """Export LangChain Documents to JSON"""
    data = {
        "metadata": {
            "total_chunks": len(chunks),
            "chunk_types": {},
            "chunking_strategy": "page-level",
            "description": "One chunk per page with full metadata",
            "format": "langchain_document"
        },
        "chunks": [
            {
                "page_content": doc.page_content,
                "metadata": doc.metadata
            }
            for doc in chunks
        ]
    }
    
    # Count by content types
    for chunk in chunks:
        content_types = chunk.metadata.get("content_types", ["text"])
        for ctype in content_types:
            data["metadata"]["chunk_types"][ctype] = data["metadata"]["chunk_types"].get(ctype, 0) + 1
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Exported {len(chunks)} page-level chunks to {output_file}")


def main():
    """Example usage"""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python page_level_extractor.py <pdf_path>")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    
    try:
        # Extract page-level chunks
        extractor = PageLevelExtractor(pdf_path)
        chunks = extractor.extract_pages()
        
        # Print summary
        print("\n" + "="*80)
        print(f"Page-Level Extraction Complete: {Path(pdf_path).name}")
        print("="*80)
        
        print(f"\nTotal chunks: {len(chunks)} (1 chunk per page)")
        
        # Group by content type
        pages_with_examples = 0
        pages_with_text_only = 0
        
        for chunk in chunks:
            content_types = chunk.metadata.get('content_types', [])
            if 'example' in content_types:
                pages_with_examples += 1
            if content_types == ['text']:
                pages_with_text_only += 1
        
        print(f"\nContent distribution:")
        print(f"   Pages with examples: {pages_with_examples}")
        print(f"   Pages with text only: {pages_with_text_only}")
        
        # Show sample chunks
        print(f"\n{'='*80}")
        print("Sample Pages (first 3):")
        print("="*80)
        
        for i, chunk in enumerate(chunks[:3], 1):
            meta = chunk.metadata
            content = chunk.page_content
            
            print(f"\n[Page {meta['page']}]")
            print(f"Chapter: {meta.get('chapter_number')} - {meta.get('chapter_title')}")
            print(f"Section: {meta.get('section_number')} - {meta.get('section_title')}")
            if meta.get('subsection_title'):
                print(f"Subsection: {meta.get('subsection_number')} - {meta.get('subsection_title')}")
            print(f"Content types: {meta.get('content_types')}")
            if meta.get('example_numbers'):
                print(f"Examples: {meta.get('example_numbers')}")
            print(f"Tokens: {meta.get('token_count')}, Words: {meta['word_count']}")
            print(f"\nContent preview (first 200 chars):")
            print(f"  {content[:200]}...")
            print("-"*80)
        
        # Export
        output_file = Path(pdf_path).stem + "_page_level_chunks.json"
        export_chunks(chunks, output_file)
        
        print(f"\nExported to: {output_file}")
        
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

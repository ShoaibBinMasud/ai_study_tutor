"""
LLM Tool for PDF Content Extraction

This module provides a simple tool for extracting text content from PDF page ranges.
Compatible with any LLM that supports OpenAI-style function calling (GPT, Gemini, Claude, Llama).

Usage with LLMPDFNavigator:
    from pdf_extraction_tool import extract_pdf_pages, PDF_EXTRACTION_TOOL
    
    # Use the function directly
    text = extract_pdf_pages("physics.pdf", start_page=10, end_page=24)
    
    # Or add to your LLM tools
    tools = [PDF_NAVIGATOR_TOOL, PDF_EXTRACTION_TOOL]

Usage standalone:
    python pdf_extraction_tool.py physics.pdf 10 24
"""

import sys
import logging
from pathlib import Path
from typing import Optional, List
from utils.page_level_extractor import PageLevelExtractor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# Core Extraction Function
# ============================================================================

def extract_pdf_pages(
    pdf_path: str,
    start_page: int,
    end_page: int,
    strategy: str = "page-level"
) -> str:
    """
    Extract text content from a PDF page range.
    
    This function extracts clean text content from the specified page range
    of a PDF document. It's designed for LLM consumption and returns formatted
    text suitable for analysis or question answering.
    
    Args:
        pdf_path: Path to the PDF file (relative or absolute)
        start_page: Starting page number (1-indexed, inclusive)
        end_page: Ending page number (1-indexed, inclusive)
        strategy: Extraction strategy ("page-level" is default and recommended)
    
    Returns:
        Extracted text content as a formatted string with page markers
        
    Raises:
        FileNotFoundError: If PDF file doesn't exist
        ValueError: If page range is invalid
        
    Example:
        >>> text = extract_pdf_pages("physics.pdf", 10, 24)
        >>> print(text)
        === PAGE 10 ===
        Chapter 2: Relativity
        ...
        === PAGE 11 ===
        ...
    """
    try:
        # Validate PDF path
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            return f"Error: PDF file not found: {pdf_path}"
        
        # Initialize extractor
        extractor = PageLevelExtractor(str(pdf_file))
        total_pages = len(extractor.doc)
        
        # Validate page range
        if start_page < 1:
            return f"Error: start_page must be >= 1 (got {start_page})"
        if end_page > total_pages:
            return f"Error: end_page ({end_page}) exceeds PDF length ({total_pages} pages)"
        if start_page > end_page:
            return f"Error: start_page ({start_page}) must be <= end_page ({end_page})"
        
        # PageLevelExtractor uses 1-based page numbers
        page_list = list(range(start_page, end_page + 1))
        
        logger.info(f"Extracting pages {start_page}-{end_page} from {pdf_file.name} ({len(page_list)} pages)")
        
        # Extract chunks (one per page)
        chunks = extractor.extract_pages(pages=page_list)
        
        if not chunks:
            return f"Error: No content extracted from pages {start_page}-{end_page}"
        
        # Format output for LLM consumption
        output_lines = []
        output_lines.append(f"PDF: {pdf_file.name}")
        output_lines.append(f"Pages: {start_page}-{end_page} ({len(chunks)} pages)")
        output_lines.append("=" * 80)
        output_lines.append("")
        
        for chunk in chunks:
            # Extract page number from metadata
            page_num = chunk.metadata.get('page', 'unknown')
            chapter_info = chunk.metadata.get('chapter', {})
            section_info = chunk.metadata.get('section', {})
            
            # Page header with context
            output_lines.append(f"{'=' * 80}")
            output_lines.append(f"PAGE {page_num}")
            
            # Add chapter/section context if available
            if chapter_info and chapter_info.get('title'):
                ch_num = chapter_info.get('number', '?')
                ch_title = chapter_info.get('title', '')
                output_lines.append(f"Chapter {ch_num}: {ch_title}")
            
            if section_info and section_info.get('title'):
                sec_num = section_info.get('number', '?')
                sec_title = section_info.get('title', '')
                output_lines.append(f"  Section {sec_num}: {sec_title}")
            
            output_lines.append(f"{'=' * 80}")
            
            # Add page content
            output_lines.append(chunk.page_content.strip())
            output_lines.append("")  # Blank line between pages
        
        # Add summary
        output_lines.append("")
        output_lines.append("=" * 80)
        output_lines.append(f"EXTRACTION COMPLETE: {len(chunks)} pages extracted")
        output_lines.append("=" * 80)
        
        result = "\n".join(output_lines)
        logger.info(f"Successfully extracted {len(chunks)} pages, {len(result)} characters")
        
        return result
        
    except Exception as e:
        error_msg = f"Error extracting PDF content: {str(e)}"
        logger.error(error_msg)
        return error_msg


# ============================================================================
# Tool Definition for LLM (OpenAI Function Calling Format)
# ============================================================================

PDF_EXTRACTION_TOOL = {
    "type": "function",
    "function": {
        "name": "extract_pdf_pages",
        "description": (
            "Extract text content from a specific page range in a PDF document. "
            "Returns the full text content with page markers, chapter/section context, "
            "and metadata. Use this when the user wants to read or analyze specific pages "
            "from the PDF. For example: 'show me pages 10-24', 'what's on page 50', "
            "'extract pages 100 to 150', 'read chapter 2 pages'. "
            "Page numbers are 1-indexed (first page is page 1)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pdf_path": {
                    "type": "string",
                    "description": (
                        "Path to the PDF file to extract from. "
                        "Can be absolute path like 'C:/docs/physics.pdf' or "
                        "relative path like 'physics.pdf'"
                    )
                },
                "start_page": {
                    "type": "integer",
                    "description": (
                        "Starting page number (1-indexed, inclusive). "
                        "First page of the PDF is page 1. "
                        "Example: For pages 10-24, start_page=10"
                    ),
                    "minimum": 1
                },
                "end_page": {
                    "type": "integer",
                    "description": (
                        "Ending page number (1-indexed, inclusive). "
                        "Must be >= start_page. "
                        "Example: For pages 10-24, end_page=24"
                    ),
                    "minimum": 1
                },
                "strategy": {
                    "type": "string",
                    "description": (
                        "Extraction strategy to use. Default is 'page-level' which "
                        "extracts one chunk per page. This is recommended for most uses."
                    ),
                    "enum": ["page-level"],
                    "default": "page-level"
                }
            },
            "required": ["pdf_path", "start_page", "end_page"]
        }
    }
}


# ============================================================================
# Command Line Interface
# ============================================================================

def main():
    """Command line interface for testing the tool."""
    if len(sys.argv) < 4:
        print(__doc__)
        print("\nUsage: python pdf_extraction_tool.py <pdf_path> <start_page> <end_page>")
        print("\nExample:")
        print("  python pdf_extraction_tool.py modern_physics.pdf 10 24")
        print("  python pdf_extraction_tool.py Nelson-Physics-12.pdf 1 5")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    try:
        start_page = int(sys.argv[2])
        end_page = int(sys.argv[3])
    except ValueError:
        print("Error: start_page and end_page must be integers")
        sys.exit(1)
    
    print("\n" + "=" * 80)
    print("PDF EXTRACTION TOOL")
    print("=" * 80)
    print(f"PDF: {pdf_path}")
    print(f"Pages: {start_page}-{end_page}")
    print("=" * 80 + "\n")
    
    # Extract content
    result = extract_pdf_pages(pdf_path, start_page, end_page)
    
    # Print result
    print(result)
    
    # Optionally save to file
    output_file = f"extracted_pages_{start_page}-{end_page}.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(result)
    
    print(f"\n[OK] Content saved to: {output_file}")


if __name__ == "__main__":
    main()

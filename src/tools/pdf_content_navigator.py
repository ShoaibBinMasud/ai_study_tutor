"""
PDF Content Navigator
=====================
Production-ready tool for extracting chapter/section page ranges from PDFs.

Strategy:
1. Use PyMuPDF's built-in ToC (doc.get_toc())
2. Build chapter/section index with start/end pages
3. Support search by number or name
4. Auto-detect parent chapter from section numbers

Usage:
    result = get_pdf_content_range("textbook.pdf")  # All content
    result = get_pdf_content_range("textbook.pdf", chapter=1)  # Chapter 1 + sections
    result = get_pdf_content_range("textbook.pdf", section="1.2")  # Section + parent chapter
"""

import fitz
import re
from typing import Dict, List, Optional, Union
from pathlib import Path


def get_pdf_content_range(
    pdf_path: str,
    chapter: Union[str, int, None] = "all",
    section: Union[str, int, None] = "all"
) -> str:
    """
    Get page ranges for chapters/sections from PDF's built-in ToC.
    
    Args:
        pdf_path: Path to PDF file
        chapter: "all" (default), single chapter (1), name ("Introduction"),
                range ("1-3" for chapters 1,2,3), or list ("1,3,5")
        section: "all" (default), section number ("1-2", "4-5"), name ("Methods"),
                range with "to" ("1-1 to 1-5"), or list ("1-2,4-5,7-1")
                NOTE: "4-5" is section 5 in chapter 4 (single section)
                      For ranges, use "to": "4-1 to 4-5" (multiple sections)
    
    Returns:
        Formatted text string with page ranges. Format depends on query:
        - chapter="all": Complete table of contents with all chapters and their sections
        - chapter=N: That chapter's range + all sections inside
        - chapter="1-3": Multiple chapters with their page ranges and sections
        - section="4-5": That section's range + parent chapter info
        - section="1-1 to 1-5": Multiple sections with their page ranges
        - chapter=N + section=M: Both chapter and section info (combined query)
        - Error message if ToC not found or chapter/section doesn't exist
    
    Examples:
        >>> get_pdf_content_range("book.pdf")
        "Available Chapters (12 total, pages 15-450):\nTotal Sections: 87\n\n1. Introduction (pages 15-45)\n   Sections (4):\n     - 1-1 Overview..."
        
        >>> get_pdf_content_range("book.pdf", chapter=1)
        "Chapter: Introduction (pages 15-45)\nSections:\n  1.1 Background (pages 16-20)\n..."
        
        >>> get_pdf_content_range("book.pdf", chapter="1-3")
        "Chapters 1-3 (pages 15-120):\n\nChapter 1: Introduction (pages 15-45)\n..."
        
        >>> get_pdf_content_range("book.pdf", section="4-5")
        "Section: 4-5 Experiments (pages 192-202)\nParent Chapter: Chapter 4 (pages 180-220)"
        
        >>> get_pdf_content_range("book.pdf", section="1-1 to 1-3")
        "Found 3 sections (pages 16-45):\n\nSection: 1-1 Intro...\nSection: 1-2...\nSection: 1-3..."
        
        >>> get_pdf_content_range("book.pdf", chapter=2, section="5-2")
        "CHAPTERS:\n  Chapter 2: Methodology (pages 46-80)\n\nSECTIONS:\n  Section: 5-2 Analysis [from Chapter 5] (pages 205-213)"
    """
    # Load PDF and extract ToC
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        return f"Error: Failed to open PDF '{pdf_path}'\n{str(e)}"
    
    builtin_toc = doc.get_toc()
    
    # Check if ToC exists
    if not builtin_toc:
        return f"Error: No Table of Contents found in this PDF.\nPlease manually specify the page range or starting page.\nTotal pages in PDF: {len(doc)}"
    
    # Build chapter/section index
    index = _build_chapter_index(builtin_toc, len(doc))
    
    # Route to appropriate handler
    if section != "all" and chapter != "all":
        # Combined query: both chapter and section specified
        return _handle_combined_query(chapter, section, index, doc)
    elif section != "all":
        # Section query only - check if multiple
        section_ids = _parse_range_or_list(str(section), is_section=True)
        if len(section_ids) > 1:
            return _handle_multiple_sections_query(section_ids, index, doc)
        else:
            return _handle_section_query(section, index, doc)
    elif chapter != "all":
        # Chapter query only - check if multiple
        chapter_ids = _parse_range_or_list(str(chapter), is_section=False)
        if len(chapter_ids) > 1:
            return _handle_multiple_chapters_query(chapter_ids, index, doc)
        else:
            return _handle_chapter_query(chapter, index, doc)
    else:
        # Default: all content range
        return _handle_all_content_query(index, doc)


def _build_chapter_index(toc: List, total_pages: int) -> Dict:
    """Build index of chapters and sections with page ranges."""
    index = {
        'chapters': [],
        'sections': [],
        'by_number': {},
    }
    
    for i, (level, title, page_num) in enumerate(toc):
        # Calculate end page
        end_page = total_pages
        for j in range(i + 1, len(toc)):
            next_level, _, next_page = toc[j]
            if next_level <= level:
                end_page = next_page - 1
                break
        
        entry = {
            'level': level,
            'title': title,
            'start_page': page_num,
            'end_page': end_page,
            'page_count': end_page - page_num + 1
        }
        
        # Extract number
        number = _extract_number(title)
        if number:
            entry['number'] = number
            index['by_number'][number] = entry
        
        # Categorize as chapter or section
        # Skip Answers, Appendices, and other back matter (usually after page 700)
        is_back_matter = (
            page_num >= 700 or
            any(word in title.lower() for word in ['answer', 'appendix', 'index', 'glossary'])
        )
        
        # Only detect as chapter if:
        # 1. Not in back matter
        # 2. Level 1-2
        # 3. Contains PART or CHAPTER (strict pattern)
        if not is_back_matter and level <= 2:
            title_lower = title.lower()
            # More strict: must match "CHAPTER \d+" or "PART \d+" pattern
            if (re.search(r'\bchapter\s+\d+', title_lower) or 
                re.search(r'\bpart\s+\d+', title_lower)):
                index['chapters'].append(entry)
            else:
                index['sections'].append(entry)
        else:
            index['sections'].append(entry)
    
    return index


def _parse_range_or_list(value: str, is_section: bool = False) -> List[str]:
    """
    Parse chapter/section input that can be:
    - Single: "1" -> ["1"]
    - Range: "1-3" -> ["1", "2", "3"] (chapters only)
    - List: "1,3,5" -> ["1", "3", "5"]
    - Section number: "4-5" -> ["4-5"] (when is_section=True)
    - Section range: "1-1 to 1-3" -> ["1-1", "1-2", "1-3"]
    
    Args:
        value: The input string to parse
        is_section: If True, treat "X-Y" as a section number by default, not a range.
                   Use "to" keyword for section ranges: "1-1 to 1-5"
    """
    value = value.strip()
    
    # Check for "to" keyword (section ranges)
    if " to " in value.lower():
        parts = value.lower().split(" to ")
        if len(parts) == 2:
            start_sec = parts[0].strip()
            end_sec = parts[1].strip()
            # Extract chapter and section numbers
            # E.g., "1-1" -> chapter=1, section=1
            if '-' in start_sec and '-' in end_sec:
                start_ch, start_s = start_sec.split('-', 1)
                end_ch, end_s = end_sec.split('-', 1)
                
                # Only support same chapter for now
                if start_ch == end_ch:
                    try:
                        start_num = int(start_s)
                        end_num = int(end_s)
                        return [f"{start_ch}-{i}" for i in range(start_num, end_num + 1)]
                    except ValueError:
                        pass
            elif '.' in start_sec and '.' in end_sec:
                start_ch, start_s = start_sec.split('.', 1)
                end_ch, end_s = end_sec.split('.', 1)
                
                # Only support same chapter for now
                if start_ch == end_ch:
                    try:
                        start_num = int(start_s)
                        end_num = int(end_s)
                        return [f"{start_ch}.{i}" for i in range(start_num, end_num + 1)]
                    except ValueError:
                        pass
    
    # Check for comma-separated list
    if ',' in value:
        return [item.strip() for item in value.split(',')]
    
    # Check for range like "1-3" vs section number like "4-5"
    if '-' in value:
        parts = value.split('-')
        if len(parts) == 2:
            try:
                start = int(parts[0].strip())
                end = int(parts[1].strip())
                
                # Decision logic:
                # 1. If is_section=True, treat as section number by default
                # 2. If is_section=False (chapters), treat as range if end > start
                
                if is_section:
                    # For sections, always treat "X-Y" as section number
                    # Use "to" keyword for ranges: "1-1 to 1-5"
                    return [value]
                else:
                    # For chapters, treat as range if end > start
                    if end > start:
                        return [str(i) for i in range(start, end + 1)]
            except ValueError:
                pass
    
    # Single value
    return [value]


def _extract_number(title: str) -> Optional[str]:
    """Extract chapter/section number from title (supports 1.2, 1-2, etc.)."""
    patterns = [
        r'chapter\s+(\d+)',
        r'unit\s+(\d+)',
        r'part\s+(\d+)',
        r'section\s+(\d+(?:[\.\-]\d+)?)',  # Matches "1.2" or "1-2"
        r'^(\d+(?:[\.\-]\d+)?)\s*[:\|\-]',  # Matches "1-2:" or "1.2:"
        r'^(\d+)\s+[A-Z]',
    ]
    
    title_lower = title.lower()
    for pattern in patterns:
        match = re.search(pattern, title_lower)
        if match:
            return match.group(1)
    
    return None


def _handle_combined_query(chapter: Union[str, int], section: Union[str, int], index: Dict, doc) -> str:
    """
    Handle combined chapter + section query.
    Returns information about both the specified chapter(s) and section(s).
    """
    lines = []
    
    # Parse chapter(s)
    chapter_ids = _parse_range_or_list(str(chapter), is_section=False)
    
    # Parse section(s)
    section_ids = _parse_range_or_list(str(section), is_section=True)
    
    # Process chapters
    chapters_found = []
    for chapter_id in chapter_ids:
        ch = _find_chapter(chapter_id, index)
        if ch:
            chapters_found.append(ch)
    
    # Process sections
    sections_found = []
    for section_id in section_ids:
        sec = _find_section(section_id, index)
        if sec:
            sections_found.append(sec)
    
    # Build output
    if not chapters_found and not sections_found:
        return f"No chapters or sections found for: chapter={chapter}, section={section}"
    
    # Chapter information
    if chapters_found:
        lines.append("CHAPTERS:")
        for ch in sorted(chapters_found, key=lambda x: x['start_page']):
            lines.append(f"  Chapter {ch.get('number', '?')}: {ch['title']} (pages {ch['start_page']}-{ch['end_page']})")
            
            # Show sections within this chapter
            ch_sections = _find_sections_in_chapter(ch, index)
            if ch_sections:
                lines.append(f"    Sections ({len(ch_sections)}):")
                for s in ch_sections:
                    lines.append(f"      {s['title']} (pages {s['start_page']}-{s['end_page']})")
        lines.append("")
    
    # Section information
    if sections_found:
        lines.append("SECTIONS:")
        for sec in sorted(sections_found, key=lambda x: x['start_page']):
            parent = _find_parent_chapter(sec, index)
            parent_info = f" [from {parent['title']}]" if parent else ""
            lines.append(f"  Section: {sec['title']}{parent_info} (pages {sec['start_page']}-{sec['end_page']})")
    
    # Note if some items not found
    not_found = []
    if len(chapters_found) < len(chapter_ids):
        not_found.append(f"chapter(s): {', '.join([c for c in chapter_ids if not any(ch.get('number') == c for ch in chapters_found)])}")
    if len(sections_found) < len(section_ids):
        not_found.append(f"section(s): {', '.join([s for s in section_ids if not any(sec.get('number') == s for sec in sections_found)])}")
    
    if not_found:
        lines.append(f"\nNote: Not found: {', '.join(not_found)}")
    
    return "\n".join(lines)


def _handle_all_content_query(index: Dict, doc) -> str:
    """Handle query for all content with list of all chapters and their sections."""
    chapters = index['chapters']
    
    if not chapters:
        return f"Error: No chapters found in Table of Contents.\nFound {len(index['sections'])} sections instead."
    
    # Sort by start page
    chapters_sorted = sorted(chapters, key=lambda x: x['start_page'])
    
    # Build text output
    start_page = chapters_sorted[0]['start_page']
    end_page = chapters_sorted[-1]['end_page']
    total_chapters = len(chapters_sorted)
    
    # Count total sections
    total_sections = 0
    for ch in chapters_sorted:
        sections = _find_sections_in_chapter(ch, index)
        total_sections += len(sections)
    
    lines = []
    lines.append(f"Available Chapters ({total_chapters} total, pages {start_page}-{end_page}):")
    lines.append(f"Total Sections: {total_sections}\n")
    
    for i, ch in enumerate(chapters_sorted, 1):
        # Find sections in this chapter
        ch_sections = _find_sections_in_chapter(ch, index)
        
        lines.append(f"{i}. {ch['title']} (pages {ch['start_page']}-{ch['end_page']})")
        
        if ch_sections:
            lines.append(f"   Sections ({len(ch_sections)}):")
            for sec in ch_sections:
                lines.append(f"     - {sec['title']} (pages {sec['start_page']}-{sec['end_page']})")
        else:
            lines.append(f"   Sections (0)")
        
        # Add blank line between chapters (except last)
        if i < len(chapters_sorted):
            lines.append("")
    
    return "\n".join(lines)


def _handle_chapter_query(chapter_id: Union[str, int], index: Dict, doc) -> str:
    """Handle query for specific chapter."""
    # Find chapter by number or name
    chapter = _find_chapter(chapter_id, index)
    
    if not chapter:
        # Return available chapters
        chapters_sorted = sorted(index['chapters'], key=lambda x: x['start_page'])
        lines = []
        lines.append(f"Chapter '{chapter_id}' not found.")
        lines.append("(Search supports: chapter number like '1' or name like 'Relativity')\n")
        lines.append("Available Chapters:\n")
        
        for i, ch in enumerate(chapters_sorted, 1):
            lines.append(f"{i}. {ch['title']} (pages {ch['start_page']}-{ch['end_page']})")
        
        return "\n".join(lines)
    
    # Find sections within this chapter
    sections = _find_sections_in_chapter(chapter, index)
    
    # Build text output
    lines = []
    lines.append(f"Chapter: {chapter['title']} (pages {chapter['start_page']}-{chapter['end_page']})\n")
    
    if sections:
        lines.append("Sections:")
        for s in sections:
            lines.append(f"  {s['title']} (pages {s['start_page']}-{s['end_page']})")
    else:
        lines.append("No sections found in this chapter.")
    
    return "\n".join(lines)


def _handle_section_query(section_id: Union[str, int], index: Dict, doc) -> str:
    """Handle query for specific section."""
    # Find section by number or name
    section = _find_section(section_id, index)
    
    if not section:
        # Return available sections
        sections_sorted = sorted(index['sections'], key=lambda x: x['start_page'])
        lines = []
        lines.append(f"Section '{section_id}' not found.")
        lines.append("(Search supports: section number like '1-2' or name with 4+ chars and 60% word match)\n")
        lines.append("Available Sections:\n")
        
        # Limit to first 20 sections to avoid overwhelming output
        for i, s in enumerate(sections_sorted[:20], 1):
            lines.append(f"{i}. {s['title']} (pages {s['start_page']}-{s['end_page']})")
        
        if len(sections_sorted) > 20:
            lines.append(f"\n... and {len(sections_sorted) - 20} more sections")
        
        return "\n".join(lines)
    
    # Auto-detect parent chapter
    parent_chapter = _find_parent_chapter(section, index)
    
    # Build text output
    lines = []
    lines.append(f"Section: {section['title']} (pages {section['start_page']}-{section['end_page']})")
    
    if parent_chapter:
        lines.append(f"Parent Chapter: {parent_chapter['title']} (pages {parent_chapter['start_page']}-{parent_chapter['end_page']})")
    
    return "\n".join(lines)


def _find_chapter(chapter_id: Union[str, int], index: Dict) -> Optional[Dict]:
    """Find chapter by number or name (fuzzy matching). Prioritizes CHAPTER over PART."""
    chapters = index['chapters']
    
    # If searching by number, prioritize "CHAPTER X" over "PART X"
    if isinstance(chapter_id, int) or (isinstance(chapter_id, str) and chapter_id.isdigit()):
        chapter_num = str(chapter_id)
        
        # First: Look for "CHAPTER X" specifically
        for chapter in chapters:
            title_lower = chapter['title'].lower()
            if re.search(rf'\bchapter\s+{chapter_num}\b', title_lower):
                return chapter
        
        # Second: Look for exact number match (catches PART if no CHAPTER found)
        for chapter in chapters:
            if chapter.get('number') == chapter_num:
                return chapter
    
    # Try name matching with improved fuzzy matching
    query = str(chapter_id).lower().strip()
    
    # Skip if query is too short
    if len(query) < 4:
        return None
    
    # Exact match first
    for chapter in chapters:
        if query == chapter['title'].lower().strip():
            return chapter
    
    # Partial match - require at least 60% of query words to be in title
    query_words = set(query.split())
    best_match = None
    best_score = 0
    
    for chapter in chapters:
        title_lower = chapter['title'].lower()
        title_words = set(title_lower.split())
        
        # Count matching words
        matching_words = query_words & title_words
        if len(matching_words) == 0:
            continue
        
        # Calculate match score
        score = len(matching_words) / len(query_words)
        
        # Bonus if title contains the full query as substring
        if query in title_lower:
            score += 0.3
        
        if score > best_score and score >= 0.6:  # Require 60% match
            best_score = score
            best_match = chapter
    
    return best_match


def _find_section(section_id: Union[str, int], index: Dict) -> Optional[Dict]:
    """Find section by number or name with improved fuzzy matching."""
    sections = index['sections']
    section_str = str(section_id)
    
    # Method 1: Exact number match (e.g., "1-2", "1.2")
    if section_str in index['by_number']:
        return index['by_number'][section_str]
    
    for section in sections:
        if section.get('number') == section_str:
            return section
    
    # Method 2: Name matching - require substantial overlap
    query = section_str.lower().strip()
    
    # Skip if query is too short (avoid matching single words like "the")
    if len(query) < 4:
        return None
    
    # Exact match first
    for section in sections:
        if query == section['title'].lower().strip():
            return section
    
    # Partial match - require at least 60% of query words to be in title
    query_words = set(query.split())
    best_match = None
    best_score = 0
    
    for section in sections:
        title_lower = section['title'].lower()
        title_words = set(title_lower.split())
        
        # Count matching words
        matching_words = query_words & title_words
        if len(matching_words) == 0:
            continue
        
        # Calculate match score (percentage of query words found)
        score = len(matching_words) / len(query_words)
        
        # Bonus if title contains the full query as substring
        if query in title_lower:
            score += 0.3
        
        if score > best_score and score >= 0.6:  # Require 60% match
            best_score = score
            best_match = section
    
    return best_match


def _find_sections_in_chapter(chapter: Dict, index: Dict) -> List[Dict]:
    """Find all sections that belong to a chapter."""
    sections = []
    chapter_start = chapter['start_page']
    chapter_end = chapter['end_page']
    
    for section in index['sections']:
        # Section belongs to chapter if it's within chapter's page range
        if chapter_start <= section['start_page'] <= chapter_end:
            sections.append(section)
    
    return sorted(sections, key=lambda x: x['start_page'])


def _handle_multiple_chapters_query(chapter_ids: List[str], index: Dict, doc) -> str:
    """Handle query for multiple chapters."""
    chapters = []
    not_found = []
    
    for chapter_id in chapter_ids:
        chapter = _find_chapter(chapter_id, index)
        if chapter:
            chapters.append(chapter)
        else:
            not_found.append(chapter_id)
    
    if not chapters:
        return f"No chapters found for: {', '.join(chapter_ids)}\n\n" + _handle_all_content_query(index, doc)
    
    # Sort by start page
    chapters_sorted = sorted(chapters, key=lambda x: x['start_page'])
    
    # Count total sections across all chapters
    total_sections = 0
    all_sections = []
    for ch in chapters_sorted:
        sections = _find_sections_in_chapter(ch, index)
        total_sections += len(sections)
        all_sections.extend(sections)
    
    # Build text output
    lines = []
    
    # Summary header with counts
    if len(chapter_ids) > 1:
        range_desc = f"Chapters {chapter_ids[0]}-{chapter_ids[-1]}" if len(chapter_ids) > 2 else f"Chapters {', '.join(chapter_ids)}"
        start_page = chapters_sorted[0]['start_page']
        end_page = chapters_sorted[-1]['end_page']
        lines.append(f"{range_desc} (pages {start_page}-{end_page}):")
        lines.append(f"Total: {len(chapters_sorted)} chapters, {total_sections} sections\n")
    
    # List each chapter with sections
    for i, ch in enumerate(chapters_sorted):
        # Find sections within this chapter
        sections = _find_sections_in_chapter(ch, index)
        
        lines.append(f"Chapter {ch.get('number', '?')}: {ch['title']} (pages {ch['start_page']}-{ch['end_page']})")
        
        if sections:
            lines.append(f"  Sections ({len(sections)}):")
            for s in sections:
                lines.append(f"    {s['title']} (pages {s['start_page']}-{s['end_page']})")
        else:
            lines.append("  Sections (0)")
        
        # Add blank line between chapters (except last)
        if i < len(chapters_sorted) - 1:
            lines.append("")
    
    if not_found:
        lines.append(f"\nNote: Not found: {', '.join(not_found)}")
    
    return "\n".join(lines)


def _handle_multiple_sections_query(section_ids: List[str], index: Dict, doc) -> str:
    """Handle query for multiple sections."""
    sections = []
    not_found = []
    
    for section_id in section_ids:
        section = _find_section(section_id, index)
        if section:
            sections.append(section)
        else:
            not_found.append(section_id)
    
    if not sections:
        return f"No sections found for: {', '.join(section_ids)}"
    
    # Sort by start page
    sections_sorted = sorted(sections, key=lambda x: x['start_page'])
    
    # Build text output
    lines = []
    
    # Summary header - make it clear these are specific sections, not a range
    start_page = sections_sorted[0]['start_page']
    end_page = sections_sorted[-1]['end_page']
    lines.append(f"Found {len(sections_sorted)} section(s) (pages {start_page}-{end_page}):\n")
    
    # Find parent chapters (might be different for each section)
    parent_chapters = {}
    for s in sections_sorted:
        parent = _find_parent_chapter(s, index)
        if parent:
            parent_chapters[parent['title']] = parent
    
    if parent_chapters:
        if len(parent_chapters) == 1:
            parent = list(parent_chapters.values())[0]
            lines.append(f"Parent Chapter: {parent['title']} (pages {parent['start_page']}-{parent['end_page']})\n")
        else:
            lines.append(f"Parent Chapters: {len(parent_chapters)} chapters\n")
    
    # List each section with its details
    for i, s in enumerate(sections_sorted):
        parent = _find_parent_chapter(s, index)
        parent_info = f" [from {parent['title']}]" if parent and len(parent_chapters) > 1 else ""
        lines.append(f"Section: {s['title']}{parent_info} (pages {s['start_page']}-{s['end_page']})")
    
    if not_found:
        lines.append(f"\nNote: Sections not found: {', '.join(not_found)}")
    
    return "\n".join(lines)


def _find_parent_chapter(section: Dict, index: Dict) -> Optional[Dict]:
    """Auto-detect parent chapter from section's page location or number. Prioritizes CHAPTER over PART."""
    # Method 1: Extract chapter number from section number (e.g., "1-2" → chapter 1)
    section_num = section.get('number')
    if section_num and ('-' in section_num or '.' in section_num):
        # Extract chapter number (before - or .)
        chapter_num = section_num.split('-')[0] if '-' in section_num else section_num.split('.')[0]
        
        # Prioritize "CHAPTER X" over "PART X"
        for chapter in index['chapters']:
            title_lower = chapter['title'].lower()
            if chapter.get('number') == chapter_num and 'chapter' in title_lower:
                return chapter
        
        # Fallback to any chapter with matching number
        for chapter in index['chapters']:
            if chapter.get('number') == chapter_num:
                return chapter
    
    # Method 2: Find most specific (smallest page range) chapter containing this section
    section_start = section['start_page']
    matching_chapters = []
    
    for chapter in index['chapters']:
        if chapter['start_page'] <= section_start <= chapter['end_page']:
            matching_chapters.append(chapter)
    
    if matching_chapters:
        # Sort by page count (ascending) to get most specific chapter
        matching_chapters.sort(key=lambda x: x['page_count'])
        return matching_chapters[0]
    
    return None


# ============================================================================
# CLI for testing
# ============================================================================

def main():
    """Command-line interface for testing."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python pdf_content_navigator.py <pdf_path> [chapter=N] [section=N]")
        print("\nExamples:")
        print("  python pdf_content_navigator.py book.pdf")
        print("  python pdf_content_navigator.py book.pdf chapter=1")
        print("  python pdf_content_navigator.py book.pdf section=1.2")
        print("  python pdf_content_navigator.py book.pdf chapter=Introduction")
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    chapter = "all"
    section = "all"
    
    # Parse arguments
    for arg in sys.argv[2:]:
        if arg.startswith("chapter="):
            chapter = arg.split("=", 1)[1]
            # Convert to int if numeric
            if chapter.isdigit():
                chapter = int(chapter)
        elif arg.startswith("section="):
            section = arg.split("=", 1)[1]
    
    # Execute query
    result = get_pdf_content_range(pdf_path, chapter=chapter, section=section)
    
    # Print result
    print("\n" + "="*80)
    print("PDF Content Navigator - Result")
    print("="*80)
    print(result)
    print("="*80 + "\n")


if __name__ == "__main__":
    main()

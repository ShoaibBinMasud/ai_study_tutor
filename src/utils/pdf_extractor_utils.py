"""
PDF Extractor Utilities
=======================
Shared utility classes for PDF extraction.

This module contains common components used by both page-level and section-aware extractors:
- TokenCounter: Handle token counting with tiktoken or fallback
- FontAnalyzer: Analyze document-wide font statistics
- PageProcessor: Process individual pages and extract structured content
"""

import fitz  # PyMuPDF
import re
from typing import Dict, List, Optional
import logging

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

logger = logging.getLogger(__name__)

# Log tiktoken status once at module load, not on every TokenCounter instantiation
if not TIKTOKEN_AVAILABLE:
    logger.debug("tiktoken not available, using word-based token approximation")


class TokenCounter:
    """Handle token counting with tiktoken or fallback"""
    def __init__(self):
        self.encoding = None
        if TIKTOKEN_AVAILABLE:
            try:
                self.encoding = tiktoken.get_encoding("cl100k_base")
            except Exception:
                pass  # Silently fall back to word-based
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        if self.encoding:
            try:
                return len(self.encoding.encode(text))
            except:
                pass
        # Fallback: 1 token ≈ 0.75 words
        return int(len(text.split()) / 0.75)


class FontAnalyzer:
    """Analyze document-wide font statistics"""
    
    def __init__(self, doc: fitz.Document):
        self.doc = doc
        self.body_size = 10.0
        self.header_sizes = {}
        
    def analyze(self, sample_pages: int = 20) -> Dict:
        """Analyze font sizes across document and calculate adaptive thresholds"""
        from collections import Counter
        font_sizes = []
        
        # Sample pages
        total_pages = len(self.doc)
        step = max(1, total_pages // sample_pages)
        
        for page_num in range(0, total_pages, step):
            page = self.doc[page_num]
            blocks = page.get_text("dict")["blocks"]
            
            for block in blocks:
                if block.get("type") == 0:  # Text block
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            size = span.get("size", 0)
                            if 8 <= size <= 40:  # Reasonable range
                                font_sizes.append(round(size, 1))
        
        if not font_sizes:
            return {
                "body_size": 10.0,
                "header_threshold": 12.0,
                "section_min": 12.0,
                "section_max": 20.0,
                "chapter_min": 20.0
            }
        
        # Find body text size (most common font size)
        size_counts = Counter(font_sizes)
        body_size = size_counts.most_common(1)[0][0]
        self.body_size = body_size
        
        # Adaptive thresholds based on document's actual fonts
        # Section headers: typically 1.3-2.2x body size (with numbers like "1.1" or "1-1")
        section_min = body_size * 1.3
        section_max = body_size * 2.2
        
        # Chapter headers: typically 2.2x+ body size
        chapter_min = body_size * 2.2
        
        # Subsection: slightly larger than body (1.1-1.6x) - allows overlap with sections
        # Distinction: sections have numbers, subsections are plain bold text
        subsection_min = body_size * 1.1
        subsection_max = body_size * 1.6  # More generous to catch borderline cases
        
        # Header threshold (for general detection)
        header_threshold = body_size * 1.2
        
        logger.info(f"📊 Adaptive Font Analysis:")
        logger.info(f"  Body text: {body_size:.1f}pt")
        logger.info(f"  Subsections: {subsection_min:.1f}-{subsection_max:.1f}pt")
        logger.info(f"  Sections: {section_min:.1f}-{section_max:.1f}pt")
        logger.info(f"  Chapters: {chapter_min:.1f}pt+")
        
        return {
            "body_size": body_size,
            "header_threshold": header_threshold,
            "section_min": section_min,
            "section_max": section_max,
            "chapter_min": chapter_min,
            "subsection_min": subsection_min,
            "subsection_max": subsection_max
        }


class PageProcessor:
    """Process a single page and extract structured content"""
    
    # Detection patterns
    CHAPTER_PATTERNS = [
        r'^CHAPTER\s*(\d+)',  # Must be at start (^), \s* allows "CHAPTER4" or "CHAPTER 4"
        r'^Chapter\s*(\d+)',  # Must be at start (^), \s* allows "Chapter4" or "Chapter 4"
    ]
    
    # Special sections that should reset chapter/section context
    SPECIAL_SECTION_PATTERNS = [
        r'^(APPENDIX|Appendix)\s*([A-Z])?',  # Appendix A, Appendix B, etc.
        r'^(BIBLIOGRAPHY|Bibliography)\s*$',
        r'^(REFERENCES|References)\s*$',
        r'^(INDEX|Index)\s*$',
        r'^(GLOSSARY|Glossary)\s*$',
        r'^(ANSWERS?|Answers?)\s+(to|TO)\s+(PROBLEMS?|Problems?|QUESTIONS?|Questions?)',  # Answers to Problems
        r'^(SOLUTIONS?|Solutions?)\s+(to|TO)\s+(PROBLEMS?|Problems?|EXERCISES?|Exercises?)',  # "Solutions to Problems" only
    ]
    
    SECTION_PATTERNS = [
        r'^(\d+[-.][\d]{1,2})\s+(.+)',  # "1-1 Title" or "1.1 Title" (strict: 1-2 digits after separator)
        r'^(\d+)\s+([A-Z][a-zA-Z\s\-]+)$',  # "1 Introduction" or "2 Pre-training"
    ]
    
    SUBSECTION_PATTERNS = [
        # Subsections are usually short, bold titles without numbers
        # Examples: "Classical Relativity", "Speed of Light", "The Lorentz Transformation"
        r'^(\d+[-.][\d]{1,2}[-.][\d]{1,2})\s+(.+)',  # "1.1.1 Title" or "1-1-1 Title"
        r'^([A-Z])\.\s+(.+)',  # "A. Title" or "B. Title"
    ]
    
    EXAMPLE_PATTERNS = [
        r'EXAMPLE\s+(\d+[-.][\.\d]*)',
        r'Example\s+(\d+[-.][\.\d]*)',
    ]
    
    PRACTICE_PATTERNS = [
        r'(?:Practice\s+)?(?:Problems|Questions)',
        r'End[- ]of[- ]Chapter',
    ]
    
    def __init__(self, doc: fitz.Document, font_info: Dict):
        self.doc = doc
        self.body_size = font_info["body_size"]
        self.header_threshold = font_info["header_threshold"]
        # Adaptive thresholds
        self.section_min = font_info.get("section_min", 12.0)
        self.section_max = font_info.get("section_max", 20.0)
        self.chapter_min = font_info.get("chapter_min", 20.0)
        self.subsection_min = font_info.get("subsection_min", 13.0)
        self.subsection_max = font_info.get("subsection_max", 16.0)
    
    def process_page(self, page_num: int, current_section: Optional[Dict] = None, current_subsection: Optional[Dict] = None) -> Dict:
        """
        Process a single page and return structured data.
        
        Args:
            page_num: Page index (0-based)
            current_section: Current section context from previous pages
            current_subsection: Current subsection context from previous pages
        
        Returns:
            {
                "detected_chapter": {...} or None,
                "detected_section": {...} or None,
                "detected_subsection": {...} or None,
                "text_blocks": [{"text": "...", "is_example": bool, ...}]
            }
        """
        page = self.doc[page_num]
        blocks = page.get_text("dict")["blocks"]
        
        result = {
            "page_num": page_num,
            "detected_chapter": None,
            "detected_section": None,
            "detected_subsection": None,
            "detected_special_section": None,
            "text_blocks": []
        }
        
        current_block_text = []
        current_block_info = {"is_header": False, "font_size": self.body_size}
        
        # Track current section/subsection for tagging text blocks (inherit from previous pages)
        current_section_info = current_section
        current_subsection_info = current_subsection
        
        # Track recent large-font lines for backward title reference
        # Some PDFs have title BEFORE chapter marker (e.g., "The Nuclear Atom" then "CHAPTER4")
        recent_large_text = []  # List of (text, font_size, is_bold)
        
        for block in blocks:
            if block.get("type") != 0:  # Not text
                continue
            
            for line in block.get("lines", []):
                line_text = ""
                line_size = self.body_size
                is_bold = False
                
                # Extract line info
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if text:
                        line_text += text + " "
                        line_size = max(line_size, span.get("size", self.body_size))
                        flags = span.get("flags", 0)
                        is_bold = is_bold or (flags & 2 ** 4)  # Bold flag
                
                line_text = line_text.strip()
                if not line_text:
                    continue
                
                # Check if this is a header
                is_header = (line_size >= self.header_threshold or is_bold) and len(line_text) < 200
                
                # Track large-font lines for backward title reference (before chapter detection)
                # This handles PDFs where title appears BEFORE chapter marker (e.g., Modern Physics)
                # Only track if it's in title size range (not too large, not too small)
                if (self.section_min <= line_size <= 50 and  # Reasonable title font range
                    len(line_text) > 5 and len(line_text) < 100 and
                    not re.match(r'^\d+(\s+\d+)?$', line_text)):  # Not just a number
                    # Keep only recent 3 lines (minimize false matches)
                    recent_large_text.append((line_text, line_size, is_bold))
                    if len(recent_large_text) > 3:
                        recent_large_text.pop(0)
                
                # **SPECIAL CASE**: Nelson Physics style - "chapter" label after title
                # E.g., "Kinematics" (32pt bold) then "chapter" (18pt)
                # Check if this is the word "chapter" without a number
                if (line_text.lower() == 'chapter' and 
                    self.section_min <= line_size < self.chapter_min and
                    recent_large_text):
                    # Look for a large bold title in recent text
                    for prev_text, prev_size, prev_bold in reversed(recent_large_text):
                        if (prev_bold and prev_size >= self.chapter_min * 0.9 and
                            len(prev_text) > 5 and len(prev_text) < 100):
                            # Found a title! This is likely a Nelson-style chapter
                            # Infer chapter number from sequence (will be validated later)
                            # For now, use a placeholder that will trigger collection
                            result["detected_chapter"] = {
                                "number": "INFER",  # Will be set by parent based on sequence
                                "title": prev_text
                            }
                            result["_collecting_chapter_title"] = False  # Already have title
                            result["_chapter_title_parts"] = []
                            continue
                
                # Detect chapter (pass font size for better detection)
                chapter_match = self._detect_chapter(line_text, line_size)
                if chapter_match:
                    # If chapter title is just the number OR generic chapter label (e.g., "CHAPTER 4", "Chapter 1"), 
                    # we'll collect the actual title from subsequent large-font lines OR use backward reference
                    result["detected_chapter"] = chapter_match
                    
                    # Check if we should collect/find the real title:
                    # 1. Title equals number (e.g., "4" == "4") - bare number on its own
                    # 2. Title is generic "CHAPTER X" or "Chapter X" format
                    is_bare_number = (chapter_match['title'] == chapter_match['number'])
                    is_generic_label = bool(re.match(rf'^(CHAPTER|Chapter)\s*{chapter_match["number"]}$', 
                                                     chapter_match['title']))
                    
                    # Try backward reference first (title appeared BEFORE chapter marker)
                    if (is_bare_number or is_generic_label) and recent_large_text:
                        # Look for a good title candidate in recent large text
                        # Skip the current line itself and look at previous ones
                        for prev_text, prev_size, prev_bold in reversed(recent_large_text[:-1]):
                            # Good title candidate: not a number, reasonable length, large font
                            if (prev_size >= self.section_min and 
                                not re.match(r'^\d+(\s+\d+)?$', prev_text) and
                                not prev_text.lower() in ['chapter', 'unit'] and
                                5 < len(prev_text) < 100):
                                # Found a backward title!
                                result["detected_chapter"]["title"] = prev_text
                                result["_collecting_chapter_title"] = False  # Don't collect forward
                                result["_chapter_title_parts"] = []
                                break
                        else:
                            # No backward title found, collect forward
                            result["_collecting_chapter_title"] = True
                            result["_chapter_title_parts"] = []
                    else:
                        # Not generic, use title as-is
                        result["_collecting_chapter_title"] = False
                        result["_chapter_title_parts"] = []
                    
                    continue
                
                # If collecting chapter title, check if this is part of it
                if result.get("_collecting_chapter_title"):
                    # Collect lines with large font (chapter or section sized) as title
                    # But stop at common intro text patterns
                    skip_patterns = ['in this chapter', 'you will be able to', 'by the end']
                    should_skip = any(pattern in line_text.lower() for pattern in skip_patterns)
                    
                    if (line_size >= self.section_min and 
                        len(line_text) > 5 and
                        line_text.lower() not in ['chapter', 'unit'] and
                        not line_text.startswith('•') and
                        not line_text.startswith('�') and
                        not should_skip and
                        not re.match(r'^\d+(\s+\d+)?$', line_text)):  # Not just number like "11" or "1 1"
                        
                        result["_chapter_title_parts"].append(line_text)
                        
                        # Stop collecting if we hit section-sized text (title is complete)
                        if line_size < self.chapter_min:
                            result["_collecting_chapter_title"] = False
                        continue
                    elif should_skip:
                        # Stop collecting - we've hit intro text
                        result["_collecting_chapter_title"] = False
                        # Don't continue, let this line be processed normally
                
                # Detect special sections (Appendix, Bibliography, etc.)
                # Do this AFTER chapter detection to avoid suppressing chapter titles containing words like "Solutions"
                special_match = self._detect_special_section(line_text, line_size)
                if special_match:
                    result["detected_special_section"] = special_match
                    # Don't continue - let chapter/section detection also run
                    # to handle cases like "APPENDIX A" which might also look like a chapter
                
                # Detect section (pass font size and bold status for better detection)
                section_match = self._detect_section(line_text, line_size, is_bold)
                if section_match:
                    # Save previous block with its section metadata
                    if current_block_text:
                        # Join text preserving newline markers
                        text_parts = []
                        for i, part in enumerate(current_block_text):
                            if part.endswith("\n") or part.startswith("\n\n"):
                                # This has newline marker
                                text_parts.append(part if i == 0 else part)
                            else:
                                # Regular text - add space before if not first part
                                text_parts.append(part if i == 0 else " " + part)
                        
                        result["text_blocks"].append({
                            "text": "".join(text_parts),
                            "is_header": current_block_info["is_header"],
                            "font_size": current_block_info.get("font_size", 0),
                            "section": current_section_info,
                            "subsection": current_subsection_info
                        })
                        current_block_text = []
                    
                    result["detected_section"] = section_match
                    current_section_info = section_match  # Track for text blocks
                    current_subsection_info = None  # Reset subsection
                    current_block_info = {"is_header": True, "font_size": line_size, "collecting_title": section_match.get("title") is None}
                    continue
                
                # If we're collecting a section title (multi-line header), append to existing section
                if result["detected_section"] and current_block_info.get("collecting_title"):
                    # This line should be the section title (12-30pt range to handle different styles including chapter-sized titles)
                    # Accept if: similar size to section number OR reasonable title size OR chapter-sized title
                    prev_size = current_block_info.get("font_size", line_size)
                    
                    # Check if this looks like a title
                    is_title_size = (
                        (abs(line_size - prev_size) < 5) or  # Similar to section number (relaxed from 3 to 5)
                        (12 <= line_size <= 30)              # Reasonable title range (includes chapter-sized)
                    )
                    
                    # Relax bold requirement: Allow non-bold if font is large (section-sized or larger)
                    # Many PDFs use large non-bold fonts for section titles
                    needs_bold = line_size < self.section_min  # Only require bold if font is small
                    meets_bold_req = (not needs_bold) or is_bold
                    
                    # Additional checks: not body text, reasonable length
                    is_body_text = line_size < self.section_min * 0.9  # Clearly body text
                    is_reasonable_length = 5 < len(line_text) < 100
                    
                    if is_title_size and meets_bold_req and is_reasonable_length and not is_body_text:
                        # Append to existing section title
                        if result["detected_section"]["title"]:
                            result["detected_section"]["title"] += " " + line_text
                        else:
                            result["detected_section"]["title"] = line_text
                        # Also update current_section_info
                        current_section_info = result["detected_section"]
                        # Keep collecting if this line was large (multi-line title)
                        # Stop if next line is body text or we've collected enough
                        continue
                    else:
                        # Done collecting title
                        current_block_info["collecting_title"] = False
                
                # Detect subsection-like headers (bold/large font, short text)
                # Subsections are adaptive: typically 1.1-1.3x body size (e.g., 12-15pt for 10pt body)
                # Examples: "Speed of Light", "Classical Relativity", "Questions", "Problems", "Functions", "Modeling"
                is_subsection_font = self.subsection_min <= line_size < self.subsection_max
                if is_subsection_font and len(line_text) < 100:
                    # Filter out equations, figure captions, and very short text
                    # Count only letters (not spaces) to filter out equations like "F = m a"
                    letter_count = sum(c.isalpha() for c in line_text)
                    word_count = len(line_text.split())
                    
                    # Subsection must be:
                    # - Short (< 60 chars or <= 8 words)
                    # - Mostly letters (>60%)
                    # - Start with capital letter or common header words
                    # - Not a figure/table caption or footer
                    if (len(line_text) > 5 and len(line_text) < 60 and word_count <= 8 and 
                        letter_count / len(line_text) > 0.6):
                        # Skip figure/table captions and footers
                        footer_patterns = [
                            r'access for free',
                            r'copyright',
                            r'all rights reserved',
                            r'page \d+',
                            r'chapter \d+$',
                            r'^\d+$',  # Just a page number
                            r'openstax',
                            r'©',
                        ]
                        is_footer = any(re.search(pattern, line_text, re.I) for pattern in footer_patterns)
                        
                        if not re.match(r'^(Figure|Table|Equation|Fig\.)', line_text, re.I) and not is_footer:
                            # Must start with capital letter or header word
                            if line_text[0].isupper() or re.match(r'^(Questions|Problems|Summary|Example|Solution)', line_text, re.I):
                                # This looks like a subsection header - save it
                                # Save previous block first
                                if current_block_text:
                                    result["text_blocks"].append({
                                        "text": " ".join(current_block_text) if not any(p.startswith("\n") for p in current_block_text) else "".join(current_block_text),
                                        "is_header": False,
                                        "font_size": current_block_info.get("font_size", 0),
                                        "section": current_section_info,
                                        "subsection": current_subsection_info
                                    })
                                    current_block_text = []
                                
                                # Truncate to first 4 words if too long
                                subsection_title = line_text
                                if word_count > 4:
                                    subsection_title = " ".join(line_text.split()[:4])
                                
                                # Mark this as a detected subsection
                                current_subsection_info = {
                                    "title": subsection_title,
                                    "number": None
                                }
                                result["detected_subsection"] = current_subsection_info
                                # Don't add the subsection title to the block text
                                continue
                    
                    # If not a subsection, add with newlines for structure
                    if current_block_text:
                        current_block_text.append("\n\n" + line_text + "\n")
                    else:
                        current_block_text.append(line_text + "\n")
                else:
                    # Regular text - accumulate with newline to preserve line structure
                    current_block_text.append(line_text + "\n")
        
        # Add final block
        if current_block_text:
            # Join text preserving newline markers
            text_parts = []
            for i, part in enumerate(current_block_text):
                if part.startswith("\n\n") or (i > 0 and current_block_text[i-1].endswith("\n")):
                    # This has newline prefix or previous part ended with newline
                    text_parts.append(part)  # Keep as-is, no extra space
                else:
                    # Regular text - add space before if not first part
                    if i > 0:
                        text_parts.append(" " + part)
                    else:
                        text_parts.append(part)
            
            text = "".join(text_parts)
            
            # Split examples into separate blocks (with section metadata)
            blocks_to_add = self._split_examples_from_text(text, current_section_info, current_subsection_info)
            result["text_blocks"].extend(blocks_to_add)
        
        # Finalize chapter title if we collected parts
        if result.get("_chapter_title_parts"):
            title_parts = result["_chapter_title_parts"]
            if title_parts:
                # Remove duplicates while preserving order (sometimes title appears twice)
                seen = set()
                unique_parts = []
                for part in title_parts:
                    if part not in seen:
                        seen.add(part)
                        unique_parts.append(part)
                result["detected_chapter"]["title"] = ' '.join(unique_parts)
        
        # Clean up temp fields
        result.pop("_collecting_chapter_title", None)
        result.pop("_chapter_title_parts", None)
        
        return result
    
    def _detect_chapter(self, text: str, font_size: float) -> Optional[Dict]:
        """Detect chapter header - uses adaptive thresholds from document analysis"""
        # Chapters use the largest fonts (adaptive threshold)
        is_large_font = font_size >= self.chapter_min
        
        # CRITICAL: Reject fonts that are TOO LARGE (decorative page numbers like "11" at 138pt)
        # These are typically decorative chapter displays, not semantic chapter markers
        is_decorative = font_size > 60  # Anything >60pt is likely decorative, not a real chapter marker
        
        # Try pattern matching first
        # Use re.match (start of text) to prevent body text false positives
        # For explicit patterns like "CHAPTER 1", be more lenient with font size
        for pattern in self.CHAPTER_PATTERNS:
            match = re.match(pattern, text, re.I)
            if match:
                chapter_num = match.group(1) if match.lastindex else None
                
                # VALIDATION LEVELS:
                # 1. Standard: font >= chapter_min (strict, preferred)
                # 2. Relaxed: 14pt <= font < chapter_min (for PDFs with smaller chapter labels)
                # 3. Reject: font < 14pt (footers, headers, TOC entries)
                
                is_standard = font_size >= self.chapter_min
                is_relaxed_acceptable = 14 <= font_size < self.chapter_min
                
                # DEBUG: Log when relaxed validation is used
                if is_relaxed_acceptable and not is_standard:
                    logger.info(f"Using relaxed validation for chapter pattern '{text}' at {font_size:.1f}pt (chapter_min={self.chapter_min:.1f}pt)")
                
                if is_standard or is_relaxed_acceptable:
                    # Try to extract title
                    title = text
                    if chapter_num:
                        # Remove the chapter number part to get title
                        title = re.sub(rf'^chapter\s*{chapter_num}[:\s]*', '', text, flags=re.I).strip()
                    
                    return {
                        "number": chapter_num,
                        "title": title if title else text
                    }
        
        # If no pattern match but very large font and looks like a chapter
        # Look for formats like "1 | Title", "Chapter 1", or just numbered headings
        if is_large_font:
            # Skip section numbers like "1.1" or "1-1" (these are sections, not chapters)
            if re.match(r'^\d+[.-]\d+$', text):
                return None
            
            # Format: "1 | FUNCTIONS AND GRAPHS"
            pipe_match = re.match(r'^(\d+)\s*\|\s*(.+)$', text, re.I)
            if pipe_match:
                num = pipe_match.group(1)
                title = pipe_match.group(2).strip()
                return {
                    "number": num,
                    "title": f"{num} | {title}"  # Keep original format
                }
            
            # Format: Just starts with a number and text (relaxed)
            num_match = re.match(r'^(\d+)[\s\.:\-]+(.+)$', text)
            if num_match and len(text) < 100:
                return {
                    "number": num_match.group(1),
                    "title": num_match.group(2).strip()
                }
            
            # Format: Standalone chapter number (e.g., "11" or "1 1" in huge font)
            # This handles Nelson Physics style where number is on its own line
            # BUT reject if TOO LARGE (decorative) or TOO SMALL (page numbers)
            bare_num_match = re.match(r'^(\d+)(\s+\d+)?$', text)  # Matches "11" or "1 1"
            if bare_num_match and not is_decorative:
                # Also reject if font is too small for a chapter (likely a page number)
                if font_size >= self.section_min:  # Must be at least section-sized
                    return {
                        "number": bare_num_match.group(1),
                        "title": bare_num_match.group(1)  # Title will be collected from next blocks
                    }
        
        return None
    
    def _detect_special_section(self, text: str, font_size: float) -> Optional[Dict]:
        """Detect special sections like Appendix, Bibliography, Answers, etc."""
        # Special sections typically have larger font (but not necessarily chapter-level)
        is_header_font = font_size >= self.section_min
        
        if not is_header_font:
            return None
        
        for pattern in self.SPECIAL_SECTION_PATTERNS:
            match = re.match(pattern, text, re.I)
            if match:
                return {
                    "type": "special",
                    "title": text.strip(),
                    "category": match.group(1).upper() if match.lastindex else text.strip().upper()
                }
        
        return None
    
    def _detect_section(self, text: str, font_size: float, is_bold: bool = False) -> Optional[Dict]:
        """Detect section header - now prioritizes font size over patterns"""
        # Sections are typically 12-19pt (smaller than chapters 20+)
        # Can also be larger (20-30pt) in some textbooks
        # Lowered to 11.9pt to handle floating point precision (kimi-k2 reports 11.9552pt for 12pt fonts)
        is_section_font = 11.9 <= font_size < 35
        
        # CRITICAL: Reject body text (typically 9-11pt) to avoid false positives
        # Allow 11.9-13pt ONLY if BOLD and matches section pattern
        if font_size < 11.9:
            return None
        
        # For 12-14pt text, require bold AND strong section pattern match
        if font_size < 14:
            if not is_bold:
                return None
            # Also require section pattern match (allow lowercase for scientific notation like "sp3")
            # Accept: "1.1 Title", "1-1 Title", or standalone "1", "2", etc.
            # Limit to 1-2 digits after dot/hyphen to avoid matching equation numbers like "1.055"
            has_section_pattern = bool(re.match(r'^(\d+[\.\-]\d{1,2}|\d+)(\s|$)', text))
            if not has_section_pattern:
                return None
        
        # Try pattern matching first
        for pattern in self.SECTION_PATTERNS:
            match = re.match(pattern, text)
            if match:
                # Only accept if font size confirms this is a section
                # Reject patterns with too many levels (e.g., "1.1.7")
                number = match.group(1)
                if number.count('.') > 1:
                    continue
                    
                # Check if we have a title or just a number
                if len(match.groups()) >= 2:
                    title = match.group(2).strip()
                    # Additional checks:
                    # 1. Title should not be too long (body text sentences)
                    if len(title) > 100:
                        continue
                    # 2. Title should start with a letter (not symbols like "#", ">", etc.)
                    if title and not title[0].isalpha():
                        continue
                    # 3. Reject calculation-like text (contains "=", multiple "#", ">", etc.)
                    # These are equations/calculations, not section titles
                    calc_indicators = ['=', '×', '÷', ' # ', ' > ', ' < ', '≈', '≠']
                    if title and any(indicator in title for indicator in calc_indicators):
                        continue
                    # 4. Reject if too many special chars (calculations have lots of symbols)
                    if title:
                        special_char_count = sum(1 for c in title if not (c.isalnum() or c.isspace() or c in ',-.:()'))
                        if special_char_count > len(title) * 0.3:  # More than 30% special chars
                            continue
                else:
                    title = None  # No title yet, will be collected from next line
                    
                return {
                    "number": number,
                    "title": title
                }
        
        # Font-based detection for sections without strict patterns
        if is_section_font:
            # Format: "1.1 | Title" or "Introduction"
            pipe_match = re.match(r'^(\d+\.\d{1,2})\s*\|\s*(.+)$', text)
            if pipe_match:
                title = pipe_match.group(2).strip()
                # Reject calculation-like text
                calc_indicators = ['=', '×', '÷', ' # ', ' > ', ' < ', '≈', '≠']
                if any(indicator in title for indicator in calc_indicators):
                    return None
                return {
                    "number": pipe_match.group(1),
                    "title": title
                }
            
            # Format: "1.1 Title" (number with single dot, then title - limit to 1-2 digits)
            num_match = re.match(r'^(\d+\.\d{1,2})\s+(.+)$', text)
            if num_match and len(text) < 100:
                title = num_match.group(2).strip()
                # Ensure title starts with a letter
                if title and title[0].isalpha():
                    # Reject calculation-like text
                    calc_indicators = ['=', '×', '÷', ' # ', ' > ', ' < ', '≈', '≠']
                    if any(indicator in title for indicator in calc_indicators):
                        return None
                    # Reject if too many special chars
                    special_char_count = sum(1 for c in title if not (c.isalnum() or c.isspace() or c in ',-.:()'))
                    if special_char_count > len(title) * 0.3:
                        return None
                    return {
                        "number": num_match.group(1),
                        "title": title
                    }
            
            # Format: Standalone number like "1", "2", "3" (multi-line section header)
            standalone_num = re.match(r'^(\d+)$', text)
            if standalone_num and is_bold:
                return {
                    "number": standalone_num.group(1),
                    "title": None  # Title will be on next line
                }
            
            # Format: Just a word like "Introduction" (common section header)
            if re.match(r'^(Introduction|Conclusion|Summary|Overview)$', text, re.I):
                return {
                    "number": None,
                    "title": text
                }
        
        # Detect standalone section numbers (for multi-line section headers)
        # e.g., "1.1" on one line, then title on next line(s)
        if font_size >= 20:  # Large font for section number
            standalone_num = re.match(r'^(\d+[.-]\d{1,2})$', text)
            if standalone_num:
                return {
                    "number": standalone_num.group(1),
                    "title": None  # Title will be collected from next line
                }
        
        return None
    
    def _split_examples_from_text(self, text: str, section_info=None, subsection_info=None) -> List[Dict]:
        """Split text into separate blocks if it contains examples"""
        blocks = []
        
        # Look for EXAMPLE pattern
        example_pattern = r'(EXAMPLE\s+\d+[-.][\.\d]*[^\n]*(?:\n|$)(?:.*?)(?=EXAMPLE\s+\d+|$))'
        
        # Try to find examples
        matches = list(re.finditer(r'EXAMPLE\s+(\d+[-.][\.\d]*)', text, re.I))
        
        if not matches:
            # No examples, check for practice questions
            for pattern in self.PRACTICE_PATTERNS:
                if re.search(pattern, text[:200], re.I):
                    return [{
                        "text": text,
                        "is_header": False,
                        "is_example": False,
                        "is_practice": True,
                        "example_info": {"number": None, "content_type": "practice_questions"},
                        "section": section_info,
                        "subsection": subsection_info
                    }]
            
            # Just regular text
            return [{
                "text": text,
                "is_header": False,
                "is_example": False,
                "example_info": None,
                "section": section_info,
                "subsection": subsection_info
            }]
        
        # Found examples - split text
        last_end = 0
        for i, match in enumerate(matches):
            start_pos = match.start()
            
            # Add text before example
            if start_pos > last_end:
                before_text = text[last_end:start_pos].strip()
                if before_text:
                    blocks.append({
                        "text": before_text,
                        "is_header": False,
                        "is_example": False,
                        "example_info": None,
                        "section": section_info,
                        "subsection": subsection_info
                    })
            
            # Find end of this example (start of next example or end of text)
            if i + 1 < len(matches):
                end_pos = matches[i + 1].start()
            else:
                end_pos = len(text)
            
            # Add example block
            example_text = text[start_pos:end_pos].strip()
            blocks.append({
                "text": example_text,
                "is_header": False,
                "is_example": True,
                "example_info": {
                    "number": match.group(1),
                    "content_type": "example"
                },
                "section": section_info,
                "subsection": subsection_info
            })
            
            last_end = end_pos
        
        # Add any remaining text after last example
        if last_end < len(text):
            after_text = text[last_end:].strip()
            if after_text:
                blocks.append({
                    "text": after_text,
                    "is_header": False,
                    "is_example": False,
                    "example_info": None,
                    "section": section_info,
                    "subsection": subsection_info
                })
        
        return blocks

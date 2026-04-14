"""
Production-Ready Scanned PDF Extraction Tool
=============================================

Extracts detailed content from scanned PDFs using Vision LLM.
Handles: text, tables, equations, figures, diagrams.

Features:
- Batch processing for cost optimization
- Detailed markdown output with hierarchical tables
- Config file + CLI arguments
- Comprehensive logging
- Cost tracking and analysis
- Type hints and error handling

Usage:
    python scanned_pdf_extraction.py document.pdf
    python scanned_pdf_extraction.py document.pdf --start-page 1 --end-page 10 --batch-size 3
"""

import argparse
import base64
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from enum import Enum

from dotenv import load_dotenv
import fitz
import openai
import yaml

# Load environment
load_dotenv()

# Constants
VISION_PRICING = {
    "input_tokens": 0.005 / 1000,
    "output_tokens": 0.015 / 1000,
}

DEFAULT_DPI = 150
DEFAULT_BATCH_SIZE = 2
DEFAULT_CONFIG_FILE = "scanned_pdf_config.yaml"


class LogLevel(Enum):
    """Logging levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure logging with consistent format."""
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    return logging.getLogger(__name__)


logger = setup_logging()


class Config:
    """Configuration handler for scanned PDF extraction."""

    DEFAULT_CONFIG = {
        "vision_model": "gpt-4o",
        "batch_size": DEFAULT_BATCH_SIZE,
        "dpi": DEFAULT_DPI,
        "output_directory": ".",
        "output_prefix": "scanned_extraction",
        "log_level": "INFO",
        "max_tokens": 4000,
        "temperature": 0.1,
    }

    def __init__(self, config_file: Optional[str] = None) -> None:
        """Initialize configuration from file or defaults."""
        self.config = self.DEFAULT_CONFIG.copy()

        if config_file and Path(config_file).exists():
            try:
                with open(config_file, "r") as f:
                    file_config = yaml.safe_load(f) or {}

                    # Check for unified config structure
                    if "scanned_pdf_extraction" in file_config:
                        # Unified config format
                        logger.info(f"Loaded configuration from {config_file} (unified format)")
                        pdf_config = file_config.get("scanned_pdf_extraction", {})
                        global_config = file_config.get("global", {})
                        self.config.update(global_config)
                        self.config.update(pdf_config)
                    else:
                        # Legacy config format (direct settings)
                        logger.info(f"Loaded configuration from {config_file} (legacy format)")
                        self.config.update(file_config)

            except Exception as e:
                logger.warning(f"Failed to load config file {config_file}: {e}")

    def get(self, key: str, default: Optional[str] = None) -> any:
        """Get configuration value."""
        return self.config.get(key, default if default is not None else self.DEFAULT_CONFIG.get(key))

    def __getitem__(self, key: str) -> any:
        """Dictionary-style access."""
        return self.get(key)


def extract_pdf_pages(
    pdf_path: str,
    start_page: int = 1,
    end_page: Optional[int] = None,
    dpi: int = DEFAULT_DPI
) -> List[Tuple[int, str]]:
    """
    Extract PDF pages as base64-encoded images.

    Args:
        pdf_path: Path to PDF file
        start_page: Starting page (1-indexed)
        end_page: Ending page (inclusive, None = last page)
        dpi: Resolution for page rendering

    Returns:
        List of (page_number, base64_image) tuples

    Raises:
        FileNotFoundError: If PDF doesn't exist
        RuntimeError: If page extraction fails
    """
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    logger.info(f"Extracting pages {start_page} to {end_page or 'end'} from {pdf_path}...")

    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)

        if end_page is None:
            end_page = total_pages
        else:
            end_page = min(end_page, total_pages)

        if start_page < 1 or start_page > end_page:
            raise ValueError(f"Invalid page range: {start_page}-{end_page}")

        pages = []
        for page_num in range(start_page - 1, end_page):
            try:
                page = doc[page_num]
                mat = fitz.Matrix(dpi / 72, dpi / 72)
                pix = page.get_pixmap(matrix=mat)
                img_bytes = pix.tobytes("png")
                img_b64 = base64.b64encode(img_bytes).decode()
                pages.append((page_num + 1, img_b64))
            except Exception as e:
                logger.error(f"Failed to extract page {page_num + 1}: {e}")
                continue

        doc.close()

        if not pages:
            raise RuntimeError("No pages extracted successfully")

        logger.info(f"Successfully extracted {len(pages)} pages")
        return pages

    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        raise


def extract_content_from_pages(
    pages: List[Tuple[int, str]],
    model: str = "gpt-4o",
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_tokens: int = 4000,
    temperature: float = 0.1,
) -> Dict:
    """
    Extract content from pages using Vision LLM.

    Args:
        pages: List of (page_number, base64_image) tuples
        model: Vision model to use
        batch_size: Pages per API call
        max_tokens: Maximum tokens in response
        temperature: Model temperature

    Returns:
        Dictionary with extracted content and cost info
    """
    if not pages:
        logger.warning("No pages provided for extraction")
        return {
            "extracted_pages": [],
            "pages_processed": 0,
            "batches": 0,
            "total_cost": 0.0,
            "total_tokens": 0,
            "processing_time": 0.0,
        }

    logger.info(f"Extracting content from {len(pages)} pages with {model}")

    extraction_prompt = """You are a DETAILED FACTUAL content extractor for lecture slides.
Extract ONLY what is actually visible. NO interpretation.
Assume the reader CANNOT see the slide - describe completely.

For EACH slide extract:

1. **SLIDE TITLE** — Exact title shown

2. **TEXT CONTENT** — All visible text (headings, paragraphs, bullets, labels)

3. **TABLES** — As proper markdown with full structure:
   - All column headers (including multi-level headers)
   - Row headers
   - Every cell value
   - For grouped columns, use header hierarchy

4. **EQUATIONS** — For each equation:
   - Exact LaTeX
   - Caption/label if visible
   - Variable meanings

5. **FIGURES/DIAGRAMS/PLOTS** — EXHAUSTIVE description:
   - Layout and structure
   - All visual elements (shapes, colors, labels, numbers)
   - Text annotations (exact wording)
   - Connections and relationships
   - For specific types: graphs (axes, scale, data), plots (ranges, legends), molecular (atoms, bonds), flowcharts (steps), particle diagrams (particles, interactions)

NO SPECULATION. ONLY WHAT IS VISIBLE.

Return JSON:
{
  "pages": [
    {
      "page_number": 1,
      "slide_title": "Title",
      "text_content": "All visible text",
      "tables": [{"table_number": 1, "caption": "...", "markdown_table": "..."}],
      "equations": [{"equation_number": 1, "latex": "...", "variables": {}}],
      "figures": [{"figure_number": 1, "type": "...", "detailed_description": "..."}]
    }
  ]
}"""

    # Create batches
    batches = [pages[i : i + batch_size] for i in range(0, len(pages), batch_size)]
    logger.info(f"Processing {len(batches)} batch(es) ({batch_size} pages per batch)")

    client = openai.OpenAI(api_key=__import__("os").getenv("OPENAI_API_KEY"))
    all_extracted = []
    total_input_tokens = 0
    total_output_tokens = 0
    overall_start = time.time()

    for batch_idx, batch_pages in enumerate(batches, 1):
        batch_start = time.time()
        page_nums = [str(pnum) for pnum, _ in batch_pages]

        # Build content
        content = [{"type": "text", "text": extraction_prompt}]
        content.append({"type": "text", "text": f"Extract from pages: {', '.join(page_nums)}"})

        for page_num, img_b64 in batch_pages:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_b64}", "detail": "high"},
            })

        logger.info(f"  Batch {batch_idx}/{len(batches)}: Pages {', '.join(page_nums)}...")

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": content}],
                max_tokens=max_tokens,
                temperature=temperature,
            )

            batch_elapsed = time.time() - batch_start

            # Parse response
            response_text = response.choices[0].message.content

            # Extract JSON from code blocks if needed
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            extracted = json.loads(response_text)
            all_extracted.extend(extracted.get("pages", []))

            total_input_tokens += response.usage.prompt_tokens
            total_output_tokens += response.usage.completion_tokens

            logger.info(f"    ✓ Completed in {batch_elapsed:.1f}s ({response.usage.prompt_tokens}↓ {response.usage.completion_tokens}↑ tokens)")

        except json.JSONDecodeError as e:
            logger.error(f"    ✗ JSON parse failed: {e}")
            continue
        except Exception as e:
            logger.error(f"    ✗ Extraction failed: {e}")
            continue

    total_time = time.time() - overall_start
    total_tokens = total_input_tokens + total_output_tokens
    input_cost = total_input_tokens * VISION_PRICING["input_tokens"]
    output_cost = total_output_tokens * VISION_PRICING["output_tokens"]
    total_cost = input_cost + output_cost

    logger.info(f"Extraction complete: {len(all_extracted)} pages in {total_time:.1f}s")

    return {
        "extracted_pages": all_extracted,
        "pages_processed": len(pages),
        "batches": len(batches),
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_tokens,
        "input_cost": input_cost,
        "output_cost": output_cost,
        "total_cost": total_cost,
        "processing_time": total_time,
        "time_per_page": total_time / len(pages) if pages else 0,
    }


def convert_to_markdown(pages: List[Dict]) -> str:
    """
    Convert extracted pages to markdown format.

    Args:
        pages: List of extracted page dictionaries

    Returns:
        Formatted markdown string
    """
    lines = []

    for page in pages:
        page_num = page.get("page_number", "?")
        title = page.get("slide_title", "Untitled")

        lines.append(f"# Page {page_num}: {title}")
        lines.append("")

        # Text content
        if page.get("text_content"):
            lines.append("## Content")
            lines.append(page["text_content"])
            lines.append("")

        # Tables
        if page.get("tables"):
            lines.append("## Tables")
            for table in page["tables"]:
                if isinstance(table, dict):
                    table_num = table.get("table_number", "")
                    caption = table.get("caption", "")
                    description = table.get("description", "")
                    header_structure = table.get("header_structure", "")
                    markdown_table = table.get("markdown_table", "")

                    if table_num:
                        lines.append(f"### Table {table_num}")
                    if caption:
                        lines.append(f"**{caption}**")
                        lines.append("")
                    if description:
                        lines.append(f"{description}")
                        lines.append("")
                    if header_structure:
                        lines.append(f"**Structure:** {header_structure}")
                        lines.append("")
                    if markdown_table:
                        lines.append(markdown_table)
                    lines.append("")

        # Equations
        if page.get("equations"):
            lines.append("## Equations")
            for eq in page["equations"]:
                if isinstance(eq, dict):
                    eq_num = eq.get("equation_number", "")
                    latex = eq.get("latex", "")
                    caption = eq.get("caption", "")
                    variables = eq.get("variables", {})

                    if eq_num:
                        lines.append(f"### Equation {eq_num}")
                    if caption:
                        lines.append(f"**{caption}**")
                        lines.append("")
                    if latex:
                        lines.append(f"$$\n{latex}\n$$")
                        lines.append("")
                    if variables:
                        lines.append("**Variables:**")
                        for symbol, definition in variables.items():
                            if definition and definition != "None":
                                lines.append(f"- **{symbol}** — {definition}")
                        lines.append("")

        # Figures
        if page.get("figures"):
            lines.append("## Figures & Diagrams")
            for fig in page["figures"]:
                if isinstance(fig, dict):
                    fig_num = fig.get("figure_number", "")
                    fig_type = fig.get("type", "")
                    caption = fig.get("caption", "")
                    description = fig.get("detailed_description", "")

                    if fig_num:
                        type_str = f" ({fig_type})" if fig_type else ""
                        lines.append(f"### Figure {fig_num}{type_str}")
                        lines.append("")
                    if caption:
                        lines.append(f"**Caption:** {caption}")
                        lines.append("")
                    if description:
                        lines.append("**Description:**")
                        lines.append("")
                        lines.append(description)
                    lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Extract detailed content from scanned PDFs using Vision LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract all pages
  python scanned_pdf_extraction.py document.pdf

  # Extract pages 1-10 with custom batch size
  python scanned_pdf_extraction.py document.pdf --start-page 1 --end-page 10 --batch-size 3

  # Use custom model
  python scanned_pdf_extraction.py document.pdf --model gpt-4o-mini

  # Use config file
  python scanned_pdf_extraction.py document.pdf --config custom.yaml
        """
    )

    parser.add_argument("pdf_path", help="Path to PDF file")
    parser.add_argument("--start-page", type=int, default=1, help="Start page (default: 1)")
    parser.add_argument("--end-page", type=int, default=None, help="End page (default: last)")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help=f"Pages per batch (default: {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--model", default="gpt-4o", help="Vision model (default: gpt-4o)")
    parser.add_argument("--config", default="extraction_config_unified.yaml", help="Config file path (default: extraction_config_unified.yaml)")
    parser.add_argument("--output-dir", default=".", help="Output directory")
    parser.add_argument("--output-prefix", default="scanned_extraction", help="Output file prefix")
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI, help=f"Page DPI (default: {DEFAULT_DPI})")

    args = parser.parse_args()

    # Load config
    config = Config(args.config)
    setup_logging(config["log_level"])

    # Override with CLI args
    if args.model:
        config.config["vision_model"] = args.model
    if args.batch_size:
        config.config["batch_size"] = args.batch_size

    # Validate PDF
    if not Path(args.pdf_path).exists():
        logger.error(f"PDF not found: {args.pdf_path}")
        sys.exit(1)

    try:
        # Extract pages
        pages = extract_pdf_pages(
            args.pdf_path,
            start_page=args.start_page,
            end_page=args.end_page,
            dpi=args.dpi
        )

        # Extract content
        result = extract_content_from_pages(
            pages,
            model=config["vision_model"],
            batch_size=config["batch_size"],
            max_tokens=config["max_tokens"],
            temperature=config["temperature"],
        )

        # Convert to markdown
        markdown = convert_to_markdown(result["extracted_pages"])

        # Save output
        output_file = Path(args.output_dir) / f"{args.output_prefix}_{args.start_page}_{args.end_page or 'end'}.md"
        output_file.write_text(markdown, encoding="utf-8")

        # Print summary
        print()
        print("=" * 70)
        print("SCANNED PDF EXTRACTION COMPLETE")
        print("=" * 70)
        print(f"Output file: {output_file}")
        print(f"Pages processed: {result['pages_processed']}")
        print(f"Batches: {result['batches']}")
        print()
        print(f"Tokens: {result['total_tokens']:,} (↓ {result['total_input_tokens']:,} / ↑ {result['total_output_tokens']:,})")
        print(f"Time: {result['processing_time']:.1f}s ({result['time_per_page']:.2f}s per page)")
        print(f"Cost: ${result['total_cost']:.6f}")
        print("=" * 70)

    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

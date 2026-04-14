"""
Vision LLM extraction for scanned PDFs.

Tests GPT-4o vision extraction on scanned PDFs with cost estimation.
Batches multiple pages per request to reduce costs.

Usage:
    python test_vision_extraction.py
"""

import base64
import json
import logging
import os
import time
from pathlib import Path

from dotenv import load_dotenv
import fitz  # PyMuPDF
import openai

# Load env
load_dotenv()

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Pricing for GPT-4o vision (as of 2026-04)
VISION_PRICING = {
    "input_tokens": 0.005 / 1000,  # $0.005 per 1K input tokens
    "output_tokens": 0.015 / 1000,  # $0.015 per 1K output tokens
}

# Rough token estimates for images
IMAGE_TOKENS = {
    "low_res": 65,      # low resolution image
    "high_res": 258,    # high resolution image (default)
}


def convert_to_markdown(extracted_pages: list) -> str:
    """Convert extracted content to detailed, richly-formatted markdown."""
    lines = []

    for page in extracted_pages:
        page_num = page.get("page_number", "?")
        slide_title = page.get("slide_title", "")
        text_content = page.get("text_content", "")
        figures = page.get("figures", [])
        equations = page.get("equations", [])
        tables = page.get("tables", [])

        # Header
        lines.append(f"# Slide {page_num}: {slide_title}")
        lines.append("")

        # Text content
        if text_content:
            lines.append("## Content")
            lines.append(text_content)
            lines.append("")

        # Tables (extract and display properly)
        if tables:
            lines.append("## Tables")
            for table in tables:
                if isinstance(table, dict):
                    table_num = table.get("table_number", "")
                    caption = table.get("caption", "")
                    description = table.get("description", "")
                    markdown_table = table.get("markdown_table", "")

                    lines.append(f"### Table {table_num}")
                    if caption:
                        lines.append(f"**{caption}**")
                        lines.append("")
                    if description:
                        lines.append(f"{description}")
                        lines.append("")

                                # Display header structure if present
                    header_structure = table.get("header_structure", "")
                    if header_structure:
                        lines.append(f"**Table Structure:** {header_structure}")
                        lines.append("")

                    # Display the actual markdown table
                    if markdown_table:
                        lines.append(markdown_table)
                    lines.append("")

        # Equations with variables
        if equations:
            lines.append("## Equations")
            for eq in equations:
                if isinstance(eq, dict):
                    eq_num = eq.get("equation_number", "")
                    latex = eq.get("latex", "")
                    caption = eq.get("caption", "")
                    variables = eq.get("variables", {})

                    lines.append(f"### Equation {eq_num}")
                    if caption:
                        lines.append(f"**{caption}**")
                        lines.append("")

                    lines.append(f"$$\n{latex}\n$$")
                    lines.append("")

                    if variables and variables != {}:
                        lines.append("**Variables:**")
                        for symbol, definition in variables.items():
                            if definition and definition != "None":
                                lines.append(f"- **{symbol}** — {definition}")
                        lines.append("")

        # Figures with rich descriptions
        if figures:
            lines.append("## Figures & Diagrams")
            for fig in figures:
                if isinstance(fig, dict):
                    fig_num = fig.get("figure_number", "")
                    fig_type = fig.get("type", "")
                    caption = fig.get("caption", "")
                    description = fig.get("detailed_description", "")

                    type_str = f" ({fig_type})" if fig_type else ""
                    lines.append(f"### Figure {fig_num}{type_str}")
                    lines.append("")

                    if caption:
                        lines.append(f"**Caption:** {caption}")
                        lines.append("")

                    if description:
                        lines.append(f"**Description:**")
                        lines.append("")
                        lines.append(description)
                    lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def convert_to_markdown_old(extracted_pages: list) -> str:
    """Convert extracted page data to COMPREHENSIVE pedagogical markdown for tutoring."""
    lines = []

    for page in extracted_pages:
        page_num = page.get("page_number", "?")
        slide_title = page.get("slide_title", "")
        full_explanation = page.get("full_explanation", "")
        content_with_detail = page.get("content_with_detail", "")
        figures = page.get("figures", [])
        equations = page.get("equations", [])
        tables = page.get("tables", [])

        # Page header
        lines.append(f"# Slide {page_num}: {slide_title}")
        lines.append("")

        # Full explanation (overview)
        if full_explanation:
            lines.append("## Overview & Context")
            lines.append(full_explanation)
            lines.append("")

        # Content with detail
        if content_with_detail:
            lines.append("## Content Explanation")
            lines.append(content_with_detail)
            lines.append("")

        # Equations with FULL detail
        if equations:
            lines.append("## Equations & Formulas")
            for eq in equations:
                if isinstance(eq, dict):
                    eq_num = eq.get("equation_number", "")
                    name = eq.get("name", "")
                    latex = eq.get("latex", "")
                    meaning = eq.get("meaning_in_words", "")
                    significance = eq.get("significance", "")
                    when_to_use = eq.get("when_to_use", "")
                    related = eq.get("related_concepts", "")
                    symbols = eq.get("symbols_explained", {})

                    lines.append(f"### Equation {eq_num}: {name}")
                    lines.append("")

                    # The formula
                    lines.append(f"$$\n{latex}\n$$")
                    lines.append("")

                    # Meaning in words
                    if meaning:
                        lines.append(f"**What this equation says:** {meaning}")
                        lines.append("")

                    # Symbols
                    if symbols:
                        lines.append("**Symbol Definitions:**")
                        for symbol, definition in symbols.items():
                            lines.append(f"- **{symbol}** — {definition}")
                        lines.append("")

                    # Significance
                    if significance:
                        lines.append(f"**Why it matters:** {significance}")
                        lines.append("")

                    # When to use
                    if when_to_use:
                        lines.append(f"**When/where to use:** {when_to_use}")
                        lines.append("")

                    # Related concepts
                    if related:
                        lines.append(f"**Connections:** {related}")
                        lines.append("")

                else:
                    lines.append(f"### Equation")
                    lines.append(f"$$\n{eq}\n$$")
                    lines.append("")

        # Figures with EXHAUSTIVE detail
        if figures:
            lines.append("## Figures & Visual Elements")
            for fig in figures:
                if isinstance(fig, dict):
                    fig_num = fig.get("figure_number", "")
                    caption = fig.get("caption", "")
                    visual_desc = fig.get("visual_description", "")
                    interpretation = fig.get("interpretation_guide", "")
                    key_insight = fig.get("key_insight", "")
                    phys_meaning = fig.get("physical_meaning", "")
                    connections = fig.get("connections", "")

                    lines.append(f"### Figure {fig_num}: {caption}" if caption else f"### Figure {fig_num}")
                    lines.append("")

                    # Visual description
                    if visual_desc:
                        lines.append("**What you see:**")
                        lines.append(visual_desc)
                        lines.append("")

                    # How to interpret
                    if interpretation:
                        lines.append("**How to read/interpret this figure:**")
                        lines.append(interpretation)
                        lines.append("")

                    # Key insight
                    if key_insight:
                        lines.append("**Key insight (what this teaches):**")
                        lines.append(key_insight)
                        lines.append("")

                    # Physical meaning
                    if phys_meaning:
                        lines.append("**Physical/mathematical meaning:**")
                        lines.append(phys_meaning)
                        lines.append("")

                    # Connections
                    if connections:
                        lines.append("**How it connects to other elements:**")
                        lines.append(connections)
                        lines.append("")

                else:
                    lines.append(f"### Figure")
                    lines.append(fig)
                    lines.append("")

        # Tables with COMPLETE detail
        if tables:
            lines.append("## Tables & Data")
            for table in tables:
                if isinstance(table, dict):
                    table_num = table.get("table_number", "")
                    purpose = table.get("purpose", "")
                    structure = table.get("structure_explanation", "")
                    row_by_row = table.get("row_by_row", [])
                    col_by_col = table.get("column_by_column", [])
                    patterns = table.get("patterns_and_insights", "")
                    markdown_table = table.get("markdown_table", "")

                    lines.append(f"### Table {table_num}")
                    lines.append("")
                    
                    # Purpose
                    if purpose:
                        lines.append(f"**What this table shows:** {purpose}")
                        lines.append("")

                    # Structure
                    if structure:
                        lines.append(f"**Table structure:** {structure}")
                        lines.append("")

                    # The actual table
                    if markdown_table:
                        lines.append(markdown_table)
                        lines.append("")

                    # Row-by-row explanation
                    if row_by_row:
                        lines.append("**Row-by-row explanation:**")
                        for row_desc in row_by_row:
                            lines.append(f"- {row_desc}")
                        lines.append("")

                    # Column-by-column explanation
                    if col_by_col:
                        lines.append("**Column-by-column explanation:**")
                        for col_desc in col_by_col:
                            lines.append(f"- {col_desc}")
                        lines.append("")

                    # Patterns and insights
                    if patterns:
                        lines.append(f"**Patterns & insights:** {patterns}")
                        lines.append("")

                else:
                    lines.append(f"### Table")
                    lines.append(table)
                    lines.append("")

        # Separator
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def extract_pdf_pages(pdf_path: str, start_page: int = 1, end_page: int = None, dpi: int = 150) -> list[tuple[int, str]]:
    """
    Extract PDF pages as base64-encoded images.

    Returns: List of (page_num, base64_image) tuples
    """
    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    if end_page is None:
        end_page = total_pages

    end_page = min(end_page, total_pages)

    pages = []
    for page_num in range(start_page - 1, end_page):  # 0-indexed
        page = doc[page_num]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        img_b64 = base64.b64encode(img_bytes).decode()
        pages.append((page_num + 1, img_b64))  # return 1-indexed page num

    doc.close()
    return pages


def extract_with_vision(
    pdf_path: str,
    start_page: int = 1,
    end_page: int = None,
    pages_per_batch: int = 5,
    model: str = "gpt-4o",
) -> dict:
    """
    Extract content from scanned PDF using vision LLM.

    Args:
        pdf_path: Path to PDF
        start_page: Starting page (1-indexed)
        end_page: Ending page (inclusive)
        pages_per_batch: Pages to send per API call (5-10 recommended)
        model: Vision model to use

    Returns:
        {
            "extracted_text": str,
            "pages_processed": int,
            "batches": int,
            "total_tokens_estimate": int,
            "total_cost_estimate": float,
            "total_time_seconds": float,
        }
    """
    overall_start = time.time()
    client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Extract pages
    print(f"Extracting PDF pages {start_page} to {end_page or 'end'}...")
    pages = extract_pdf_pages(pdf_path, start_page, end_page, dpi=150)
    print(f"Extracted {len(pages)} pages as images")

    if not pages:
        return {"error": "No pages extracted"}

    # Batch and process
    batches = []
    for i in range(0, len(pages), pages_per_batch):
        batch_pages = pages[i : i + pages_per_batch]
        batches.append(batch_pages)

    print(f"\nProcessing {len(batches)} batch(es) ({pages_per_batch} pages per batch)...")

    all_extracted_content = []
    total_input_tokens = 0
    total_output_tokens = 0

    extraction_prompt = """You are a DETAILED FACTUAL content extractor for lecture slides (any subject: physics, chemistry, math, biology, etc.).
Extract ONLY what is actually visible. NO interpretation. DESCRIBE EVERYTHING IN DETAIL.
Assume the reader CANNOT see the slide - describe so they understand completely.

For EACH slide extract:

1. **SLIDE TITLE** — Exact title shown

2. **TEXT CONTENT** — All visible text word-for-word (headings, paragraphs, bullets, labels, annotations)

3. **TABLES** — Extract as proper markdown table WITH FULL STRUCTURE:
   - Identify ALL column headers, including multi-level/sub-headers
   - Include row headers (first column)
   - For tables with grouped columns (like "Generation: 1st, 2nd, 3rd"), represent the hierarchy:
     * Use TWO HEADER ROWS if there are main headers and sub-headers
     * First row: main category headers
     * Second row: sub-category headers
   - Include every row and column exactly as shown
   - Preserve all values/text in cells
   - Example for proper hierarchical structure:
     | Particle Type | Generation ||| Charge | Feels force |||
     |---|1st|2nd|3rd|Units of e|Strong|EM|Weak|
     | U-Quarks (×3 colours) | u | c | t | +2/3 | Y | Y | Y |
     | D-Quarks (×3 colours) | d | s | b | -1/3 | Y | Y | Y |
     | Charged Leptons | e | μ | τ | -1 | N | Y | Y |
     | Neutral Leptons | νe | νμ | ντ | 0 | N | N | Y |

4. **EQUATIONS** — For each equation:
   - Exact LaTeX
   - Any visible caption/label
   - Variables and their meanings (from visible labels/context)

5. **FIGURES/DIAGRAMS/PLOTS** — EXHAUSTIVE description:

   **Layout & Structure:**
   - Overall composition (centered, side-by-side, grid, etc.)
   - Number and arrangement of elements
   - Relative sizes and spacing

   **Visual Elements** (describe EVERY one):
   - Shapes: circles, boxes, rectangles, spheres, curves, lines, arrows
   - Colors: EVERY color used and what it represents/distinguishes
   - Text labels and annotations: EXACT wording and location
   - Numbers, values, or data points shown
   - Patterns, shading, or visual emphasis

   **Connections & Relationships:**
   - How elements connect (lines, arrows, grouping)
   - Hierarchies or sequences
   - Pairs or grouped elements

   **For specific diagram types:**
   - GRAPHS: axes labels, scale, units, data points, curves/trends, grid lines
   - PLOTS: axis ranges, labeled points, lines/dots, legends
   - MOLECULAR: atoms (symbols, colors), bonds (single/double/triple), structure
   - FLOWCHARTS: decision points, flow direction, process steps
   - CONCEPT MAPS: central concept, branches, relationships
   - PARTICLE DIAGRAMS: incoming/outgoing particles, interaction points, force carriers

   **Caption** — exact text if visible

   **Example 1 (Physics):** "Diagram shows two vertical boxes side-by-side. LEFT BOX (dark red header 'Quarks'): contains 3 pairs of colored spheres arranged vertically. Top pair: left sphere (dark red/purple) labeled 'Bottom' with charge '-1/3', right sphere (light) labeled 'Top' with '+2/3'. Middle pair: left (dark blue) 'Strange' (-1/3), right (light) 'Charm' (+2/3). Bottom pair: left (brown) 'Down' (-1/3), right (light) 'Up' (+2/3). Footer text: 'each quark: R, B, G 3 colours'. RIGHT BOX (dark green header 'Leptons'): 3 pairs, top to bottom: Tau (dark green sphere, -1) paired with Tau Neutrino (light sphere, 0); Muon (dark green, -1) with Muon Neutrino (light, 0); Electron (dark green, -1) with Electron Neutrino (light, 0)."

   **Example 2 (Chemistry):** "Molecular structure diagram. Central carbon atom (black C). Four bonds extending in tetrahedral arrangement: top-left bond to oxygen (red O, double bond shown as double line); top-right to hydrogen (H); bottom-left to hydrogen (H); bottom-right to carbon atom (C) which connects to three more hydrogens. All atoms labeled with element symbols. Bond angles approximately 109.5 degrees."

   **Example 3 (Math):** "Cartesian coordinate system with x-axis (0-10, labeled 'Time (s)') and y-axis (0-100, labeled 'Distance (m)'). Blue curve starting at origin (0,0) rising steeply initially then leveling off, reaching approximately (10, 95). Red dotted line at y=100. Curve labeled 'position over time'. Grid lines shown every unit. Origin marked with small circle."

NO SPECULATION. ONLY WHAT IS VISIBLE.

{
  "pages": [
    {
      "page_number": 1,
      "slide_title": "Exact title",
      "text_content": "All visible text, exact wording",
      "tables": [
        {
          "table_number": 1,
          "caption": "Caption if visible",
          "description": "What data/information this table contains",
          "header_structure": "Description of column hierarchy (e.g., 'Main headers: Generation (subcolumns: 1st, 2nd, 3rd), Charge, Forces (subcolumns: Strong, EM, Weak)')",
          "markdown_table": "Properly structured markdown table with all data, showing grouped columns with appropriate spacing"
        }
      ],
      "equations": [
        {
          "equation_number": 1,
          "latex": "equation",
          "caption": "caption if visible",
          "variables": {"symbol": "meaning from context"}
        }
      ],
      "figures": [
        {
          "figure_number": 1,
          "type": "diagram type (graph, plot, molecular diagram, flowchart, concept map, particle diagram, etc)",
          "caption": "Exact caption if visible",
          "detailed_description": "VERY DETAILED description covering: layout, all elements, colors, labels, values, connections, visual hierarchy. Assume reader cannot see the image."
        }
      ]
    }
  ]
}"""

    for batch_idx, batch_pages in enumerate(batches, 1):
        batch_start = time.time()

        # Build message with all pages in batch
        content = [
            {
                "type": "text",
                "text": extraction_prompt,
            }
        ]

        page_nums_str = ", ".join(str(pnum) for pnum, _ in batch_pages)
        content.append({
            "type": "text",
            "text": f"Extract content from pages: {page_nums_str}",
        })

        # Add images
        for page_num, img_b64 in batch_pages:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{img_b64}",
                    "detail": "high",
                },
            })

        # Call GPT-4o vision
        print(f"  Batch {batch_idx}/{len(batches)}: Pages {page_nums_str}...", end=" ", flush=True)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": content}
            ],
            max_tokens=4000,
            temperature=0.1,
        )

        batch_elapsed = time.time() - batch_start

        # Parse response
        try:
            response_text = response.choices[0].message.content

            # Try to extract JSON if it's wrapped in markdown code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            extracted = json.loads(response_text)
            all_extracted_content.extend(extracted.get("pages", []))
            print(f"OK ({batch_elapsed:.1f}s)")
        except (json.JSONDecodeError, AttributeError, IndexError) as e:
            print(f"FAILED: {e}")
            logger.error(f"Response text (first 200 chars): {response_text[:200] if response_text else 'empty'}")
            continue

        # Token usage
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

        total_input_tokens += input_tokens
        total_output_tokens += output_tokens

        logger.info(f"  Batch {batch_idx}: {input_tokens} input + {output_tokens} output tokens")

    # Calculate cost
    input_cost = total_input_tokens * VISION_PRICING["input_tokens"]
    output_cost = total_output_tokens * VISION_PRICING["output_tokens"]
    total_cost = input_cost + output_cost

    total_time = time.time() - overall_start

    return {
        "extracted_pages": all_extracted_content,
        "pages_processed": len(pages),
        "batches": len(batches),
        "pages_per_batch": pages_per_batch,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "input_cost": input_cost,
        "output_cost": output_cost,
        "total_cost": total_cost,
        "total_time_seconds": total_time,
        "time_per_page": total_time / len(pages),
    }


def print_cost_analysis(result: dict):
    """Print formatted cost analysis."""
    if "error" in result:
        print(f"Error: {result['error']}")
        return

    print(f"\n{'='*60}")
    print(f"VISION EXTRACTION COST ANALYSIS")
    print(f"{'='*60}")
    print(f"Pages processed: {result['pages_processed']}")
    print(f"Batches: {result['batches']} (pages per batch: {result['pages_per_batch']})")
    print(f"\nTokens:")
    print(f"  Input: {result['total_input_tokens']:,}")
    print(f"  Output: {result['total_output_tokens']:,}")
    print(f"  Total: {result['total_input_tokens'] + result['total_output_tokens']:,}")
    print(f"\nCost:")
    print(f"  Input: ${result['input_cost']:.4f}")
    print(f"  Output: ${result['output_cost']:.4f}")
    print(f"  Total: ${result['total_cost']:.4f}")
    print(f"\nTiming:")
    print(f"  Total time: {result['total_time_seconds']:.1f}s")
    print(f"  Time per page: {result['time_per_page']:.2f}s")
    print(f"\nScaling:")
    cost_per_100_pages = (result['total_cost'] / result['pages_processed']) * 100
    time_per_100_pages = (result['total_time_seconds'] / result['pages_processed']) * 100
    print(f"  Cost for 100 pages: ${cost_per_100_pages:.2f}")
    print(f"  Time for 100 pages: {time_per_100_pages:.1f}s ({time_per_100_pages/60:.1f}m)")
    print(f"{'='*60}\n")


def main():
    # Use one of the physics lecture PDFs
    pdf_path = "sample_pdfs/physic_lecture/lecture_2.pdf"

    if not Path(pdf_path).exists():
        print(f"PDF not found: {pdf_path}")
        return

    # Test with different batch sizes to find optimal cost/speed
    print("Testing vision extraction with different batch sizes...\n")

    configs = [
        {"start": 1, "end": 6, "batch_size": 2, "label": "Test 1: 6 pages, 2 per batch"},
        # Uncomment to test more:
        # {"start": 1, "end": 10, "batch_size": 5, "label": "Test 2: 10 pages, 5 per batch"},
        # {"start": 1, "end": 20, "batch_size": 10, "label": "Test 3: 20 pages, 10 per batch"},
    ]

    results = []
    for config in configs:
        print(f"\n{config['label']}")
        print("-" * 60)

        result = extract_with_vision(
            pdf_path,
            start_page=config["start"],
            end_page=config["end"],
            pages_per_batch=config["batch_size"],
        )

        results.append((config["label"], result))
        print_cost_analysis(result)

        # Save extracted content (both JSON and Markdown)
        if "extracted_pages" in result:
            # Save JSON
            json_file = f"vision_extraction_{config['start']}_{config['end']}.json"
            with open(json_file, "w") as f:
                json.dump(result["extracted_pages"], f, indent=2)
            print(f"Extracted content saved to {json_file}")

            # Convert to Markdown
            md_file = f"vision_extraction_{config['start']}_{config['end']}.md"
            markdown_content = convert_to_markdown(result["extracted_pages"])
            with open(md_file, "w", encoding="utf-8") as f:
                f.write(markdown_content)
            print(f"Markdown saved to {md_file}\n")

    # Summary table
    print(f"\n{'='*60}")
    print("COST COMPARISON")
    print(f"{'='*60}")
    print(f"{'Test':<30} {'Pages':<8} {'Cost':<12} {'Time':<12}")
    print(f"{'-'*60}")
    for label, result in results:
        if "error" not in result:
            pages = result["pages_processed"]
            cost = f"${result['total_cost']:.4f}"
            time_s = f"{result['total_time_seconds']:.1f}s"
            print(f"{label:<30} {pages:<8} {cost:<12} {time_s:<12}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()

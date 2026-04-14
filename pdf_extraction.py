"""
Production-Ready PDF Extraction Tool
====================================

Hybrid extraction combining:
1. Docling - text + formula detection
2. Vision LLM - image descriptions (optional)
3. Vision LLM - formula LaTeX (optional)

Features:
- Config file support (YAML)
- CLI arguments for customization
- Multiple extraction modes
- Batch processing
- Token and cost tracking

Usage:
    python pdf_extraction.py <pdf_path> [--start-page 1] [--end-page 10] [--mode complete]
    python pdf_extraction.py <pdf_path> --config extraction_config.yaml
"""

import argparse
import asyncio
import base64
import json
import logging
import os
import sys
import time
from collections.abc import Iterable
from pathlib import Path
from enum import Enum

from dotenv import load_dotenv
import fitz
import openai
import yaml

from docling.datamodel.base_models import InputFormat, ItemAndImageEnrichmentElement
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.models.base_model import BaseItemAndImageEnrichmentModel
from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
from docling_core.types.doc import DocItemLabel, DoclingDocument, NodeItem, TextItem

# Load env
load_dotenv()

# Pricing for GPT-4o vision
VISION_PRICING = {
    "input_tokens": 0.005 / 1000,
    "output_tokens": 0.015 / 1000,
}

# Global storage
FORMULA_DATA = []


class ExtractionMode(Enum):
    """Extraction modes."""
    TEXT_ONLY = "text_only"
    TEXT_FORMULAS = "text_formulas"
    TEXT_IMAGES = "text_images"
    COMPLETE = "complete"


class Config:
    """Configuration handler - reads from unified config file."""
    def __init__(self, config_file: str = None):
        self.defaults = {
            "vision_model": "gpt-4o",
            "extraction_mode": "complete",
            "image_dpi": 150,
            "image_batch_size": 2,
            "output_directory": ".",
            "output_prefix": "extraction",
            "extract_formulas": True,
            "extract_pictures": False,
            "extract_tables": False,
            "log_level": "INFO",
        }

        self.config = self.defaults.copy()

        if config_file and Path(config_file).exists():
            with open(config_file, "r") as f:
                file_config = yaml.safe_load(f) or {}

                # Check for unified config structure
                if "pdf_extraction" in file_config:
                    # Unified config format
                    logger.info(f"Loaded configuration from {config_file} (unified format)")
                    pdf_config = file_config.get("pdf_extraction", {})
                    global_config = file_config.get("global", {})
                    self.config.update(global_config)
                    self.config.update(pdf_config)
                else:
                    # Legacy config format (direct settings)
                    logger.info(f"Loaded configuration from {config_file} (legacy format)")
                    self.config.update(file_config)

    def get(self, key, default=None):
        return self.config.get(key, default if default is not None else self.defaults.get(key))

    def __getitem__(self, key):
        return self.get(key)


# Setup logging
def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    return logging.getLogger(__name__)


logger = setup_logging()


class FormulaExtractionOptions(PdfPipelineOptions):
    """Custom options to enable formula understanding."""
    do_formula_understanding: bool = True


class FormulaExtractionModel(BaseItemAndImageEnrichmentModel):
    """Saves formula images for later extraction."""
    images_scale = 2.6

    def __init__(self, enabled: bool, output_dir: str = "formulas"):
        self.enabled = enabled
        self.formula_count = 0
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    def is_processable(self, doc: DoclingDocument, element: NodeItem) -> bool:
        return (
            self.enabled
            and isinstance(element, TextItem)
            and element.label == DocItemLabel.FORMULA
        )

    def __call__(
        self,
        doc: DoclingDocument,
        element_batch: Iterable[ItemAndImageEnrichmentElement],
    ) -> Iterable[NodeItem]:
        """Save formula images."""
        if not self.enabled:
            return

        for enrich_element in element_batch:
            image_path = self.output_dir / f"formula_{self.formula_count}.png"
            enrich_element.image.save(str(image_path))

            item = enrich_element.item
            bbox = item.bbox if hasattr(item, "bbox") else None
            page_no = item.prov[0].page_no if (hasattr(item, "prov") and item.prov) else None

            FORMULA_DATA.append({
                "id": self.formula_count,
                "image_path": str(image_path),
                "page": page_no,
                "bbox": {
                    "left": bbox.l,
                    "top": bbox.t,
                    "right": bbox.r,
                    "bottom": bbox.b,
                } if bbox else None,
            })

            self.formula_count += 1
            yield item


class FormulaExtractionPipeline(StandardPdfPipeline):
    """Pipeline with formula extraction."""
    def __init__(self, pipeline_options: FormulaExtractionOptions):
        super().__init__(pipeline_options)
        self.pipeline_options: FormulaExtractionOptions
        self.model = FormulaExtractionModel(
            enabled=self.pipeline_options.do_formula_understanding
        )
        self.enrichment_pipe = [self.model]

        if self.pipeline_options.do_formula_understanding:
            self.keep_backend = True

    @classmethod
    def get_default_options(cls) -> FormulaExtractionOptions:
        return FormulaExtractionOptions()


def extract_text_with_docling(
    pdf_path: str,
    start_page: int = 1,
    end_page: int = None,
    extract_formulas: bool = True,
    extract_pictures: bool = False,
    extract_tables: bool = False,
) -> dict:
    """Extract text from PDF using Docling."""
    overall_start = time.time()

    if end_page is None:
        doc = fitz.open(pdf_path)
        end_page = len(doc)
        doc.close()

    logger.info(f"Extracting text from pages {start_page}-{end_page}...")

    FORMULA_DATA.clear()

    pipeline_options = FormulaExtractionOptions()
    pipeline_options.do_formula_understanding = extract_formulas
    pipeline_options.generate_picture_images = extract_pictures
    pipeline_options.generate_table_images = extract_tables

    if extract_formulas:
        doc_converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_cls=FormulaExtractionPipeline,
                    pipeline_options=pipeline_options,
                )
            }
        )
    else:
        doc_converter = DocumentConverter()

    if start_page == end_page:
        # Single page — no markers needed
        result = doc_converter.convert(pdf_path, page_range=(start_page, end_page))
        markdown_content = result.document.export_to_markdown()
    else:
        # Multiple pages — convert one page at a time so we can insert page markers.
        # Docling's export_to_markdown() produces a flat string with no page boundaries,
        # so we call convert() per page and concatenate with headers.
        page_parts = []
        for pno in range(start_page, end_page + 1):
            page_result = doc_converter.convert(pdf_path, page_range=(pno, pno))
            page_md = page_result.document.export_to_markdown().strip()
            page_parts.append(f"---\n## Page {pno}\n---\n\n{page_md}")
        markdown_content = "\n\n".join(page_parts)

    elapsed = time.time() - overall_start

    return {
        "markdown": markdown_content,
        "formula_data": list(FORMULA_DATA),
        "elapsed_time": elapsed,
    }


def extract_pdf_images(pdf_path: str, start_page: int = 1, end_page: int = None, dpi: int = 150) -> list:
    """Extract page images from PDF."""
    logger.info(f"Extracting page images...")

    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    if end_page is None:
        end_page = total_pages

    end_page = min(end_page, total_pages)

    images = []
    for page_num in range(start_page - 1, end_page):
        page = doc[page_num]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        images.append((page_num + 1, img_bytes))

    doc.close()
    return images


async def extract_images_with_vision(
    images: list,
    pages_per_batch: int = 2,
    model: str = "gpt-4o"
) -> dict:
    """Extract detailed descriptions of images using vision LLM."""
    if not images:
        return {
            "image_descriptions": {},
            "total_tokens": 0,
            "input_cost": 0,
            "output_cost": 0,
            "processing_time": 0
        }

    logger.info(f"Extracting image descriptions ({len(images)} images)...")

    overall_start = time.time()
    client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    batches = []
    for i in range(0, len(images), pages_per_batch):
        batch_images = images[i : i + pages_per_batch]
        batches.append(batch_images)

    image_descriptions = {}
    total_input_tokens = 0
    total_output_tokens = 0

    extraction_prompt = """You are a DETAILED FACTUAL image extractor. Analyze these PDF page images.
For each page, write a single plain-text paragraph describing:
- Main content (text, tables, plots, diagrams)
- All visible labels, titles, captions, and annotations
- Any data shown in graphs or plots
- Overall structure and layout

Return JSON with page_number as key and a plain string description as value. No nested objects.

{
  "descriptions": {
    "1": "Plain text description of page 1 as a single paragraph.",
    "2": "Plain text description of page 2 as a single paragraph."
  }
}"""

    for batch_idx, batch_images in enumerate(batches, 1):
        content = [{"type": "text", "text": extraction_prompt}]

        page_nums_str = ", ".join(str(pnum) for pnum, _ in batch_images)
        content.append({"type": "text", "text": f"Extract from pages: {page_nums_str}"})

        for page_num, img_bytes in batch_images:
            img_b64 = base64.b64encode(img_bytes).decode()
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{img_b64}",
                    "detail": "high",
                },
            })

        logger.info(f"  Batch {batch_idx}/{len(batches)}: Pages {page_nums_str}...")

        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
            max_tokens=4000,
            temperature=0.1,
        )

        try:
            response_text = response.choices[0].message.content

            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            extracted = json.loads(response_text)
            descriptions = extracted.get("descriptions", {})

            for page_str, desc in descriptions.items():
                try:
                    page_num = int(page_str)
                    image_descriptions[page_num] = desc
                except (ValueError, TypeError):
                    pass

            logger.info("  Result: OK")
        except (json.JSONDecodeError, AttributeError, IndexError) as e:
            logger.error(f"FAILED: {e}")
            continue

        total_input_tokens += response.usage.prompt_tokens
        total_output_tokens += response.usage.completion_tokens

    input_cost = total_input_tokens * VISION_PRICING["input_tokens"]
    output_cost = total_output_tokens * VISION_PRICING["output_tokens"]
    total_cost = input_cost + output_cost
    total_time = time.time() - overall_start

    return {
        "image_descriptions": image_descriptions,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_input_tokens + total_output_tokens,
        "input_cost": input_cost,
        "output_cost": output_cost,
        "total_cost": total_cost,
        "processing_time": total_time,
    }


async def extract_formulas_with_vision(model: str = "gpt-4o") -> dict:
    """Extract LaTeX from formula images using vision LLM."""
    if not FORMULA_DATA:
        return {
            "latex_dict": {},
            "total_tokens": 0,
            "input_cost": 0,
            "output_cost": 0,
            "processing_time": 0
        }

    logger.info(f"Extracting formula LaTeX ({len(FORMULA_DATA)} formulas)...")

    overall_start = time.time()
    client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    image_messages = []
    for formula in FORMULA_DATA:
        image_path = formula["image_path"]
        if not Path(image_path).exists():
            continue

        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()

        image_messages.append({
            "type": "image_url",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": image_b64,
            },
            "formula_id": formula["id"],
        })

    content = [
        {
            "type": "text",
            "text": """Extract LaTeX from formula images. Return JSON with formula IDs as keys.
Example: {"0": "E = mc^2", "1": "\\\\frac{1}{2}mv^2"}

Return ONLY valid JSON.""",
        }
    ]

    for msg in image_messages:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{msg['source']['data']}"
            },
        })

    response = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        max_tokens=4096,
    )

    try:
        response_text = response.choices[0].message.content

        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        latex_dict = json.loads(response_text)
        elapsed = time.time() - overall_start

        input_cost = response.usage.prompt_tokens * VISION_PRICING["input_tokens"]
        output_cost = response.usage.completion_tokens * VISION_PRICING["output_tokens"]

        return {
            "latex_dict": latex_dict,
            "total_tokens": response.usage.prompt_tokens + response.usage.completion_tokens,
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
            "input_cost": input_cost,
            "output_cost": output_cost,
            "total_cost": input_cost + output_cost,
            "processing_time": elapsed,
        }
    except (json.JSONDecodeError, AttributeError) as e:
        logger.error(f"Failed to parse formulas: {e}")
        return {
            "latex_dict": {},
            "total_tokens": 0,
            "input_cost": 0,
            "output_cost": 0,
            "processing_time": 0
        }


def merge_content(
    markdown: str,
    image_descriptions: dict = None,
    latex_dict: dict = None,
    start_page: int = 1,
    mode: ExtractionMode = ExtractionMode.COMPLETE
) -> str:
    """Merge markdown with images and/or formulas based on mode."""
    lines = markdown.split("\n")
    image_counter = 0
    formula_counter = 0

    for i, line in enumerate(lines):
        # Handle images
        if mode in (ExtractionMode.TEXT_IMAGES, ExtractionMode.COMPLETE):
            if "<!-- image -->" in line and image_descriptions:
                page_for_image = start_page + image_counter
                description = image_descriptions.get(page_for_image, "")
                if not description:
                    description = image_descriptions.get(image_counter + 1, "")
                if description:
                    # description may be a dict (structured LLM response) or a plain string
                    if isinstance(description, dict):
                        parts = []
                        if description.get("main_content"):
                            parts.append(description["main_content"])
                        if description.get("labels_titles_annotations"):
                            labels = description["labels_titles_annotations"]
                            if isinstance(labels, list):
                                parts.append("Labels/Annotations: " + "; ".join(labels))
                            else:
                                parts.append(f"Labels/Annotations: {labels}")
                        if description.get("data_shown"):
                            parts.append(description["data_shown"])
                        description_text = " ".join(parts)
                    else:
                        description_text = str(description)
                    lines[i] = f"**Image Description:** {description_text}"
                image_counter += 1

        # Handle formulas
        if mode in (ExtractionMode.TEXT_FORMULAS, ExtractionMode.COMPLETE):
            if "<!-- formula-not-decoded -->" in line and latex_dict:
                latex = latex_dict.get(str(formula_counter), "")
                if latex:
                    lines[i] = f"${latex}$"
                formula_counter += 1

    return "\n".join(lines)


async def extract_pdf(
    pdf_path: str,
    start_page: int = 1,
    end_page: int = None,
    config: Config = None
) -> dict:
    """Main extraction function."""
    if config is None:
        config = Config()

    mode = ExtractionMode(config["extraction_mode"])
    vision_model = config["vision_model"]
    output_dir = config["output_directory"]
    output_prefix = config["output_prefix"]

    logger.info(f"Starting PDF extraction: {pdf_path}")
    logger.info(f"Mode: {mode.value}")
    logger.info(f"Model: {vision_model}")

    overall_start = time.time()

    # Step 1: Extract text (always)
    text_result = extract_text_with_docling(
        pdf_path,
        start_page,
        end_page,
        extract_formulas=mode in (ExtractionMode.TEXT_FORMULAS, ExtractionMode.COMPLETE),
        extract_pictures=config["extract_pictures"],
        extract_tables=config["extract_tables"],
    )

    markdown = text_result["markdown"]
    formula_count = len(text_result["formula_data"])
    docling_time = text_result["elapsed_time"]

    image_descriptions = {}
    images_time = 0
    formula_time = 0
    vision_cost = 0

    # Step 2: Extract images if needed
    if mode in (ExtractionMode.TEXT_IMAGES, ExtractionMode.COMPLETE):
        if end_page is None:
            doc = fitz.open(pdf_path)
            end_page = len(doc)
            doc.close()

        images = extract_pdf_images(pdf_path, start_page, end_page, dpi=config["image_dpi"])

        image_result, formula_result = await asyncio.gather(
            extract_images_with_vision(
                images,
                pages_per_batch=config["image_batch_size"],
                model=vision_model
            ),
            extract_formulas_with_vision(model=vision_model) if mode == ExtractionMode.COMPLETE and formula_count > 0 else asyncio.sleep(0),
        )

        image_descriptions = image_result["image_descriptions"]
        images_time = image_result["processing_time"]
        vision_cost += image_result["total_cost"]

        if mode == ExtractionMode.COMPLETE and formula_count > 0:
            formula_time = formula_result["processing_time"]
            vision_cost += formula_result["total_cost"]

    # Step 3: Extract formulas if needed (without images)
    # Only run here for TEXT_FORMULAS — COMPLETE mode already ran this in Step 2's gather.
    # Do NOT reset formula_result here if it was already populated in Step 2.
    if mode == ExtractionMode.TEXT_FORMULAS and formula_count > 0:
        formula_result = await extract_formulas_with_vision(model=vision_model)
        formula_time = formula_result["processing_time"]
        vision_cost = formula_result["total_cost"]
    elif mode != ExtractionMode.COMPLETE:
        formula_result = {}

    # Step 4: Merge content
    latex_dict = None
    if mode in (ExtractionMode.TEXT_FORMULAS, ExtractionMode.COMPLETE):
        latex_dict = formula_result.get("latex_dict", {}) if formula_result else {}

    final_markdown = merge_content(
        markdown,
        image_descriptions=image_descriptions if image_descriptions else None,
        latex_dict=latex_dict,
        start_page=start_page,
        mode=mode
    )

    # Step 5: Save output
    output_file = Path(output_dir) / f"{output_prefix}_{start_page}_{end_page}.md"
    output_file.write_text(final_markdown, encoding="utf-8")

    total_time = time.time() - overall_start

    return {
        "output_file": str(output_file),
        "mode": mode.value,
        "pages": end_page - start_page + 1 if end_page else "unknown",
        "formulas": formula_count,
        "images": len(image_descriptions),
        "times": {
            "docling": docling_time,
            "images": images_time,
            "formulas": formula_time,
            "total": total_time,
        },
        "costs": {
            "vision": vision_cost,
        }
    }


def main():
    parser = argparse.ArgumentParser(
        description="Production PDF Extraction Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract everything with default config
  python pdf_extraction.py document.pdf

  # Extract pages 138-147
  python pdf_extraction.py document.pdf --start-page 138 --end-page 147

  # Text + formulas only (no images)
  python pdf_extraction.py document.pdf --mode text_formulas

  # Text + images only (no formulas)
  python pdf_extraction.py document.pdf --mode text_images

  # Use custom config
  python pdf_extraction.py document.pdf --config custom_config.yaml
        """
    )

    parser.add_argument("pdf_path", help="Path to PDF file")
    parser.add_argument("--start-page", type=int, default=1, help="Start page (default: 1)")
    parser.add_argument("--end-page", type=int, default=None, help="End page (default: last page)")
    parser.add_argument(
        "--mode",
        choices=["text_only", "text_formulas", "text_images", "complete"],
        default="complete",
        help="Extraction mode (default: complete)"
    )
    parser.add_argument("--model", default="gpt-4o", help="Vision model (default: gpt-4o)")
    parser.add_argument("--config", default="extraction_config_unified.yaml", help="Config file path (default: extraction_config_unified.yaml)")
    parser.add_argument("--output-dir", default=".", help="Output directory")
    parser.add_argument("--output-prefix", default="extraction", help="Output file prefix")

    args = parser.parse_args()

    # Load config
    config = Config(args.config if Path(args.config).exists() else None)

    # Override with CLI args
    if args.mode:
        config.config["extraction_mode"] = args.mode
    if args.model:
        config.config["vision_model"] = args.model
    if args.output_dir != ".":
        config.config["output_directory"] = args.output_dir
    if args.output_prefix != "extraction":
        config.config["output_prefix"] = args.output_prefix

    # Validate PDF exists
    if not Path(args.pdf_path).exists():
        logger.error(f"PDF not found: {args.pdf_path}")
        sys.exit(1)

    # Run extraction
    try:
        result = asyncio.run(extract_pdf(
            args.pdf_path,
            start_page=args.start_page,
            end_page=args.end_page,
            config=config
        ))

        # Print summary
        print()
        print("=" * 70)
        print("EXTRACTION COMPLETE")
        print("=" * 70)
        print(f"Output file: {result['output_file']}")
        print(f"Mode: {result['mode']}")
        print(f"Pages processed: {result['pages']}")
        print(f"Formulas extracted: {result['formulas']}")
        print(f"Images described: {result['images']}")
        print()
        print("TIME BREAKDOWN:")
        print(f"  Docling (text + formulas):     {result['times']['docling']:6.1f}s")
        if result['times']['images'] > 0:
            print(f"  Image extraction (Vision LLM): {result['times']['images']:6.1f}s")
        if result['times']['formulas'] > 0:
            print(f"  Formula extraction (Vision):   {result['times']['formulas']:6.1f}s")
        print(f"  {'-' * 40}")
        print(f"  Total processing time:         {result['times']['total']:6.1f}s ({result['times']['total']/60:.1f}m)")
        print()
        print(f"VISION LLM COST: ${result['costs']['vision']:.6f}")
        print("=" * 70)

    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

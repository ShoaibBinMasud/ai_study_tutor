"""
Production-Ready Image Content Extraction Tool
==============================================

Extracts detailed content from images (PNG, JPEG, etc) using Vision LLM.
Ideal for: scientific plots, diagrams, screenshots, figures.

Features:
- Batch processing of multiple images
- Detailed structured extraction
- Markdown output
- Cost tracking and analysis
- Config file + CLI arguments
- Comprehensive logging
- Type hints and error handling

Usage:
    python image_extraction.py image.png
    python image_extraction.py *.png --model gpt-4o
    python image_extraction.py --config image_config.yaml image1.png image2.png
"""

import argparse
import base64
import glob
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional, Dict, List
from enum import Enum

from dotenv import load_dotenv
import openai
import yaml

# Load environment
load_dotenv()

# Constants
VISION_PRICING = {
    "input_tokens": 0.005 / 1000,
    "output_tokens": 0.015 / 1000,
}

SUPPORTED_FORMATS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


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
    """Configuration handler for image extraction."""

    DEFAULT_CONFIG = {
        "vision_model": "gpt-4o",
        "output_directory": ".",
        "output_format": "markdown",  # or "json"
        "log_level": "INFO",
        "max_tokens": 2000,
        "temperature": 0.1,
    }

    def __init__(self, config_file: Optional[str] = None) -> None:
        """Initialize configuration from file or defaults."""
        self.config = self.DEFAULT_CONFIG.copy()

        if config_file and Path(config_file).exists():
            try:
                with open(config_file, "r") as f:
                    file_config = yaml.safe_load(f) or {}

                if "image_extraction" in file_config:
                    # Unified config format
                    logger.info(f"Loaded configuration from {config_file} (unified format)")
                    image_config = file_config.get("image_extraction", {})
                    global_config = file_config.get("global", {})
                    self.config.update(global_config)
                    self.config.update(image_config)
                else:
                    # Legacy config format
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


def read_image_as_base64(image_path: str) -> str:
    """
    Read image file and convert to base64.

    Args:
        image_path: Path to image file

    Returns:
        Base64-encoded image string

    Raises:
        FileNotFoundError: If image doesn't exist
        IOError: If image cannot be read
    """
    path = Path(image_path)

    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    if path.suffix.lower() not in SUPPORTED_FORMATS:
        raise ValueError(f"Unsupported format: {path.suffix}. Supported: {', '.join(SUPPORTED_FORMATS)}")

    try:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except IOError as e:
        raise IOError(f"Failed to read image {image_path}: {e}")


def get_image_media_type(image_path: str) -> str:
    """Get MIME type for image."""
    suffix = Path(image_path).suffix.lower()
    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    return mime_types.get(suffix, "image/png")


def extract_image_content(
    image_path: str,
    model: str = "gpt-4o",
    max_tokens: int = 2000,
    temperature: float = 0.1,
) -> Dict:
    """
    Extract detailed content from image using Vision LLM.

    Args:
        image_path: Path to image file
        model: Vision model to use
        max_tokens: Maximum tokens in response
        temperature: Model temperature

    Returns:
        Dictionary with extracted content and metadata
    """
    logger.info(f"Processing {Path(image_path).name}...")

    try:
        image_b64 = read_image_as_base64(image_path)
        media_type = get_image_media_type(image_path)

        extraction_prompt = """You are a DETAILED FACTUAL content extractor for images (plots, diagrams, charts, screenshots, etc.).
Extract ONLY what is actually visible. NO interpretation.
Assume the reader CANNOT see the image - describe so they understand completely.

Extract:

1. **IMAGE TITLE/CAPTION** — Exact title shown if visible

2. **PLOTS/GRAPHS/CHARTS** — EXHAUSTIVE description:
   - Type (line plot, scatter, bar chart, histogram, spectrum, etc.)
   - Axes: labels (with units), ranges, scale (linear/log)
   - Data: curves/lines/points with colors, labels
   - Multiple datasets: how many, what each shows
   - Peaks, valleys, trends, patterns
   - Legends or annotations: exact text
   - All visible labels, values, data points

3. **DIAGRAMS/SCHEMATICS** — Detailed description:
   - Overall structure and composition
   - All elements and labels
   - Colors, shading, visual emphasis
   - Connections and relationships
   - Text and annotations

4. **TEXT AND LABELS** — Exact wording of:
   - Titles, subtitles
   - Axis labels
   - Legend entries
   - Annotations, captions

5. **VISUAL DETAILS**:
   - Colors of curves, areas, points
   - Line styles (solid, dashed, dotted)
   - Markers or symbols
   - Grid lines or reference lines
   - Visual emphasis or highlighting

NO SPECULATION. ONLY WHAT IS VISIBLE.

{
  "image_name": "filename",
  "image_type": "plot | diagram | chart | spectrum | screenshot | etc",
  "description": "VERY DETAILED description of the image content",
  "text_elements": {
    "title": "title if present",
    "axis_labels": {"x": "...", "y": "...", "units": "..."},
    "legend": ["entry 1", "entry 2"],
    "annotations": ["text 1", "text 2"]
  },
  "visual_elements": "Description of colors, styles, markers, emphasis"
}"""

        client = openai.OpenAI(api_key=__import__("os").getenv("OPENAI_API_KEY"))
        start_time = time.time()

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": extraction_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{image_b64}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )

        processing_time = time.time() - start_time

        # Parse response
        response_text = response.choices[0].message.content

        # Extract JSON from code blocks if needed
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        extracted = json.loads(response_text)

        # Calculate costs
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        total_tokens = input_tokens + output_tokens
        input_cost = input_tokens * VISION_PRICING["input_tokens"]
        output_cost = output_tokens * VISION_PRICING["output_tokens"]
        total_cost = input_cost + output_cost

        logger.info(f"  ✓ Completed in {processing_time:.1f}s ({input_tokens}↓ {output_tokens}↑ tokens)")

        return {
            "image_path": str(Path(image_path).absolute()),
            "image_name": Path(image_path).name,
            "content": extracted,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "input_cost": input_cost,
            "output_cost": output_cost,
            "total_cost": total_cost,
            "processing_time": processing_time,
        }

    except Exception as e:
        logger.error(f"Failed to extract {image_path}: {e}")
        return {
            "image_path": str(Path(image_path).absolute()),
            "image_name": Path(image_path).name,
            "error": str(e),
            "total_cost": 0.0,
            "processing_time": 0.0,
        }


def convert_to_markdown(result: Dict) -> str:
    """
    Convert extraction result to markdown.

    Args:
        result: Extraction result dictionary

    Returns:
        Formatted markdown string
    """
    if "error" in result:
        return f"# {result['image_name']}\n\n**Error:** {result['error']}\n"

    lines = []
    content = result.get("content", {})
    image_name = result.get("image_name", "Image")

    # Header
    lines.append(f"# {image_name}")
    lines.append("")

    # Image type
    img_type = content.get("image_type", "")
    if img_type:
        lines.append(f"**Type:** {img_type}")
        lines.append("")

    # Main description
    description = content.get("description", "")
    if description:
        lines.append("## Content Description")
        lines.append(description)
        lines.append("")

    # Text elements
    text_elements = content.get("text_elements", {})
    if text_elements:
        lines.append("## Labels & Text")

        title = text_elements.get("title", "")
        if title:
            lines.append(f"**Title:** {title}")
            lines.append("")

        axis_labels = text_elements.get("axis_labels", {})
        if axis_labels:
            lines.append("**Axes:**")
            if axis_labels.get("x"):
                x_units = f" ({axis_labels.get('units', '')})" if axis_labels.get("units") else ""
                lines.append(f"- X: {axis_labels.get('x')}{x_units}")
            if axis_labels.get("y"):
                lines.append(f"- Y: {axis_labels.get('y')}")
            lines.append("")

        legend = text_elements.get("legend", [])
        if legend:
            lines.append("**Legend:**")
            for entry in legend:
                lines.append(f"- {entry}")
            lines.append("")

        annotations = text_elements.get("annotations", [])
        if annotations:
            lines.append("**Annotations:**")
            for annotation in annotations:
                lines.append(f"- {annotation}")
            lines.append("")

    # Visual elements
    visual = content.get("visual_elements", "")
    if visual:
        lines.append("## Visual Details")
        lines.append(visual)
        lines.append("")

    return "\n".join(lines)


def expand_image_paths(paths: List[str]) -> List[str]:
    """
    Expand glob patterns and validate image paths.

    Args:
        paths: List of image paths (may contain glob patterns)

    Returns:
        List of valid image file paths

    Raises:
        ValueError: If no valid images found
    """
    expanded = []

    for path_pattern in paths:
        if "*" in path_pattern:
            # Glob pattern
            matches = glob.glob(path_pattern, recursive=True)
            expanded.extend([p for p in matches if Path(p).suffix.lower() in SUPPORTED_FORMATS])
        else:
            # Single file
            if Path(path_pattern).suffix.lower() in SUPPORTED_FORMATS:
                expanded.append(path_pattern)

    if not expanded:
        raise ValueError("No valid image files found")

    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for path in expanded:
        abs_path = str(Path(path).absolute())
        if abs_path not in seen:
            seen.add(abs_path)
            unique.append(path)

    return unique


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Extract detailed content from images using Vision LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract single image
  python image_extraction.py plot.png

  # Extract multiple images
  python image_extraction.py image1.png image2.png image3.jpeg

  # Extract all PNGs in directory (glob pattern)
  python image_extraction.py "diagrams/*.png"

  # Use custom model
  python image_extraction.py image.png --model gpt-4o-mini

  # Use config file
  python image_extraction.py --config custom.yaml plot.png
        """
    )

    parser.add_argument("images", nargs="+", help="Image file(s) or glob pattern(s)")
    parser.add_argument("--model", default="gpt-4o", help="Vision model (default: gpt-4o)")
    parser.add_argument("--config", default="extraction_config_unified.yaml", help="Config file path (default: extraction_config_unified.yaml)")
    parser.add_argument("--output-dir", default=".", help="Output directory")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")

    args = parser.parse_args()

    # Load config
    config = Config(args.config)
    setup_logging(config["log_level"])

    # Override with CLI args
    if args.model:
        config.config["vision_model"] = args.model
    if args.format:
        config.config["output_format"] = args.format

    try:
        # Expand image paths
        image_paths = expand_image_paths(args.images)
        logger.info(f"Found {len(image_paths)} image(s) to process")

        # Process images
        results = []
        total_cost = 0.0
        total_time = 0.0
        total_tokens = 0

        for image_path in image_paths:
            result = extract_image_content(
                image_path,
                model=config["vision_model"],
                max_tokens=config["max_tokens"],
                temperature=config["temperature"],
            )
            results.append(result)

            if "error" not in result:
                total_cost += result["total_cost"]
                total_time += result["processing_time"]
                total_tokens += result["total_tokens"]

        # Save outputs
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        for result in results:
            image_name = Path(result["image_name"]).stem

            if config["output_format"] == "markdown":
                markdown = convert_to_markdown(result)
                output_file = output_dir / f"{image_name}_extracted.md"
                output_file.write_text(markdown, encoding="utf-8")
            else:
                output_file = output_dir / f"{image_name}_extracted.json"
                with open(output_file, "w") as f:
                    json.dump(result, f, indent=2)

            logger.info(f"Saved: {output_file}")

        # Print summary
        print()
        print("=" * 70)
        print("IMAGE EXTRACTION COMPLETE")
        print("=" * 70)
        print(f"Images processed: {len(image_paths)}")
        print(f"Output directory: {output_dir}")
        print()
        print(f"Tokens: {total_tokens:,}")
        print(f"Time: {total_time:.1f}s")
        print(f"Cost: ${total_cost:.6f}")
        print("=" * 70)

    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

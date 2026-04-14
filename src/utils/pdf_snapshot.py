"""
PDF Page Snapshot and LLM Extraction Tool

Takes snapshots of specific PDF pages, sends them to a vision LLM (Llama 4 Scout),
and extracts all information as structured markdown.

Usage:
    from pdf_snapshot import PDFSnapshotExtractor
    
    extractor = PDFSnapshotExtractor(
        pdf_path="modern_physics.pdf",
        username="m8yl",
        password="Fl33ll66"
    )
    
    # Extract pages 64 and 67
    extractor.extract_pages([64, 67], output_dir="output")
"""

import os
import base64
from pathlib import Path
from typing import List, Optional, Tuple
import fitz  # PyMuPDF
from PIL import Image
import io
import requests
import json


class PDFSnapshotExtractor:
    """
    Extracts PDF pages as images and uses Llama 4 Scout Vision to extract content as markdown.
    """
    
    def __init__(
        self,
        pdf_path: str,
        username: str = "m8yl",
        password: str = "Fl33ll66",
        api_url: Optional[str] = None
    ):
        """
        Initialize the PDF Snapshot Extractor.
        
        Args:
            pdf_path: Path to the PDF file
            username: API username (default: m8yl)
            password: API password (default: Fl33ll66)
            api_url: Llama API endpoint (default: Llama-4-Scout-17B-16E-Instruct)
        """
        self.pdf_path = pdf_path
        self.doc = fitz.open(pdf_path)
        
        # Configure Llama API
        if not api_url:
            api_url = "https://smapi-int-tsta.bcbsfl.com/gpt/api/v1/models/meta-llama/Llama-4-Scout-17B-16E-Instruct/v1/chat/completions"
        
        self.api_url = api_url
        self.auth = (username, password)
        
        print(f"[OK] PDFSnapshotExtractor initialized")
        print(f"  PDF: {pdf_path} ({len(self.doc)} pages)")
        print(f"  Model: Llama-4-Scout-17B-16E-Instruct")
        print(f"  API: {api_url}")
    
    def render_page_as_image(self, page_num: int, dpi: int = 150) -> Image.Image:
        """
        Render a PDF page as a PIL Image.
        
        Args:
            page_num: Page number (1-indexed)
            dpi: Resolution for rendering (default: 150 DPI)
        
        Returns:
            PIL Image object
        """
        # Convert to 0-indexed
        page_idx = page_num - 1
        
        if page_idx < 0 or page_idx >= len(self.doc):
            raise ValueError(f"Page {page_num} out of range (1-{len(self.doc)})")
        
        # Get page and render as pixmap
        page = self.doc[page_idx]
        zoom = dpi / 72  # PDF is 72 DPI by default
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        
        # Convert to PIL Image
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        
        print(f"  ✓ Rendered page {page_num} at {dpi} DPI ({img.width}x{img.height})")
        return img
    
    def _image_to_base64(self, image: Image.Image) -> str:
        """Convert PIL Image to base64 string."""
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        img_bytes = buffered.getvalue()
        return base64.b64encode(img_bytes).decode('utf-8')
    
    def extract_content_from_image(self, image: Image.Image, page_num: int) -> str:
        """
        Send page image to Llama Vision and extract content as markdown.
        
        Args:
            image: PIL Image of the page
            page_num: Page number for context
        
        Returns:
            Extracted content as markdown string
        """
        prompt = f"""You are analyzing page {page_num} from an academic textbook.

**TASK**: Extract ALL information from this page into well-structured markdown format.

**REQUIREMENTS**:
1. **Preserve structure**: Maintain headings, sections, subsections
2. **Include all text**: Chapters, sections, body text, examples, captions
3. **Format equations**: 
   - Use LaTeX notation in $...$ or $$...$$ blocks
   - **IMPORTANT**: Include equation numbers if visible (e.g., (1-39), (1-40))
   - Place equation numbers on the same line as the equation, aligned to the right
4. **Tables**: Convert to markdown tables
5. **Lists**: Use proper markdown list formatting
6. **Images/Figures**: When you see a figure:
   - First, write a detailed description paragraph explaining all visual elements
   - Then, immediately after the description, add `![Figure number and full caption](figure-X-description)`
7. **Callouts/Boxes**: Use blockquotes (>) for special boxes
8. **Page metadata**: Start with page number and any chapter/section info

**EQUATION FORMAT EXAMPLE**:
```markdown
$$
\\frac{{\\Delta x'}}{{c\\Delta t'}} = \\cos \\theta' \\quad \\text{{(1-39)}}
$$

$$
\\cos \\theta = \\frac{{\\cos \\theta' + \\beta}}{{1 + \\beta \\cos \\theta'}} \\quad \\text{{(1-41)}}
$$
```

**FIGURE FORMAT EXAMPLE**:
```markdown
The diagrams show three parts: (a) illustrates a runner with a 10-meter pole approaching a 5-meter barn, (b) presents the spacetime diagram from the farmer's reference frame where the pole appears contracted to fit inside the barn, and (c) shows the spacetime diagram from the runner's reference frame where the barn appears contracted. The worldlines represent the front and back of the pole and the barn doors, with large dots marking simultaneous events that demonstrate how simultaneity is relative between reference frames.

![Figure 1-37: (a) A runner carrying a 10-m pole moves quickly enough so that the farmer will see the pole entirely contained in the barn. The spacetime diagrams from the point of view of the farmer's inertial frame (b) and that of the runner (c). The resolution of the paradox is in the fact that the events of interest, shown by the large dots in each diagram, are simultaneous in S but not in S'.](spacetime-diagram-runner-barn-paradox)
```

**OUTPUT FORMAT**:
```markdown
# Page {page_num}

## Chapter/Section Title (if visible)

[Body text and content...]

[Detailed paragraph describing all visual elements, parts, labels, what the figure demonstrates]

![Figure X: Complete caption text](brief-descriptive-name)

$$
[Equations in LaTeX] \\quad \\text{{(equation-number)}}
$$

> **Note**: [Callout boxes]
```

Extract everything visible on this page. For every figure/diagram, write the detailed description first, then the image markdown with complete caption. For every equation, check if there's an equation number (like (1-39)) and include it."""

        try:
            print(f"  → Sending page {page_num} to Llama Vision...")
            
            # Convert image to base64
            image_base64 = self._image_to_base64(image)
            
            # Prepare OpenAI-compatible message format
            payload = {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_base64}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 6000,  # Increased for detailed image descriptions
                "temperature": 0.1
            }
            
            headers = {
                "Content-Type": "application/json"
            }
            
            # Call Llama API
            response = requests.post(
                self.api_url,
                json=payload,
                headers=headers,
                auth=self.auth,
                timeout=120
            )
            response.raise_for_status()
            
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            if not content:
                return f"# Page {page_num}\n\n*No content extracted*"
            
            print(f"  ✓ Extracted {len(content)} characters")
            return content
        
        except requests.exceptions.RequestException as e:
            error_msg = f"# Page {page_num}\n\n**Error**: API request failed: {str(e)}"
            print(f"  ✗ Error extracting content: {str(e)}")
            return error_msg
        
        except Exception as e:
            error_msg = f"# Page {page_num}\n\n**Error**: {str(e)}"
            print(f"  ✗ Error extracting content: {str(e)}")
            return error_msg
    
    def extract_page(self, page_num: int, output_dir: str = "output") -> str:
        """
        Extract a single page: render as image and extract content.
        
        Args:
            page_num: Page number (1-indexed)
            output_dir: Directory to save results
        
        Returns:
            Path to the saved markdown file
        """
        print(f"\n{'='*80}")
        print(f"Processing Page {page_num}")
        print(f"{'='*80}")
        
        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Render page as image
        image = self.render_page_as_image(page_num, dpi=150)
        
        # Save snapshot
        snapshot_path = output_path / f"page_{page_num}_snapshot.png"
        image.save(snapshot_path, "PNG")
        print(f"  ✓ Saved snapshot: {snapshot_path}")
        
        # Extract content using Gemini
        markdown_content = self.extract_content_from_image(image, page_num)
        
        # Save markdown
        markdown_path = output_path / f"page_{page_num}_content.md"
        with open(markdown_path, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        print(f"  ✓ Saved markdown: {markdown_path}")
        
        return str(markdown_path)
    
    def extract_pages(
        self,
        page_numbers: List[int],
        output_dir: str = "output",
        create_combined: bool = True
    ) -> List[str]:
        """
        Extract multiple pages and optionally create a combined markdown file.
        
        Args:
            page_numbers: List of page numbers to extract (1-indexed)
            output_dir: Directory to save results
            create_combined: Whether to create a combined markdown file
        
        Returns:
            List of paths to saved markdown files
        """
        print(f"\n{'='*80}")
        print(f"PDF Snapshot Extraction")
        print(f"{'='*80}")
        print(f"PDF: {self.pdf_path}")
        print(f"Pages: {page_numbers}")
        print(f"Output: {output_dir}")
        print(f"{'='*80}\n")
        
        markdown_files = []
        all_content = []
        
        for page_num in page_numbers:
            try:
                md_path = self.extract_page(page_num, output_dir)
                markdown_files.append(md_path)
                
                # Read content for combined file
                with open(md_path, "r", encoding="utf-8") as f:
                    all_content.append(f.read())
            
            except Exception as e:
                print(f"\n✗ Failed to process page {page_num}: {str(e)}")
                continue
        
        # Create combined markdown file
        if create_combined and all_content:
            combined_path = Path(output_dir) / "combined_pages.md"
            with open(combined_path, "w", encoding="utf-8") as f:
                pdf_name = Path(self.pdf_path).name
                f.write(f"# Extracted Pages from {pdf_name}\n\n")
                f.write(f"**Pages**: {', '.join(map(str, page_numbers))}\n\n")
                f.write("---\n\n")
                f.write("\n\n---\n\n".join(all_content))
            
            print(f"\n{'='*80}")
            print(f"✓ Created combined file: {combined_path}")
            markdown_files.append(str(combined_path))
        
        print(f"\n{'='*80}")
        print(f"Extraction Complete!")
        print(f"  Pages processed: {len(page_numbers)}")
        print(f"  Files created: {len(markdown_files)}")
        print(f"{'='*80}\n")
        
        return markdown_files
    
    def __del__(self):
        """Clean up: close PDF document."""
        if hasattr(self, 'doc'):
            self.doc.close()


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    """Command-line interface for PDF snapshot extraction."""
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Extract PDF pages as images and convert to markdown using Llama Vision"
    )
    parser.add_argument("pdf_path", help="Path to PDF file")
    parser.add_argument(
        "pages",
        type=int,
        nargs="+",
        help="Page numbers to extract (e.g., 64 67 100)"
    )
    parser.add_argument(
        "-o", "--output",
        default="output",
        help="Output directory (default: output)"
    )
    parser.add_argument(
        "-u", "--username",
        default="m8yl",
        help="API username (default: m8yl)"
    )
    parser.add_argument(
        "-p", "--password",
        default="Fl33ll66",
        help="API password (default: Fl33ll66)"
    )
    parser.add_argument(
        "--no-combined",
        action="store_true",
        help="Don't create combined markdown file"
    )
    
    args = parser.parse_args()
    
    # Check if PDF exists
    if not os.path.exists(args.pdf_path):
        print(f"Error: PDF not found: {args.pdf_path}")
        sys.exit(1)
    
    # Initialize extractor
    try:
        extractor = PDFSnapshotExtractor(
            pdf_path=args.pdf_path,
            username=args.username,
            password=args.password
        )
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    
    # Extract pages
    extractor.extract_pages(
        page_numbers=args.pages,
        output_dir=args.output,
        create_combined=not args.no_combined
    )


if __name__ == "__main__":
    main()

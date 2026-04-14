"""
Document Scanner — entry point

Usage:
    python scan_documents.py doc1.pdf doc2.pdf notes.txt
    python scan_documents.py /path/to/folder/*.pdf
"""

import sys
import os
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from dotenv import load_dotenv
load_dotenv()

from agents.document_scanner_agent import DocumentScannerAgent

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scan_documents.py file1.pdf file2.pdf ...")
        print("       python scan_documents.py /folder/containing/docs/")
        sys.exit(1)

    # Collect files — support passing a folder or individual files
    file_paths = []
    for arg in sys.argv[1:]:
        p = Path(arg)
        if p.is_dir():
            # Grab all PDFs and text files in the folder
            for ext in ("*.pdf", "*.txt", "*.md"):
                file_paths.extend(str(f) for f in p.glob(ext))
        elif p.exists():
            file_paths.append(str(p))
        else:
            print(f"Warning: '{arg}' not found, skipping.")

    if not file_paths:
        print("No valid files found.")
        sys.exit(1)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not set. Add it to your .env file.")
        sys.exit(1)

    agent = DocumentScannerAgent(api_key=api_key)

    print(f"\nScanning {len(file_paths)} document(s)...\n")
    result = agent.scan(file_paths)

    print("\n" + "=" * 70)
    print(result)
    print("=" * 70)


if __name__ == "__main__":
    main()

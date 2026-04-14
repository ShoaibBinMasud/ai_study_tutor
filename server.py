"""
FastAPI backend for the AI STEM Tutor.
Wraps TutorAgent and exposes a simple REST API consumed by the React frontend.
"""

import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

sys.path.insert(0, str(Path(__file__).parent / "src"))

from agents.tutor_agent import TutorAgent

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="AI STEM Tutor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global tutor instance (one per server process) ────────────────────────────

_tutor: Optional[TutorAgent] = None


def _get_tutor() -> TutorAgent:
    global _tutor
    if _tutor is None:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise HTTPException(500, "No API key configured. Set OPENAI_API_KEY in .env")
        model = os.getenv("TUTOR_MODEL", "gpt-4o-mini")
        _tutor = TutorAgent(api_key=api_key, model=model)
    return _tutor


# ── Request / Response models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    text: str
    diagram: Optional[str] = None   # SVG string, or None


class UploadResponse(BaseModel):
    text: str                        # Welcome message from agent
    diagram: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload", response_model=UploadResponse)
async def upload(files: list[UploadFile] = File(...)):
    """Upload study materials. Returns the agent's welcome message."""
    global _tutor
    _tutor = None  # fresh tutor on each upload

    tutor = _get_tutor()
    saved_paths = []

    try:
        for f in files:
            suffix = Path(f.filename).suffix
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(await f.read())
            tmp.close()
            saved_paths.append(tmp.name)

        welcome = tutor.load_files(saved_paths)
        return UploadResponse(text=welcome)

    except Exception as e:
        logging.error(f"Upload error: {e}", exc_info=True)
        raise HTTPException(500, str(e))


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Send a student message. Returns text response + optional SVG diagram."""
    try:
        tutor = _get_tutor()
        text, diagram = tutor.chat(req.message)
        return ChatResponse(text=text or "", diagram=diagram)
    except Exception as e:
        logging.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(500, str(e))


@app.post("/reset")
def reset():
    """Reset the tutor session."""
    global _tutor
    _tutor = None
    return {"status": "reset"}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)

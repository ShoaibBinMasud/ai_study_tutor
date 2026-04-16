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

from agents.supervisor import Supervisor

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="AI STEM Tutor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global supervisor instance (one per server process) ───────────────────────

_supervisor: Optional[Supervisor] = None


def _get_supervisor() -> Supervisor:
    global _supervisor
    if _supervisor is None:
        from utils.llm_client import LLMClient
        from utils.gemini_client import GeminiLLMClient

        session_dir = tempfile.mkdtemp(prefix="tutor_session_")
        _supervisor = Supervisor(
            llm_client=LLMClient(),
            gemini_client=GeminiLLMClient(),
            session_dir=session_dir,
        )
    return _supervisor


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
    """Upload study materials. Runs extract → plan → teach pipeline."""
    global _supervisor
    _supervisor = None  # fresh supervisor on each upload

    supervisor = _get_supervisor()
    saved_paths = []

    try:
        for f in files:
            suffix = Path(f.filename).suffix
            tmp = tempfile.NamedTemporaryFile(
                delete=False, suffix=suffix, dir=supervisor.session_dir
            )
            tmp.write(await f.read())
            tmp.close()
            saved_paths.append(tmp.name)

        welcome = supervisor.upload(saved_paths)
        return UploadResponse(text=welcome)

    except Exception as e:
        logging.error(f"Upload error: {e}", exc_info=True)
        raise HTTPException(500, str(e))


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Send a student message. Routes through supervisor to active tutor."""
    try:
        supervisor = _get_supervisor()
        text = supervisor.chat(req.message)
        return ChatResponse(text=text or "", diagram=None)
    except Exception as e:
        logging.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(500, str(e))


@app.post("/reset")
def reset():
    """Reset the supervisor session."""
    global _supervisor
    _supervisor = None
    return {"status": "reset"}


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)

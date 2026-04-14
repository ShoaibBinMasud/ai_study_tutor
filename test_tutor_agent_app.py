"""
Test app for TutorAgent — the main orchestrator that wires everything together.

What TutorAgent does:
  1. Loads study materials (PDFs, PPTX, DOCX, images) via FileManager
  2. On every student message, decides what to do next via an LLM + tool loop:
       show_toc        → display what's available
       load_chapter    → find all sections in a chapter, build a teaching queue
       load_section    → extract content + reference card for a section
       teach_chunk     → hand off to TeachingAgent to start a lesson
       forward_to_teaching_agent → route student replies during active teaching
       run_quiz        → generate + run a quiz after teaching ends
       run_diagnostic  → prereq assessment for exam prep mode
       search_topic    → find sections covering a concept
       get_progress    → merit score, pace, sections done
  3. Three fast paths bypass the main LLM for hot loops:
       Fast path 1: teaching_active  → all messages go to TeachingAgent directly
       Fast path 2: quiz_ready       → waiting for yes/skip, no LLM needed
       Fast path 3: quiz_active      → evaluate answers via QuizAgent directly
  4. Session state persists across turns: merit score, sections taught, chapter queue

Run:
    python test_tutor_agent_app.py
"""

import os
import sys
import shutil
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import gradio as gr
from dotenv import load_dotenv

load_dotenv()

from agents.tutor_agent import TutorAgent

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

_tutor: TutorAgent | None = None
_upload_dir = os.path.join(tempfile.gettempdir(), "tutor_agent_test")
os.makedirs(_upload_dir, exist_ok=True)
_uploaded_paths: list[str] = []


def get_tutor() -> TutorAgent:
    global _tutor
    if _tutor is None:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        _tutor = TutorAgent(api_key=api_key, model="gpt-4o-mini")
    return _tutor


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def handle_upload(files):
    global _uploaded_paths, _tutor

    if not files:
        return "No files uploaded.", [], []

    _uploaded_paths = []
    for f in files:
        dest = os.path.join(_upload_dir, os.path.basename(f.name))
        shutil.copy(f.name, dest)
        _uploaded_paths.append(dest)

    # Fresh tutor on every upload
    _tutor = None

    try:
        tutor = get_tutor()
        welcome_text, _ = tutor.load_files(_uploaded_paths)
    except Exception as e:
        welcome_text = f"Error loading files: {e}"

    file_names = [os.path.basename(p) for p in _uploaded_paths]
    history = [{"role": "assistant", "content": welcome_text}]
    return f"Loaded {len(_uploaded_paths)} file(s).", file_names, history


def handle_chat(message: str, history: list):
    if not message.strip():
        return history, ""

    tutor = get_tutor()

    if not _uploaded_paths:
        history = history + [
            {"role": "user", "content": message},
            {"role": "assistant", "content": "Please upload study materials first."},
        ]
        return history, ""

    try:
        response_text, image_path = tutor.chat(message)
    except Exception as e:
        response_text = f"Error: {e}"
        image_path = None

    history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": response_text},
    ]
    return history, ""


def handle_reset():
    global _tutor, _uploaded_paths
    _tutor = None
    _uploaded_paths = []
    return [], "Session reset. Upload files to start a new session."


def get_session_state():
    if _tutor is None:
        return "No active session."
    s = _tutor.session
    lines = [
        f"**Merit score:** {s['merit_score']:.1f}/10",
        f"**Adaptation:** {s['adaptation']}",
        f"**Teaching active:** {s['teaching_active']}",
        f"**Quiz ready:** {s['quiz_ready']}",
        f"**Quiz active:** {s['quiz_active']}",
        f"**Chapter mode:** {s['chapter_mode']}",
        f"**Loaded section:** {s.get('loaded_section_id', 'none')}",
        f"**Sections completed:** {s.get('sections_completed', [])}",
        f"**Chunks:** {s.get('chunk_index', 0)}/{len(s.get('chunks', []))}",
    ]
    if s["chapter_mode"]:
        lines += [
            f"**Chapter:** {s.get('chapter_id')}",
            f"**Queue:** {s.get('chapter_section_queue', [])}",
            f"**Sections done:** {s.get('chapter_sections_done', [])}",
        ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

EXAMPLE_MESSAGES = [
    "What topics are covered in the uploaded materials?",
    "Teach me section 1-1",
    "Teach me chapter 3",
    "I have an exam tomorrow — help me prepare",
    "I want to understand Newton's second law",
    "yes",
    "no, I didn't understand the derivation",
    "Can you explain it differently?",
    "Show me my progress",
]

with gr.Blocks(title="TutorAgent Test") as app:
    gr.Markdown(
        "# TutorAgent Test\n"
        "Upload study materials → chat naturally → the agent decides what to teach, when to quiz, how to adapt."
    )

    with gr.Row():
        # Left panel: upload + session state
        with gr.Column(scale=1):
            gr.Markdown("## Upload Materials")
            file_input = gr.File(
                label="Study Materials",
                file_count="multiple",
                file_types=[".pdf", ".pptx", ".docx", ".png", ".jpg", ".jpeg", ".txt", ".md"],
            )
            upload_btn = gr.Button("Load Files", variant="primary")
            upload_status = gr.Markdown("No files loaded.")
            file_list = gr.Dropdown(label="Loaded Files", choices=[], multiselect=True, interactive=False)

            gr.Markdown("---")
            gr.Markdown("## Session State")
            refresh_state_btn = gr.Button("Refresh State", variant="secondary", size="sm")
            session_state_display = gr.Markdown("No active session.")

            gr.Markdown("---")
            reset_btn = gr.Button("Reset Session", variant="stop")

        # Right panel: chat
        with gr.Column(scale=2):
            chatbot = gr.Chatbot(
                label="Tutor Session",
                height=540,
                sanitize_html=False,
                latex_delimiters=[
                    {"left": "$$", "right": "$$", "display": True},
                    {"left": "$", "right": "$", "display": False},
                ],
            )

            with gr.Row():
                msg_input = gr.Textbox(
                    placeholder='e.g. "Teach me section 2-1" or just "yes" / "no"...',
                    label="Your message",
                    scale=4,
                    show_label=False,
                )
                send_btn = gr.Button("Send", variant="primary", scale=1)

            gr.Examples(
                examples=[[m] for m in EXAMPLE_MESSAGES],
                inputs=[msg_input],
                label="Quick inputs",
            )

    # Events
    upload_btn.click(
        handle_upload,
        inputs=[file_input],
        outputs=[upload_status, file_list, chatbot],
    )

    send_btn.click(
        handle_chat,
        inputs=[msg_input, chatbot],
        outputs=[chatbot, msg_input],
    )

    msg_input.submit(
        handle_chat,
        inputs=[msg_input, chatbot],
        outputs=[chatbot, msg_input],
    )

    refresh_state_btn.click(get_session_state, outputs=[session_state_display])

    reset_btn.click(
        handle_reset,
        outputs=[chatbot, upload_status],
    )


if __name__ == "__main__":
    print("Starting TutorAgent Test App...")
    print("Open http://localhost:7863 in your browser")
    print()
    app.launch(share=False, server_port=7863, theme=gr.themes.Soft())

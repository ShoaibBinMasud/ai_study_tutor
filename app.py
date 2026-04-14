"""
Simple Gradio UI for testing the AI STEM Tutor.

Usage:
    python app.py
"""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Configure logging so we see all INFO from our modules
logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

sys.path.insert(0, str(Path(__file__).parent / "src"))

import gradio as gr
from agents.tutor_agent import TutorAgent
from agents.document_scanner_agent import DocumentScannerAgent

# ── Global tutor instance ─────────────────────────────────────────────────────

_tutor: TutorAgent | None = None


def _get_or_create_tutor() -> TutorAgent:
    global _tutor
    if _tutor is None:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("No API key found. Set OPENAI_API_KEY in .env")
        model = os.getenv("TUTOR_MODEL", "gpt-4o-mini")
        _tutor = TutorAgent(api_key=api_key, model=model)
    return _tutor


# ── Handlers ──────────────────────────────────────────────────────────────────

def handle_upload(files, history):
    if not files:
        return history or [], "No files selected."

    global _tutor
    _tutor = None  # fresh tutor on each upload
    tutor = _get_or_create_tutor()

    # Resolve file paths — Gradio 6 returns NamedString (str subclass)
    file_paths = []
    for f in files:
        # Try str(f) first (Gradio 6), then f.name (Gradio 4/5)
        for candidate in [str(f), getattr(f, "name", None), getattr(f, "path", None)]:
            if candidate and os.path.isfile(candidate):
                file_paths.append(candidate)
                break
        else:
            print(f"[WARN] Could not resolve path for uploaded file: {repr(f)}")

    if not file_paths:
        return history or [], "Could not resolve any file paths from upload."

    print(f"[FILE PATHS] {file_paths}")

    try:
        response = tutor.load_files(file_paths)
    except Exception as e:
        import traceback
        traceback.print_exc()
        response = f"Error loading files: {e}"

    history = history or []
    history.append({"role": "assistant", "content": response})
    return history, f"Loaded {len(file_paths)} file(s)"


def handle_message(user_input, history):
    if not user_input.strip():
        return history or [], ""

    tutor = _get_or_create_tutor()
    history = history or []
    history.append({"role": "user", "content": user_input})

    try:
        response, image_path = tutor.chat(user_input)
    except Exception as e:
        import traceback
        traceback.print_exc()
        response, image_path = f"Error: {e}", None

    history.append({"role": "assistant", "content": response})
    viz = image_path if (image_path and os.path.exists(image_path)) else None
    return history, "", viz


def reset_session():
    global _tutor
    _tutor = None
    return [], "Session reset. Upload a file to start."


def handle_scan(files):
    if not files:
        return "No files selected."

    file_paths = []
    for f in files:
        for candidate in [str(f), getattr(f, "name", None), getattr(f, "path", None)]:
            if candidate and os.path.isfile(candidate):
                file_paths.append(candidate)
                break

    if not file_paths:
        return "Could not resolve any file paths from upload."

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return "No API key found. Set OPENAI_API_KEY in .env"

    model = os.getenv("TUTOR_MODEL", "gpt-4o-mini")
    try:
        agent = DocumentScannerAgent(api_key=api_key, model=model)
        return agent.scan(file_paths)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error: {e}"


# ── UI ────────────────────────────────────────────────────────────────────────

with gr.Blocks(title="AI STEM Tutor") as demo:
    gr.Markdown("## AI STEM Tutor")

    with gr.Tabs():
        with gr.Tab("Tutor"):
            with gr.Row():
                with gr.Column(scale=1):
                    file_input = gr.File(
                        label="Upload study material",
                        file_count="multiple",
                        file_types=[".pdf", ".txt", ".md", ".pptx", ".docx", ".png", ".jpg"],
                    )
                    upload_btn = gr.Button("Load Files", variant="primary")
                    reset_btn = gr.Button("Reset Session", variant="secondary")
                    status = gr.Textbox(label="Status", interactive=False, lines=1)

                with gr.Column(scale=3):
                    chatbot = gr.Chatbot(label="Tutor", height=460)
                    with gr.Row():
                        msg_input = gr.Textbox(
                            placeholder="'teach me section 1-2', 'what's in chapter 3?', ...",
                            show_label=False,
                            scale=9,
                        )
                        send_btn = gr.Button("Send", scale=1, variant="primary")
                    viz_panel = gr.Image(
                        label="Visualization",
                        visible=False,
                        height=320,
                    )

            def _send(user_input, history):
                history, cleared, viz = handle_message(user_input, history)
                show = viz is not None
                return history, cleared, gr.update(value=viz, visible=show)

            upload_btn.click(handle_upload, inputs=[file_input, chatbot], outputs=[chatbot, status])
            send_btn.click(_send, inputs=[msg_input, chatbot], outputs=[chatbot, msg_input, viz_panel])
            msg_input.submit(_send, inputs=[msg_input, chatbot], outputs=[chatbot, msg_input, viz_panel])
            reset_btn.click(reset_session, outputs=[chatbot, status])

        with gr.Tab("Document Scanner"):
            gr.Markdown("Upload one or more documents. The agent will read the first few pages of each and return a summary table.")
            with gr.Row():
                with gr.Column(scale=1):
                    scan_files = gr.File(
                        label="Upload documents",
                        file_count="multiple",
                        file_types=[".pdf", ".txt", ".md"],
                    )
                    scan_btn = gr.Button("Scan Documents", variant="primary")
                with gr.Column(scale=3):
                    scan_output = gr.Markdown(label="Scan Results")

            scan_btn.click(handle_scan, inputs=[scan_files], outputs=[scan_output])


if __name__ == "__main__":
    demo.launch(share=False, inbrowser=True, theme=gr.themes.Soft())

"""
Test app for DocumentScannerAgent + DocumentAgent.

Run:
    python test_document_agent_app.py
"""

import os
import sys
import shutil
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import gradio as gr
from dotenv import load_dotenv

load_dotenv()

from utils.llm_client import LLMClient
from agents.document_scanner_agent import DocumentScannerAgent
from agents.document_agent import DocumentAgent
from utils.trace_logger import TraceLogger

# ---------------------------------------------------------------------------
# Global state (per session)
# ---------------------------------------------------------------------------

_llm = None
_scanner = None
_agent = None
_scan_report = None
_uploaded_paths = []
_upload_dir = os.path.join(tempfile.gettempdir(), "doc_agent_test")
os.makedirs(_upload_dir, exist_ok=True)


def get_llm():
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm


def get_scanner():
    global _scanner
    if _scanner is None:
        _scanner = DocumentScannerAgent(get_llm())
    return _scanner


def get_agent():
    global _agent
    if _agent is None:
        _agent = DocumentAgent(get_llm())
    return _agent


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def handle_upload(files):
    """Copy uploaded files to temp dir and run the scanner."""
    global _scan_report, _uploaded_paths, _agent

    if not files:
        return "No files uploaded.", "", []

    # Copy files to stable paths
    _uploaded_paths = []
    for f in files:
        dest = os.path.join(_upload_dir, os.path.basename(f.name))
        shutil.copy(f.name, dest)
        _uploaded_paths.append(dest)

    # Reset agent so it re-registers scan entries
    _agent = DocumentAgent(get_llm())

    # Run scanner
    try:
        _scan_report = get_scanner().scan(_uploaded_paths)
    except Exception as e:
        return f"Scanner error: {e}", "", _uploaded_paths

    # Register scan with agent
    get_agent().register_scan(_scan_report)

    # Format scan results as markdown
    lines = ["## Scan Results\n"]
    lines.append("| File | Type | Pages | Scanned | Has TOC |")
    lines.append("|------|------|-------|---------|---------|")
    for e in _scan_report.entries:
        lines.append(
            f"| {e.file_name} | {e.file_type} | {e.total_pages} "
            f"| {e.is_scanned} | {e.has_toc} |"
        )

    lines.append(f"\n**Collection:** {_scan_report.collection_summary}")

    file_names = [os.path.basename(p) for p in _uploaded_paths]
    return "\n".join(lines), "", file_names


def handle_ask(question, history):
    """Run DocumentAgent to extract content based on the question."""
    global _uploaded_paths

    if not _uploaded_paths:
        history = history or []
        history.append((question, "Please upload files first."))
        return history, "", ""

    if not question.strip():
        return history, "", ""

    try:
        result = get_agent().extract(_uploaded_paths, question)
        agent = get_agent()
        trace_text = ""
        if agent.last_trace:
            trace_text = agent.tracer.format_trace(agent.last_trace)
    except Exception as e:
        result = f"Error: {e}"
        trace_text = f"Error: {e}"

    history = history or []
    history.append((question, result))
    return history, "", trace_text


def handle_clear():
    """Reset everything."""
    global _scan_report, _uploaded_paths, _agent, _scanner
    _scan_report = None
    _uploaded_paths = []
    _agent = None
    _scanner = None
    return "", "", [], "", ""


def load_trace_list():
    """Get list of saved traces and return choices."""
    logger = TraceLogger()
    traces = logger.list_traces()
    if not traces:
        return gr.Dropdown(choices=["No traces yet"], value=None)
    choices = [t["path"] for t in traces]
    labels = [
        f"{t['timestamp']} | {t['request']} | {t['tool_count']} tools"
        for t in traces
    ]
    return gr.Dropdown(choices=list(zip(choices, labels)), value=choices[0] if choices else None)


def view_trace(trace_path):
    """View a specific trace."""
    if not trace_path:
        return "Select a trace to view."

    logger = TraceLogger()
    return logger.format_trace_file(trace_path)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

with gr.Blocks(title="Document Agent Test", theme=gr.themes.Soft()) as app:
    gr.Markdown("# Document Agent Test\nUpload files → scan → ask questions about the content.")

    with gr.Row():
        with gr.Column(scale=1):
            file_input = gr.File(
                label="Upload Documents",
                file_count="multiple",
                file_types=[".pdf", ".pptx", ".docx", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".md"],
            )
            scan_btn = gr.Button("Scan Documents", variant="primary")
            clear_btn = gr.Button("Clear All", variant="secondary")
            file_list = gr.Dropdown(
                label="Loaded Files",
                choices=[],
                multiselect=True,
                interactive=False,
            )

        with gr.Column(scale=2):
            scan_output = gr.Markdown(label="Scan Results")

    gr.Markdown("---")
    gr.Markdown("## Ask About the Documents")

    with gr.Tabs():
        with gr.Tab("Conversation"):
            chatbot = gr.Chatbot(height=400, label="Document Agent")
            with gr.Row():
                question_input = gr.Textbox(
                    placeholder='e.g. "teach me chapter 2", "what does the lecture cover?", "help me prepare for the exam"',
                    label="Your question",
                    scale=4,
                )
                ask_btn = gr.Button("Ask", variant="primary", scale=1)

            gr.Examples(
                examples=[
                    ["give me the table of contents"],
                    ["what is chapter 2 about?"],
                    ["extract all content from the lecture slides"],
                    ["help me prepare for the exam"],
                    ["find example 3-2"],
                    ["what topics are covered in this document?"],
                ],
                inputs=question_input,
            )

        with gr.Tab("Agent Trace (Debug)"):
            gr.Markdown("### Tool Calls & Reasoning\nSee which tools the agent called, what arguments, and what responses they got.")
            trace_output = gr.Markdown(label="Execution Trace", value="No trace yet. Ask a question to see the trace.")

        with gr.Tab("Saved Traces"):
            gr.Markdown("### View All Agent Execution Traces\nEach question you ask is saved to `.traces/` as JSON. Browse and inspect them here.")
            with gr.Row():
                refresh_btn = gr.Button("Refresh List", variant="secondary")
                trace_dropdown = gr.Dropdown(
                    label="Saved Traces",
                    choices=[],
                    value=None,
                    interactive=True,
                )
            trace_view = gr.Markdown(label="Trace Details", value="No traces yet. Ask a question to generate a trace.")

    # Wire up events
    scan_btn.click(
        handle_upload,
        inputs=[file_input],
        outputs=[scan_output, question_input, file_list],
    )

    def ask_and_refresh(q, chat):
        """Ask question and refresh trace list."""
        chat, q, trace = handle_ask(q, chat)
        updated_dropdown = load_trace_list()
        return chat, q, trace, updated_dropdown

    ask_btn.click(
        ask_and_refresh,
        inputs=[question_input, chatbot],
        outputs=[chatbot, question_input, trace_output, trace_dropdown],
    )

    question_input.submit(
        ask_and_refresh,
        inputs=[question_input, chatbot],
        outputs=[chatbot, question_input, trace_output, trace_dropdown],
    )

    refresh_btn.click(
        load_trace_list,
        outputs=[trace_dropdown],
    )

    trace_dropdown.change(
        view_trace,
        inputs=[trace_dropdown],
        outputs=[trace_view],
    )

    clear_btn.click(
        handle_clear,
        outputs=[scan_output, question_input, file_list, chatbot, trace_output],
    )

    # Load initial trace list on page load
    app.load(
        load_trace_list,
        outputs=[trace_dropdown],
    )

if __name__ == "__main__":
    print("Starting Document Agent Test App...")
    print(f"Upload directory: {_upload_dir}")
    print(f"Traces saved to: .traces/")
    print(f"Open http://localhost:7860 in your browser")
    print()
    app.launch(share=False, server_port=7860)

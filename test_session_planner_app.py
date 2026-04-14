"""
Test app for SessionPlannerAgent.

Run:
    python test_session_planner_app.py
"""

import json
import os
import sys
import shutil
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import gradio as gr
from dotenv import load_dotenv

load_dotenv()

from utils.llm_client import LLMClient
from agents.session_planner_agent import SessionPlannerAgent
from utils.trace_logger import TraceLogger

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

_llm = None
_planner = None
_uploaded_paths = []
_upload_dir = os.path.join(tempfile.gettempdir(), "session_planner_test")
os.makedirs(_upload_dir, exist_ok=True)


def get_llm():
    global _llm
    if _llm is None:
        _llm = LLMClient(model="gpt-4o-mini")
    return _llm


def get_planner():
    global _planner
    if _planner is None:
        _planner = SessionPlannerAgent(get_llm())
    return _planner


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def handle_upload(files):
    global _uploaded_paths, _planner

    if not files:
        return "No files uploaded.", []

    _uploaded_paths = []
    for f in files:
        dest = os.path.join(_upload_dir, os.path.basename(f.name))
        shutil.copy(f.name, dest)
        _uploaded_paths.append(dest)

    # Reset planner on new upload
    _planner = None

    file_names = [os.path.basename(p) for p in _uploaded_paths]
    summary = f"Uploaded {len(_uploaded_paths)} file(s):\n" + "\n".join(f"- {n}" for n in file_names)
    return summary, file_names


def handle_plan(request, student_context):
    global _uploaded_paths

    if not _uploaded_paths:
        return "Please upload files first.", "", ""

    if not request.strip():
        return "Please enter a learning request.", "", ""

    try:
        planner = get_planner()
        plan = planner.plan(
            file_paths=_uploaded_paths,
            request=request,
            student_context=student_context or "",
        )
        plan_json = json.dumps(plan, indent=2)
        plan_md = _format_plan_markdown(plan)

        # Get trace
        trace_text = ""
        if planner.last_trace:
            trace_text = planner.tracer.format_trace(planner.last_trace)

        return plan_md, plan_json, trace_text

    except Exception as e:
        err = f"Error: {e}"
        return err, err, err


def _format_plan_markdown(plan: dict) -> str:
    if "error" in plan:
        return f"**Error:** {plan['error']}"

    lines = []
    lines.append(f"## {plan.get('title', 'Teaching Plan')}")
    lines.append(f"**Duration:** {plan.get('estimated_duration', '?')} | **Scope:** {plan.get('scope', '?')}")
    lines.append(f"**Request:** {plan.get('student_request', '')}")

    prereqs = plan.get("prerequisites", [])
    if prereqs:
        lines.append(f"\n**Prerequisites:** {', '.join(prereqs)}")

    sources = plan.get("sources", [])
    if sources:
        lines.append("\n**Sources:**")
        for s in sources:
            lines.append(f"- {s.get('file', '?')} ({s.get('document_class', '?')}, pages: {s.get('pages', '?')})")

    topics = plan.get("topics", [])
    if topics:
        lines.append(f"\n### Topics ({len(topics)} total)\n")
        for t in topics:
            lines.append(f"**{t.get('order', '?')}. {t.get('title', '?')}** "
                         f"({t.get('estimated_minutes', '?')} min, {t.get('difficulty', '?')})")
            lines.append(f"  Source: {t.get('source_file', '?')} | Section: {t.get('section', '?')} | Pages: {t.get('page_range', '?')}")
            if t.get("key_concepts"):
                lines.append(f"  Concepts: {', '.join(t['key_concepts'])}")
            if t.get("key_equations"):
                lines.append(f"  Equations: {', '.join(t['key_equations'])}")
            if t.get("examples"):
                lines.append(f"  Examples: {', '.join(t['examples'])}")
            if t.get("practice_problems"):
                lines.append(f"  Problems: {', '.join(t['practice_problems'])}")
            lines.append("")

    quiz = plan.get("quiz_coverage", [])
    if quiz:
        lines.append(f"**Quiz coverage:** {', '.join(quiz)}")

    notes = plan.get("teaching_notes", "")
    if notes:
        lines.append(f"\n**Teaching notes:** {notes}")

    return "\n".join(lines)


def handle_clear():
    global _uploaded_paths, _planner
    _uploaded_paths = []
    _planner = None
    return "Cleared.", [], "", "", ""


def load_trace_list():
    logger_obj = TraceLogger()
    traces = logger_obj.list_traces()
    if not traces:
        return gr.Dropdown(choices=["No traces yet"], value=None)
    choices = [t["path"] for t in traces]
    labels = [
        f"{t['timestamp']} | {t['request'][:40]} | {t['tool_count']} tools"
        for t in traces
    ]
    return gr.Dropdown(choices=list(zip(choices, labels)), value=choices[0] if choices else None)


def view_trace(trace_path):
    if not trace_path:
        return "Select a trace to view."
    logger_obj = TraceLogger()
    return logger_obj.format_trace_file(trace_path)


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

with gr.Blocks(title="Session Planner Test", theme=gr.themes.Soft()) as app:
    gr.Markdown("# Session Planner Agent Test\nUpload documents → enter a learning request → get a teaching plan.")

    with gr.Row():
        with gr.Column(scale=1):
            file_input = gr.File(
                label="Upload Documents",
                file_count="multiple",
                file_types=[".pdf", ".pptx", ".docx", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".md"],
            )
            upload_btn = gr.Button("Upload", variant="primary")
            clear_btn = gr.Button("Clear All", variant="secondary")
            file_list = gr.Dropdown(label="Uploaded Files", choices=[], multiselect=True, interactive=False)

        with gr.Column(scale=2):
            upload_status = gr.Markdown(label="Upload Status")

    gr.Markdown("---")
    gr.Markdown("## Create Teaching Plan")

    with gr.Row():
        with gr.Column(scale=3):
            request_input = gr.Textbox(
                placeholder='e.g. "teach me chapter 3", "help me prepare for the exam", "explain kinematics"',
                label="Learning Request",
                lines=2,
            )
        with gr.Column(scale=2):
            context_input = gr.Textbox(
                placeholder='e.g. "knows calculus, merit score 7/10"',
                label="Student Context (optional)",
            )

    plan_btn = gr.Button("Create Plan", variant="primary")

    gr.Examples(
        examples=[
            ["teach me chapter 3", ""],
            ["help me prepare for the exam", ""],
            ["I want to learn about kinematics", "knows basic algebra"],
            ["give me a plan for all the lecture slides", ""],
            ["explain everything in the uploaded documents", "beginner level"],
        ],
        inputs=[request_input, context_input],
    )

    with gr.Tabs():
        with gr.Tab("Plan (Formatted)"):
            plan_markdown = gr.Markdown(value="No plan yet. Enter a request above.")

        with gr.Tab("Plan (JSON)"):
            plan_json = gr.Code(label="SessionPlan JSON", language="json", value="{}")

        with gr.Tab("Agent Trace (Debug)"):
            gr.Markdown("### Tool calls and LLM reasoning from the last planning run.")
            trace_output = gr.Markdown(value="No trace yet.")

        with gr.Tab("Saved Traces"):
            gr.Markdown("### All saved planning traces")
            with gr.Row():
                refresh_btn = gr.Button("Refresh", variant="secondary")
                trace_dropdown = gr.Dropdown(label="Saved Traces", choices=[], value=None, interactive=True)
            trace_view = gr.Markdown(value="Select a trace to view.")

    # Events
    upload_btn.click(
        handle_upload,
        inputs=[file_input],
        outputs=[upload_status, file_list],
    )

    def plan_and_refresh(req, ctx):
        md, raw, trace = handle_plan(req, ctx)
        dropdown = load_trace_list()
        return md, raw, trace, dropdown

    plan_btn.click(
        plan_and_refresh,
        inputs=[request_input, context_input],
        outputs=[plan_markdown, plan_json, trace_output, trace_dropdown],
    )

    request_input.submit(
        plan_and_refresh,
        inputs=[request_input, context_input],
        outputs=[plan_markdown, plan_json, trace_output, trace_dropdown],
    )

    refresh_btn.click(load_trace_list, outputs=[trace_dropdown])
    trace_dropdown.change(view_trace, inputs=[trace_dropdown], outputs=[trace_view])

    clear_btn.click(
        handle_clear,
        outputs=[upload_status, file_list, plan_markdown, plan_json, trace_output],
    )

    app.load(load_trace_list, outputs=[trace_dropdown])


if __name__ == "__main__":
    print("Starting Session Planner Test App...")
    print(f"Upload directory: {_upload_dir}")
    print(f"Traces saved to: .traces/")
    print(f"Open http://localhost:7861 in your browser")
    print()
    app.launch(share=False, server_port=7861)

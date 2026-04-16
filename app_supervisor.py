"""
Gradio app for the full Supervisor pipeline.

Upload documents → Supervisor chains: extract → plan → teach.
Debug tabs show agent activity, supervisor memory, and saved files.

Run:
    python app_supervisor.py

Opens http://localhost:7860
Requires OPENAI_API_KEY and GEMINI_API_KEY in .env
"""

import json
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("gradio").setLevel(logging.WARNING)

import gradio as gr
from dotenv import load_dotenv

load_dotenv()

from agents.supervisor import Supervisor
from utils.llm_client import LLMClient
from utils.gemini_client import GeminiLLMClient
from config import get_model

# Debug output folder — always written here so user can inspect
DEBUG_DIR = os.path.join(os.path.dirname(__file__), "debug")
os.makedirs(DEBUG_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

_supervisor: Supervisor | None = None
_pending_file_paths: list[str] = []


def _get_supervisor() -> Supervisor:
    global _supervisor
    if _supervisor is None:
        _supervisor = Supervisor(
            llm_client=LLMClient(model=get_model("supervisor")),
            gemini_client=GeminiLLMClient(),
            session_dir=DEBUG_DIR,
            teaching_llm_client=LLMClient(model=get_model("teaching_agent")),
        )
    return _supervisor


# ---------------------------------------------------------------------------
# Sidebar helpers
# ---------------------------------------------------------------------------

def _progress_md() -> str:
    sup = _get_supervisor()
    if sup.tutor is None:
        return "### Learning Path\n\n*Upload documents to begin.*"

    tutor = sup.tutor
    lines = ["### Learning Path"]
    for i, unit_id in enumerate(tutor.learning_path):
        unit = tutor.unit_map.get(unit_id, {})
        title = unit.get("title", unit_id)
        source = unit.get("source_id", "")
        done = unit_id in tutor.taught_sections_registry
        if i == tutor.current_index and not done:
            marker = "**→**"
            label = f"**{title}** `[{source}]`"
        elif done:
            marker = "✓"
            label = f"~~{title}~~"
        else:
            marker = f"{i + 1}."
            label = f"{title} `[{source}]`"
        lines.append(f"{marker} {label}")
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Debug panel helpers
# ---------------------------------------------------------------------------

def _activity_log_md() -> str:
    """Render activity log as markdown."""
    sup = _get_supervisor()
    if not sup.activity_log:
        return "*No activity yet.*"
    return "\n\n".join(sup.activity_log)


def _supervisor_memory_md() -> str:
    """Render supervisor's conversation history (system prompt collapsed)."""
    sup = _get_supervisor()
    lines = []
    for i, msg in enumerate(sup.conversation):
        role = msg.get("role", "?")
        content = msg.get("content") or ""
        tool_calls = msg.get("tool_calls")

        if role == "system":
            lines.append(f"**[{i}] SYSTEM** *(prompt — {len(content)} chars)*")
        elif role == "user":
            lines.append(f"**[{i}] USER**\n> {content[:300]}{'...' if len(content) > 300 else ''}")
        elif role == "assistant" and tool_calls:
            calls = ", ".join(
                f"`{tc['function']['name']}({tc['function']['arguments'][:60]})`"
                for tc in tool_calls
            )
            lines.append(f"**[{i}] ASSISTANT** → tool calls: {calls}")
        elif role == "assistant":
            lines.append(f"**[{i}] ASSISTANT**\n> {content[:300]}{'...' if len(content) > 300 else ''}")
        elif role == "tool":
            lines.append(
                f"**[{i}] TOOL RESULT**\n```\n{content[:400]}{'...' if len(content) > 400 else ''}\n```"
            )
    return "\n\n---\n\n".join(lines) if lines else "*No conversation yet.*"


def _content_json_text() -> str:
    path = os.path.join(DEBUG_DIR, "content.json")
    if not os.path.exists(path):
        return "content.json not yet created."
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        # Show source names + char counts + first 500 chars of each
        lines = [f"content.json — {len(data)} source(s)\n"]
        for entry in data:
            source = entry.get("source", "?")
            content = entry.get("content", "")
            lines.append(f"{'─'*60}")
            lines.append(f"SOURCE: {source}  ({len(content):,} chars)")
            lines.append(f"{'─'*60}")
            lines.append(content[:1000] + ("\n...(truncated)" if len(content) > 1000 else ""))
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"Error reading content.json: {e}"


def _plan_json_text() -> str:
    path = os.path.join(DEBUG_DIR, "plan_output.json")
    if not os.path.exists(path):
        return "plan_output.json not yet created."
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading plan_output.json: {e}"


def _teaching_context_text() -> str:
    """Extract and display the current reference card from TeachingAgent's system prompt."""
    sup = _get_supervisor()

    # Check if teaching is active
    if not sup.tutor or not sup.tutor.teaching_agent.conversation_history:
        return "No active teaching session yet."

    # Get the system prompt (first message in conversation history)
    history = sup.tutor.teaching_agent.conversation_history
    if not history or history[0].get("role") != "system":
        return "No system prompt found."

    system_prompt = history[0].get("content", "")

    # Extract the current unit and reference card from system prompt
    lines = system_prompt.split("\n")

    # Find CURRENT UNIT section
    current_unit_idx = -1
    for i, line in enumerate(lines):
        if "CURRENT UNIT:" in line:
            current_unit_idx = i
            break

    if current_unit_idx == -1:
        return "Could not find CURRENT UNIT in system prompt."

    # Extract everything from CURRENT UNIT onwards until next major section
    extracted = []
    for i in range(current_unit_idx, len(lines)):
        line = lines[i]
        # Stop at major section headers (━━━) to avoid including too much
        if i > current_unit_idx and line.startswith("━━━"):
            break
        extracted.append(line)

    result = "\n".join(extracted)

    # Also add current teaching state
    if sup.tutor:
        current_idx = sup.tutor.current_index
        total = len(sup.tutor.learning_path)
        current_unit_id = sup.tutor.learning_path[current_idx] if current_idx < total else "?"
        current_unit_obj = sup.tutor.unit_map.get(current_unit_id, {})
        title = current_unit_obj.get("title", "?")

        state_info = f"\n\n━━━ TEACHING STATE ━━━\nUnit: {title}\nIndex: {current_idx + 1}/{total}\nUnit ID: {current_unit_id}"
        result = state_info + "\n\n" + result

    return result


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------

def handle_upload(files, history: list):
    global _pending_file_paths, _supervisor
    if not files:
        return history, _progress_md()

    # Fresh supervisor for new upload
    _supervisor = None
    _pending_file_paths = [f.name for f in files]
    file_names = ", ".join(os.path.basename(p) for p in _pending_file_paths)

    history = history + [
        {"role": "user", "content": f"📎 Uploaded {len(_pending_file_paths)} file(s): {file_names}"},
        {"role": "assistant", "content": (
            f"Got it — {len(_pending_file_paths)} file(s) ready.\n\n"
            "**What would you like to study?** For example:\n"
            "- \"Teach me chapter 3\"\n"
            "- \"I want to learn section 3-2\"\n"
            "- \"Give me everything from the lectures\""
        )},
    ]
    return history, _progress_md()


def respond(message: str, history: list):
    """
    Generator — yields status updates then final response.

    Branches:
    1. _pending_file_paths set → full pipeline with status per phase
    2. teaching_active → direct to tutor (no supervisor LLM)
    3. else → supervisor LLM routing
    """
    global _pending_file_paths

    if not message.strip():
        yield history, "", _progress_md(), _activity_log_md(), _supervisor_memory_md(), _content_json_text(), _plan_json_text()
        return

    history = history + [{"role": "user", "content": message}]
    sup = _get_supervisor()

    def _state():
        return _progress_md(), _activity_log_md(), _supervisor_memory_md(), _content_json_text(), _plan_json_text(), _teaching_context_text()

    if _pending_file_paths:
        paths = _pending_file_paths[:]
        _pending_file_paths = []

        try:
            # Phase 1
            history = history + [{"role": "assistant", "content": "⏳ **Extracting** documents..."}]
            yield history, "", *_state()
            sup.step_extract(paths, request=message)

            # Phase 2
            history[-1] = {"role": "assistant", "content": "📋 **Planning** your learning path..."}
            yield history, "", *_state()
            sup.step_plan()

            # Phase 3
            history[-1] = {"role": "assistant", "content": "🎓 **Preparing** your first lesson..."}
            yield history, "", *_state()
            welcome = sup.step_start_teaching()

            sup.conversation.append({
                "role": "assistant",
                "content": (
                    "Pipeline complete. Teaching session is now active. "
                    "I will use forward_to_tutor for all student messages going forward."
                ),
            })

            history[-1] = {"role": "assistant", "content": welcome}
            yield history, "", *_state()

        except Exception as e:
            history[-1] = {"role": "assistant", "content": f"Error: {e}"}
            yield history, "", *_state()

    elif sup.teaching_active:
        # Direct to tutor — no supervisor LLM involvement
        history = history + [{"role": "assistant", "content": "💭 **Thinking...**"}]
        yield history, "", *_state()

        try:
            sup._log("TeachingAgent", "Student message received", message[:80])
            response = sup.tutor.chat(message)
            if sup.tutor.current_index >= len(sup.tutor.learning_path):
                sup.teaching_active = False
                sup._log("PlanDrivenTutor", "All units complete")
        except Exception as e:
            response = f"Error: {e}"

        history[-1] = {"role": "assistant", "content": response}
        yield history, "", *_state()

    else:
        history = history + [{"role": "assistant", "content": "💭 **Thinking...**"}]
        yield history, "", *_state()

        try:
            response = sup.chat(message)
        except Exception as e:
            response = f"Error: {e}"

        history[-1] = {"role": "assistant", "content": response}
        yield history, "", *_state()


def reset_session():
    global _supervisor, _pending_file_paths
    if _supervisor is not None:
        _supervisor.reset()
        _supervisor = None
    _pending_file_paths = []
    sup = _get_supervisor()  # fresh instance
    return [], _progress_md(), _activity_log_md(), _supervisor_memory_md(), _content_json_text(), _plan_json_text()


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,700;1,400;1,700&display=swap');

.message-wrap .message,
.message-wrap .prose,
.chatbot .message p,
.chatbot .message li,
.chatbot .message span {
    font-family: 'EB Garamond', Garamond, 'Times New Roman', serif !important;
    font-size: 18px !important;
    line-height: 1.75 !important;
}

.gr-textbox textarea {
    font-family: 'EB Garamond', Garamond, serif !important;
    font-size: 17px !important;
}
"""

with gr.Blocks(title="AI Study Tutor") as app:
    gr.Markdown("# AI Study Tutor")

    with gr.Row():

        # ── Left sidebar ──────────────────────────────────────────────────
        with gr.Column(scale=1, min_width=260):
            file_upload = gr.File(
                label="Upload Documents",
                file_count="multiple",
                file_types=[".pdf", ".pptx", ".docx", ".txt", ".png", ".jpg", ".jpeg"],
            )
            upload_btn = gr.Button("Process Documents", variant="primary", size="sm")

            gr.Markdown("---")
            progress_md = gr.Markdown(value="*Upload documents to begin.*")

            gr.Markdown("---")
            gr.Markdown(
                "**Tips**\n"
                "- Say **ready** or **yes** to start\n"
                "- Say **skip** to skip a unit\n"
                "- Ask *how am I doing?* for progress\n"
                f"\n**Debug files**\n`debug/content.json`\n`debug/plan_output.json`"
            )
            reset_btn = gr.Button("Reset Session", variant="secondary", size="sm")

        # ── Right panel: chat + debug tabs ────────────────────────────────
        with gr.Column(scale=3):
            with gr.Tabs():

                with gr.Tab("Chat"):
                    chatbot = gr.Chatbot(
                        label="Tutor",
                        height=520,
                        render_markdown=True,
                        sanitize_html=False,
                        latex_delimiters=[
                            {"left": "$$", "right": "$$", "display": True},
                            {"left": "$", "right": "$", "display": False},
                        ],
                    )
                    with gr.Row():
                        msg_input = gr.Textbox(
                            placeholder="Upload documents first, then type here...",
                            label="",
                            show_label=False,
                            scale=5,
                        )
                        send_btn = gr.Button("Send", variant="primary", scale=1)

                with gr.Tab("Activity Log"):
                    gr.Markdown(
                        "*Real-time log of which agent did what — updated after each message.*"
                    )
                    activity_box = gr.Markdown(value="*No activity yet.*")

                with gr.Tab("Supervisor Memory"):
                    gr.Markdown(
                        "*The supervisor's conversation history — what it knows and what tool calls it made.*"
                    )
                    memory_box = gr.Markdown(value="*No conversation yet.*")

                with gr.Tab("Extracted Content"):
                    gr.Markdown(
                        f"*Content extracted from documents — also saved to `debug/content.json`*"
                    )
                    content_box = gr.Code(
                        label="content.json",
                        language="markdown",
                        lines=25,
                        value="content.json not yet created.",
                    )

                with gr.Tab("Teaching Plan"):
                    gr.Markdown(
                        f"*Structured teaching plan — also saved to `debug/plan_output.json`*"
                    )
                    plan_box = gr.Code(
                        label="plan_output.json",
                        language="json",
                        lines=25,
                        value="plan_output.json not yet created.",
                    )

                with gr.Tab("Teaching Context"):
                    gr.Markdown(
                        "*Current reference card loaded in TeachingAgent's system prompt — validate pacing and context here.*"
                    )
                    context_box = gr.Markdown(
                        value="*No active teaching session yet.*",
                        label="Current Teaching Context"
                    )

    # ── All outputs shared across events ─────────────────────────────────
    _debug_outputs = [activity_box, memory_box, content_box, plan_box, context_box]

    upload_btn.click(
        handle_upload,
        inputs=[file_upload, chatbot],
        outputs=[chatbot, progress_md],
    )

    send_btn.click(
        respond,
        inputs=[msg_input, chatbot],
        outputs=[chatbot, msg_input, progress_md] + _debug_outputs,
    )
    msg_input.submit(
        respond,
        inputs=[msg_input, chatbot],
        outputs=[chatbot, msg_input, progress_md] + _debug_outputs,
    )

    reset_btn.click(
        reset_session,
        outputs=[chatbot, progress_md] + _debug_outputs,
    )


if __name__ == "__main__":
    print("Starting Supervisor app...")
    print(f"Debug files will be saved to: {DEBUG_DIR}")
    print("Open http://localhost:7860 in your browser")
    print()
    app.launch(share=False, server_port=7860, css=CUSTOM_CSS)

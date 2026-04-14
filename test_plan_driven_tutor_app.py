"""
Gradio test app for PlanDrivenTutor.

Run:
    python test_plan_driven_tutor_app.py

Opens http://localhost:7863
Requires plan_output.json in the project root (run test_planner_agent.py first).
"""

import os
import sys
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Configure logging to show in terminal
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
# Suppress verbose httpx logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("gradio").setLevel(logging.WARNING)

import gradio as gr
from dotenv import load_dotenv

load_dotenv()

from agents.plan_driven_tutor import PlanDrivenTutor
from utils.llm_client import LLMClient
from config import get_model

PLAN_PATH = os.path.join(os.path.dirname(__file__), "plan_output.json")

# ---------------------------------------------------------------------------
# Global state — one tutor per server process
# ---------------------------------------------------------------------------

_tutor: PlanDrivenTutor | None = None


def _get_tutor() -> PlanDrivenTutor:
    global _tutor
    if _tutor is None:
        _tutor = PlanDrivenTutor(LLMClient(model=get_model("teaching_agent")), PLAN_PATH)
    return _tutor


def _progress_md() -> str:
    """Learning path with current unit highlighted."""
    tutor = _get_tutor()
    lines = ["### Learning Path"]
    for i, unit_id in enumerate(tutor.learning_path):
        unit = tutor.unit_map.get(unit_id, {})
        title = unit.get("title", unit_id)
        source = unit.get("source_id", "")
        if i == tutor.current_index:
            marker = "**→**"
            label = f"**{title}** `[{source}]`"
        elif i < tutor.current_index:
            marker = "~~✓~~"
            label = f"~~{title}~~"
        else:
            marker = f"{i + 1}."
            label = f"{title} `[{source}]`"
        lines.append(f"{marker} {label}")
    return "\n\n".join(lines)


def _system_prompt_text() -> str:
    """Return the current system prompt sent to TeachingAgent, or a placeholder."""
    tutor = _get_tutor()
    history = tutor.teaching_agent.conversation_history
    if history and history[0]["role"] == "system":
        return history[0]["content"]
    return "(No active teaching session yet — type 'start' to begin.)"


def _reference_card_text() -> str:
    """Return the reference card for the current unit (the {content} slot)."""
    tutor = _get_tutor()
    idx = tutor.current_index
    if idx >= len(tutor.learning_path):
        return "(All units complete.)"
    unit_id = tutor.learning_path[idx]
    unit = tutor.unit_map.get(unit_id, {})
    return tutor._build_reference_card(unit) or "(No reference card for this unit.)"


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------

def load_welcome():
    tutor = _get_tutor()
    welcome = tutor.start()
    history = [{"role": "assistant", "content": welcome}]
    return history, _progress_md(), _system_prompt_text(), _reference_card_text()


def respond(message: str, history: list):
    if not message.strip():
        return history, "", _progress_md(), _system_prompt_text(), _reference_card_text()

    tutor = _get_tutor()
    history = history + [{"role": "user", "content": message}]

    try:
        response = tutor.chat(message)
    except Exception as e:
        response = f"Error: {e}"

    history = history + [{"role": "assistant", "content": response}]
    return history, "", _progress_md(), _system_prompt_text(), _reference_card_text()


def reset():
    global _tutor
    _tutor = None
    return load_welcome()


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,700;1,400;1,700&display=swap');

/* Chat bubbles */
.message-wrap .message,
.message-wrap .prose,
.chatbot .message p,
.chatbot .message li,
.chatbot .message span {
    font-family: 'EB Garamond', Garamond, 'Times New Roman', serif !important;
    font-size: 18px !important;
    line-height: 1.75 !important;
}

/* Input box */
.gr-textbox textarea {
    font-family: 'EB Garamond', Garamond, serif !important;
    font-size: 17px !important;
}
"""

with gr.Blocks(title="AI Study Tutor") as app:
    gr.Markdown("# AI Study Tutor")

    with gr.Row():
        # ── Left sidebar: learning path progress ──────────────────────────
        with gr.Column(scale=1, min_width=260):
            progress_md = gr.Markdown(value="Loading...", label="Progress")

            gr.Markdown("---")
            gr.Markdown(
                "**Commands**\n"
                "- `start` / `yes` — begin or continue\n"
                "- `go to N` — jump to unit N\n"
                "- `skip` — skip current unit\n"
            )
            reset_btn = gr.Button("Restart Session", variant="secondary", size="sm")

        # ── Right panel: chat + debug tabs ────────────────────────────────
        with gr.Column(scale=3):
            with gr.Tabs():

                # Tab 1: Chat
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
                            placeholder='Type "start" to begin, or ask anything...',
                            label="",
                            show_label=False,
                            scale=5,
                        )
                        send_btn = gr.Button("Send", variant="primary", scale=1)

                # Tab 2: Full system prompt sent to LLM
                with gr.Tab("System Prompt"):
                    gr.Markdown(
                        "*The full system prompt currently loaded into TeachingAgent. "
                        "Updates after each message. Shows how it changes unit-to-unit.*"
                    )
                    system_prompt_box = gr.Code(
                        label="System Prompt (sent to LLM)",
                        language="markdown",
                        lines=30,
                        value="(start the session to see the prompt)",
                    )

                # Tab 3: Reference card only (the {content} slot)
                with gr.Tab("Reference Card"):
                    gr.Markdown(
                        "*The structured teaching reference card for the current unit — "
                        "subtopics, equations, figures, examples. This is the `{content}` "
                        "slot inside the system prompt.*"
                    )
                    reference_card_box = gr.Code(
                        label="Reference Card (current unit)",
                        language="markdown",
                        lines=30,
                        value="(start the session to see the reference card)",
                    )

    # ── Events ────────────────────────────────────────────────────────────

    _outputs = [chatbot, msg_input, progress_md, system_prompt_box, reference_card_box]
    _load_outputs = [chatbot, progress_md, system_prompt_box, reference_card_box]

    app.load(load_welcome, outputs=_load_outputs)

    send_btn.click(respond, inputs=[msg_input, chatbot], outputs=_outputs)
    msg_input.submit(respond, inputs=[msg_input, chatbot], outputs=_outputs)
    reset_btn.click(reset, outputs=_load_outputs)


if __name__ == "__main__":
    if not os.path.exists(PLAN_PATH):
        print(f"ERROR: plan_output.json not found at {PLAN_PATH}")
        print("Run test_planner_agent.py first to generate it.")
        sys.exit(1)

    print("Starting PlanDrivenTutor app...")
    print("Open http://localhost:7863 in your browser")
    print()
    app.launch(share=False, server_port=7863, css=CUSTOM_CSS)

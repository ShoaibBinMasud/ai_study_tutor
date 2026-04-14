"""
Test app for TeachingAgent — test and tweak teaching style in isolation.

Run:
    python test_teaching_agent_app.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import re

import gradio as gr
from dotenv import load_dotenv

load_dotenv()

from utils.llm_client import LLMClient
from agents.teaching_agent import TeachingAgent, STYLE_HINTS, SYSTEM_PROMPT
from agents.visualization_agent import VisualizationAgent
from models.data_models import SubjectProfile, TeachingUnit

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------

_llm = None
_agent: TeachingAgent | None = None
_viz_agent: VisualizationAgent | None = None

# Matches [DIAGRAM: some description] emitted by TeachingAgent mid-response.
# Handles optional markdown bold wrapping (**[DIAGRAM:...]**) and multi-line descriptions.
_DIAGRAM_RE = re.compile(r'\*{0,2}\[DIAGRAM:\s*(.*?)\]\*{0,2}', re.IGNORECASE | re.DOTALL)


def get_llm():
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm


def get_agent() -> TeachingAgent:
    global _agent
    if _agent is None:
        _agent = TeachingAgent(get_llm())
    return _agent


def get_viz_agent() -> VisualizationAgent:
    global _viz_agent
    if _viz_agent is None:
        _viz_agent = VisualizationAgent(get_llm())
    return _viz_agent


def _make_iframe(html: str) -> str:
    """Wrap diagram HTML in a compact, light-background iframe for inline embedding."""
    escaped = html.replace('"', "&quot;")
    return (
        '<div style="margin:16px 0;border-radius:12px;overflow:hidden;'
        'border:1px solid #e2e8f0;background:#f8f9fc;box-shadow:0 1px 4px rgba(0,0,0,0.06);">'
        f'<iframe srcdoc="{escaped}" '
        'style="width:100%;height:420px;border:none;display:block;" '
        'scrolling="no" sandbox="allow-scripts"></iframe>'
        '</div>'
    )


def _build_inline_messages(response: str, student_message: str, topic: str, subject: str) -> list[dict]:
    """
    Split the agent response at [DIAGRAM: ...] and return a list of chat message dicts.
    If the token is found, generates the diagram and inserts it inline between the surrounding text.
    If the student explicitly asked for a visualization, treat the whole response as the context.
    """
    messages = []

    match = _DIAGRAM_RE.search(response)

    if not match:
        # No diagram token — return plain message
        clean = response.replace("SHOW_DIAGRAM", "").strip()
        return [{"role": "assistant", "content": clean}]

    concept = match.group(1).strip()
    text_before = response[:match.start()].strip()
    text_after = response[match.end():].strip()

    # Generate diagram
    try:
        html = get_viz_agent().generate(
            concept=concept,
            subject=subject,
            context=(text_before or response)[:500],
        )
    except Exception as e:
        html = None
        text_after = f"_(Diagram error: {e})_\n\n{text_after}"

    # Assemble inline: text → iframe → text
    # Do NOT wrap text in <div> — Gradio must see raw markdown so it renders
    # bold, $math$, $$equations$$ correctly. Only the iframe is raw HTML.
    parts = []
    if text_before:
        parts.append(text_before)
    if html:
        parts.append(_make_iframe(html))
    if text_after:
        parts.append(text_after)

    combined = "\n\n".join(parts)
    messages.append({"role": "assistant", "content": combined})
    return messages


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def start_lesson(
    topic: str,
    content: str,
    use_reference: bool,
    subject: str,
    sub_field: str,
    level: str,
    style: str,
    history: list,
    opening_message: str = "Begin the lesson.",
):
    global _agent
    _agent = None  # fresh agent every time

    if not topic.strip():
        return (
            [{"role": "assistant", "content": "Please enter a topic title."}],
            _build_system_prompt_preview(topic, content, use_reference, subject, sub_field, level, style),
        )

    profile = SubjectProfile(
        subject=subject or "Physics",
        sub_field=sub_field or "",
        level=level,
        material_type="textbook",
        teaching_style_hints=style,
    )

    unit = TeachingUnit(
        unit_id="test_unit",
        title=topic,
        content=content or "",
        page_range=(1, 10),
        content_type="concept",
    )

    agent = get_agent()

    try:
        if use_reference:
            response = agent.start_unit_with_reference(
                unit, profile, reference_card=content, opening_message=opening_message
            )
        else:
            response = agent.start_unit(unit, profile, opening_message=opening_message)

        history = _build_inline_messages(response, opening_message, topic, subject or "Physics")
    except Exception as e:
        history = [{"role": "assistant", "content": f"Error: {e}"}]

    prompt_preview = _build_system_prompt_preview(topic, content, use_reference, subject, sub_field, level, style)
    return history, prompt_preview


def respond(message: str, history: list, content: str, use_reference: bool, subject: str, sub_field: str, level: str, style: str):
    if not message.strip():
        return history, ""

    agent = get_agent()
    if not agent.conversation_history:
        # Auto-start: student typed in chat box without clicking Start Lesson.
        # Pass their exact message as the opening so "explain X with visualization"
        # actually reaches the LLM instead of being silently dropped.
        topic = message.strip()
        new_history, prompt_preview = start_lesson(
            topic, content, use_reference, subject, sub_field, level, style, [],
            opening_message=message,
        )
        return new_history, ""

    topic = agent._current_unit.title if agent._current_unit else "concept"

    try:
        response = agent.respond(message)
        new_messages = _build_inline_messages(response, message, topic, subject or "Physics")

        if agent.is_unit_complete(response):
            # Clean UNIT_COMPLETE signal from the last message
            if new_messages:
                new_messages[-1]["content"] = agent.clean_response(new_messages[-1]["content"])
            new_messages.append({"role": "assistant", "content": "**UNIT COMPLETE** — all concepts covered."})

        history = history + [{"role": "user", "content": message}] + new_messages
    except Exception as e:
        history = history + [{"role": "user", "content": message}, {"role": "assistant", "content": f"Error: {e}"}]

    return history, ""


def reset_chat():
    global _agent, _viz_agent
    _agent = None
    _viz_agent = None
    return [], ""


def _build_system_prompt_preview(topic, content, use_reference, subject, sub_field, level, style):
    """Render the actual system prompt that will be sent to the LLM."""
    style_hints = STYLE_HINTS.get("conceptual", "")
    for key, hints in STYLE_HINTS.items():
        if key in style.lower():
            style_hints = hints
            break

    ref = content if use_reference else (content[:6000] if content else "")

    try:
        prompt = SYSTEM_PROMPT.format(
            subject=subject or "Physics",
            level=level,
            topic=topic or "(no topic)",
            content=ref or "(no content provided)",
            style_hints=style_hints,
        )
    except Exception as e:
        prompt = f"Error building prompt: {e}"

    return prompt


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

STYLE_OPTIONS = list(STYLE_HINTS.keys())
LEVEL_OPTIONS = ["introductory", "intermediate", "advanced", "graduate"]

with gr.Blocks(title="Teaching Agent Test") as app:
    gr.Markdown("# Teaching Agent Test\nConfigure a unit → Start Lesson → Chat with the teaching agent.")

    with gr.Row():
        # ── Left panel: configuration ──────────────────────────────────────
        with gr.Column(scale=1):
            gr.Markdown("## Unit Configuration")

            topic_input = gr.Textbox(
                label="Topic Title",
                placeholder='e.g. "Relativistic Momentum", "Newton\'s Second Law"',
            )

            content_input = gr.Textbox(
                label="Content / Reference Card",
                placeholder=(
                    "Paste the raw PDF text, reference card, or leave empty.\n\n"
                    "Reference card example:\n"
                    "  Symbols: γ = Lorentz factor, m₀ = rest mass\n"
                    "  Eq. 2-1: p = γm₀u (page 84)\n"
                    "  Eq. 2-5: E = γm₀c² (page 88)\n"
                    "  Figure 2-3: momentum vs velocity (page 85)"
                ),
                lines=10,
            )

            use_reference = gr.Checkbox(
                label="Treat content as Reference Card (not raw text)",
                value=True,
                info="Reference card mode: LLM teaches from its own knowledge, cites your notation. "
                     "Raw mode: LLM teaches directly from the pasted text.",
            )

            with gr.Row():
                subject_input = gr.Textbox(label="Subject", value="Physics", scale=2)
                sub_field_input = gr.Textbox(label="Sub-field", placeholder="e.g. Special Relativity", scale=2)

            with gr.Row():
                level_input = gr.Dropdown(label="Level", choices=LEVEL_OPTIONS, value="intermediate", scale=1)
                style_input = gr.Dropdown(label="Teaching Style", choices=STYLE_OPTIONS, value="equation-heavy", scale=2)

            gr.Examples(
                label="Quick Examples",
                examples=[
                    [
                        "Relativistic Momentum",
                        "Symbols: γ = Lorentz factor = 1/√(1−u²/c²), m₀ = rest mass, u = velocity, c = speed of light\n"
                        "Eq. 2-1: p = γm₀u (page 84)\n"
                        "Eq. 2-2: p = m₀u/√(1−u²/c²) (page 84)\n"
                        "Key idea: classical momentum mu not conserved in relativistic collisions; need new definition\n"
                        "Figure 2-1: relativistic vs classical momentum vs u/c (page 85)\n"
                        "Example 2-1: momentum of probe at 0.8c (page 86)",
                        True, "Physics", "Special Relativity", "intermediate", "equation-heavy",
                    ],
                    [
                        "Newton's Second Law",
                        "",
                        False, "Physics", "Classical Mechanics", "introductory", "conceptual",
                    ],
                    [
                        "Eigenvalues and Eigenvectors",
                        "Key equation: Av = λv\nSymbols: A = n×n matrix, v = eigenvector, λ = eigenvalue\nCharacteristic equation: det(A − λI) = 0\nApplications: diagonalization, PCA, differential equations",
                        True, "Mathematics", "Linear Algebra", "intermediate", "proof-based",
                    ],
                ],
                inputs=[topic_input, content_input, use_reference, subject_input, sub_field_input, level_input, style_input],
            )

            start_btn = gr.Button("Start Lesson", variant="primary", size="lg")
            reset_btn = gr.Button("Reset", variant="secondary")

        # ── Right panel: chat + system prompt ─────────────────────────────
        with gr.Column(scale=2):
            with gr.Tabs():
                with gr.Tab("Chat"):
                    chatbot = gr.Chatbot(
                        label="Teaching Session",
                        height=500,
                        sanitize_html=False,
                        latex_delimiters=[
                            {"left": "$$", "right": "$$", "display": True},
                            {"left": "$", "right": "$", "display": False},
                        ],
                    )
                    with gr.Row():
                        msg_input = gr.Textbox(
                            placeholder='Type "yes", "no", ask a question, or "show me a diagram"...',
                            label="Your response",
                            scale=4,
                            show_label=False,
                        )
                        send_btn = gr.Button("Send", variant="primary", scale=1)

                with gr.Tab("System Prompt Preview"):
                    gr.Markdown("*Live preview of the system prompt sent to the LLM.*")
                    prompt_preview = gr.Code(
                        label="System Prompt",
                        language="markdown",
                        lines=30,
                        value="Configure the unit and click Start Lesson to see the system prompt.",
                    )

    # ── Events ────────────────────────────────────────────────────────────
    start_btn.click(
        start_lesson,
        inputs=[topic_input, content_input, use_reference, subject_input, sub_field_input, level_input, style_input, chatbot],
        outputs=[chatbot, prompt_preview],
    )

    respond_inputs = [msg_input, chatbot, content_input, use_reference, subject_input, sub_field_input, level_input, style_input]

    send_btn.click(respond, inputs=respond_inputs, outputs=[chatbot, msg_input])
    msg_input.submit(respond, inputs=respond_inputs, outputs=[chatbot, msg_input])

    reset_btn.click(reset_chat, outputs=[chatbot, msg_input])

    # Live system prompt preview as user types
    for inp in [topic_input, content_input, use_reference, subject_input, sub_field_input, level_input, style_input]:
        inp.change(
            _build_system_prompt_preview,
            inputs=[topic_input, content_input, use_reference, subject_input, sub_field_input, level_input, style_input],
            outputs=[prompt_preview],
        )


if __name__ == "__main__":
    print("Starting Teaching Agent Test App...")
    print("Open http://localhost:7862 in your browser")
    print()
    app.launch(share=False, server_port=7862, theme=gr.themes.Soft())

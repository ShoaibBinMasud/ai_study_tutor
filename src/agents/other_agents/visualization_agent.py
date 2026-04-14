"""
VisualizationAgent — generates interactive HTML/SVG/JS diagrams for STEM concepts.

The LLM writes a self-contained HTML artifact (SVG + CSS + JS) tailored to the
concept being taught. Rendered in a sandboxed iframe in the React frontend.

Triggered only when the concept genuinely benefits from a visual:
  - Block diagrams, system diagrams, flow charts
  - Force diagrams, free body diagrams
  - Wave interference, oscillations, standing waves
  - Circuit diagrams, field lines
  - Graphs of functions (phase diagrams, energy curves, motion plots)
  - Algorithm visualizations, data structure diagrams
  - Reaction mechanisms, molecular orbital diagrams
  - NOT triggered for: pure definitions, historical facts, simple derivations
"""

import logging
from typing import Optional

from utils.llm_client import LLMClient

logger = logging.getLogger(__name__)

VISUALIZATION_PROMPT = """You are a world-class STEM illustrator creating a diagram for a premium private tutoring session.

The tutor just explained this concept and needs an accompanying visual:

Concept: {concept}
Subject: {subject}
Teaching context: {context}

Generate a SINGLE self-contained HTML page that illustrates this concept beautifully.

━━━ VISUAL STYLE ━━━
Think: Brilliant.org meets a high-end textbook. Clean, precise, academic.
- White background: `#ffffff`, body/page background `#f8f9fc`
- Primary text: `#1a1a2e`  |  Secondary/label text: `#4a5568`
- Accent palette: blue `#3b82f6`, red `#ef4444`, green `#10b981`, orange `#f59e0b`, purple `#8b5cf6`
- Font: `font-family: 'Inter', system-ui, sans-serif`
- Thin, crisp strokes: `stroke-width: 1.5` to `2` for lines, `2.5` for main elements
- Generous whitespace — never cramped

━━━ DIAGRAM REQUIREMENTS ━━━
Every diagram MUST have:
1. **A clear title** at the top — 14px, semi-bold, `#1a1a2e`
2. **Labeled elements** — every arrow, force, variable, axis, node, component must be labeled
3. **Arrowheads** — use SVG `<marker>` arrowheads for any directional arrow or force vector
4. **Annotations** — key values, equations, or explanatory notes placed near the relevant element
5. **Legend** if there are multiple distinct elements or colors

━━━ WHAT TO BUILD ━━━
Choose the most appropriate form for the concept:

- **Force / free body diagrams**: SVG with properly scaled labeled arrows. Show the object at center,
  every force as an arrow with label (F_c, mg, T, N…). Use color to distinguish force types.
- **Motion / trajectory diagrams**: SVG path with velocity/acceleration vectors, labeled waypoints
- **Wave / oscillation diagrams**: SVG or JS-animated sine curves with labeled λ, A, T, nodes
- **Energy / phase diagrams**: SVG with labeled axes, annotated curves, equilibrium points marked
- **Circuit diagrams**: SVG with standard IEC/IEEE symbols, labeled components and values
- **Block / system diagrams**: SVG with labeled boxes, directed edges, and signal annotations
- **Graphs of functions**: use inline JS (vanilla canvas or SVG path) to draw precise curves with
  labeled axes, tick marks, key points annotated (max, zero crossings, asymptotes)
- **Algorithm / data structure diagrams**: SVG with step-by-step node/edge layout
- **Molecular / orbital diagrams**: SVG with labeled bonds, angles, and orbital shapes
- **Interactive sliders**: if a parameter is central (e.g. vary frequency, mass, angle) add ONE
  clean HTML range slider with a live label — keep it minimal, never more than 2 controls

━━━ REQUIRED HTML SKELETON — use this exact outer structure ━━━
Your output MUST follow this skeleton. Fill in the title, styles, and diagram content:

<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{
    width: 100%; height: 100%;
    background: #f8f9fc;
    font-family: 'Inter', system-ui, sans-serif;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    overflow: hidden;
  }}
  .diagram-title {{
    font-size: 13px; font-weight: 600; color: #1a1a2e;
    margin-bottom: 10px; text-align: center; letter-spacing: 0.01em;
  }}
  /* add your own styles below */
</style>
</head>
<body>
  <div class="diagram-title">YOUR TITLE HERE</div>
  <svg viewBox="0 0 560 310" width="560" height="310"
       style="max-width:100%; max-height:310px; overflow:visible;">
    <!-- define arrowhead markers here -->
    <defs>
      <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
        <path d="M0,0 L0,6 L8,3 z" fill="#3b82f6"/>
      </marker>
    </defs>
    <!-- YOUR DIAGRAM ELEMENTS HERE — all coordinates within 0-560 x, 0-310 y -->
  </svg>
</body>
</html>

RULES for SVG coordinates:
- The canvas is 560 wide × 310 tall. Place the main subject at center (280, 155).
- Arrows: use <line> or <path> with marker-end="url(#arrow)"
- Labels: use <text> with font-size="13" fill="#1a1a2e" for main labels,
  font-size="11" fill="#4a5568" for secondary
- For colored arrows (forces): define one <marker> per color with a unique id
- All elements must be within the 560×310 coordinate space — nothing clipped

━━━ OTHER TECHNICAL RULES ━━━
- No external images, no fetch calls, no localStorage
- CDN allowed only for Chart.js (dynamic graphs) or MathJax (rendered equations)
- For interactive controls (sliders): add them between .diagram-title and the SVG,
  max 2 controls, styled minimally
- All math computed in JS — no hardcoded placeholder values

━━━ QUALITY BAR ━━━
Every arrow must be labeled. Every angle must be marked. Every axis must have a name.
Ask: "Can a student immediately read off the forces / relationships from this diagram?"
If not — add more labels, fix positions, simplify the layout.

OUTPUT: Return ONLY the complete HTML. No explanation, no markdown fences, no preamble."""


# Concepts that warrant a visual — checked against the teaching text
VISUAL_TRIGGERS = {
    # Physics
    "wave", "interference", "diffraction", "oscillat", "pendulum", "spring",
    "projectile", "trajectory", "free body", "force diagram", "field line",
    "electric field", "magnetic field", "potential well", "energy level",
    "quantum", "wavefunction", "simple harmonic", "doppler", "standing wave",
    "resonan", "blackbody", "photoelectric", "circuit", "resistor", "capacitor",
    "inductor", "torque", "angular momentum", "orbital", "kepler",
    # Math
    "graph", "function", "derivative", "integral", "vector field", "gradient",
    "eigenvalue", "transform", "fourier", "laplace", "matrix", "linear map",
    "phase portrait", "bifurcation", "limit cycle",
    # CS / Engineering
    "block diagram", "flowchart", "algorithm", "tree", "graph traversal",
    "sorting", "state machine", "feedback loop", "pid", "bode plot",
    "data structure", "stack", "queue", "linked list", "binary tree",
    # Chemistry / Biology
    "reaction mechanism", "molecular orbital", "energy diagram", "titration",
    "action potential", "membrane potential", "signal pathway",
}


class VisualizationAgent:
    """Generates interactive HTML/SVG/JS diagrams for STEM concepts."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def should_visualize(self, concept_text: str) -> bool:
        """Return True if this concept benefits from a diagram."""
        text_lower = concept_text.lower()
        return any(trigger in text_lower for trigger in VISUAL_TRIGGERS)

    def generate(self, concept: str, subject: str, context: str = "") -> Optional[str]:
        """
        Generate a self-contained HTML diagram for the concept.
        Returns the full HTML string, or None if generation fails.
        """
        prompt = VISUALIZATION_PROMPT.format(
            concept=concept,
            subject=subject,
            context=context[:400],
        )

        try:
            html = self.llm.get_completion(
                [{"role": "user", "content": prompt}],
                max_tokens=4000,
                temperature=0.3,
            )
            html = self._clean(html)

            if not html.strip().lower().startswith("<!"):
                logger.warning("[VIZ] Response doesn't look like HTML, discarding")
                return None

            logger.info(f"[VIZ] Generated HTML artifact ({len(html)} chars)")
            return html

        except Exception as e:
            logger.error(f"[VIZ] Failed: {e}")
            return None

    def _clean(self, html: str) -> str:
        """Strip markdown fences if the LLM wrapped the output."""
        html = html.strip()
        if html.startswith("```"):
            lines = html.splitlines()
            # Remove first line (``` or ```html) and last line (```)
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            html = "\n".join(lines)
        return html

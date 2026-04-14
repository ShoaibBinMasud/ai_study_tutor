# AI STEM Tutor

An autonomous AI tutor that reads your study materials and teaches you concept by concept — with prereq checks, adaptive pacing, quizzes, and interactive diagrams.

## How It Works

### 1. Upload → The system reads the book

Drop a PDF, PPTX, DOCX, or image. The system:
- Extracts the table of contents and sections
- Auto-detects subject, level, and teaching style (Physics equation-heavy vs Math proof-based vs CS code-focused)
- Builds a reference card per section (symbols, equation numbers, key examples) — used as a notation guide during teaching

### 2. Request → The agent plans

Tell it what you want:
- `"teach me section 1-2"` — single section
- `"teach me chapter 3"` — full chapter, section by section
- `"I have a midterm on chapters 1-5"` — diagnostic first, then prioritized plan
- `"what's covered in chapter 2?"` — TOC lookup, no teaching

Before teaching, it checks your background: *"Before we start — are you comfortable with vectors?"* It skips this only if you're already mid-chapter.

### 3. Teach → Concept by concept

The teaching subagent takes over:
- Teaches ONE concept per turn — intuition first, then equations, then derivation, then example
- Uses the book's equation numbers and notation, but teaches from its own expert knowledge
- Ends every concept with **"Is this clear? (Yes / No)"**
- Student says yes → next concept. Says no → asks which part, re-explains differently
- Generates an interactive HTML diagram when the concept benefits from one (waveforms, force diagrams, algorithm visualizations, etc.)

### 4. Summary + Quiz

When all concepts are covered:
- **Summary** — key concepts, equations to remember, main takeaway (LLM-generated from what was actually taught)
- **Quiz** — 3-4 questions grounded in the actual lesson (MC, open-answer, calculation problem)
- Evaluated question by question with feedback
- Weak areas noted at the end

For a full chapter: section-by-section teaching, then a chapter-wide summary + quiz at the end.

### 5. Adapt

A silent merit evaluator scores every student response and adjusts pace:
- Low understanding → slower, smaller chunks, more examples
- High understanding → faster, larger chunks

---

## Architecture

```
Student message
      │
      ▼
  TutorAgent.chat()
      │
      ├─ teaching_active? ──→ TeachingAgent.respond()        (concept-by-concept loop)
      ├─ quiz_ready?       ──→ confirm → show Q1
      ├─ quiz_active?      ──→ _handle_quiz_answer()          (evaluate + next question)
      │
      └─ main LLM loop (tool calling)
              │
              ├── show_toc()           → FileManager
              ├── load_chapter()       → read TOC, build section queue
              ├── load_section()       → extract content + reference card
              │                          → ask student prereq question
              ├── teach_chunk()        → TeachingAgent.start_unit_with_reference()
              │                          → VisualizationAgent (if concept needs diagram)
              ├── run_quiz()           → QuizAgent.generate_quiz() (uses teaching history)
              ├── run_diagnostic()     → DiagnosticAgent
              └── search_topic()      → FileManager
```

**Key design decisions:**
- LLM decides everything about pedagogy (when to ask prereqs, how to explain, what to emphasize) — no hardcoded rules
- Python owns all state (session dict, queues, flags) — LLM reads it as context, never writes it directly
- Three fast paths bypass the main LLM during teaching and quizzing — instant responses, no tool overhead
- Teaching agent gets a compact reference card, not raw PDF text — teaches from its own expert knowledge and cites the book's notation

---

## Setup

**Requirements:** Python 3.10+, Node 18+

```bash
# 1. Clone and install
pip install -r requirements.txt

# 2. Environment
echo "OPENAI_API_KEY=your_key_here" > .env

# 3. Run backend
python server.py          # → http://localhost:8000

# 4. Run frontend (separate terminal)
cd frontend
npm install
npm run dev               # → http://localhost:5173
```

Open `http://localhost:5173`, upload a PDF, and start learning.

---

## Supported File Types

| Type | How processed |
|---|---|
| PDF | PyMuPDF — TOC extraction + page text |
| PPTX | python-pptx — slide text + speaker notes |
| DOCX | python-docx — heading-structured text |
| Images (PNG, JPG) | Vision LLM — handwritten notes, whiteboard photos |
| Markdown / TXT | Direct parse, headings become TOC |

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | required | OpenAI API key |
| `TUTOR_MODEL` | `gpt-4o-mini` | Any OpenAI-compatible model |

---

## Project Structure

```
ai_study_tutor/
├── server.py                    # FastAPI backend
├── app.py                       # Gradio UI (legacy, kept for testing)
├── requirements.txt
├── .env
├── frontend/                    # React + TypeScript + Vite
│   └── src/
│       ├── App.tsx
│       ├── api.ts               # Typed fetch wrappers
│       └── components/
│           ├── Chat.tsx
│           ├── Message.tsx      # Markdown + KaTeX rendering
│           ├── Diagram.tsx      # Sandboxed iframe for HTML diagrams
│           └── FileUpload.tsx
└── src/
    ├── agents/
    │   ├── tutor_agent.py       # Main orchestrator
    │   ├── teaching_agent.py    # Concept-by-concept teaching
    │   ├── quiz_agent.py        # Quiz generation + evaluation
    │   ├── visualization_agent.py  # HTML/SVG/JS diagram generation
    │   ├── merit_evaluator.py   # Silent adaptive scoring
    │   └── diagnostic_agent.py  # Prereq assessment
    ├── content/
    │   ├── file_manager.py      # Multi-file management, TOC, section lookup
    │   ├── document_processor.py
    │   ├── concept_mapper.py
    │   └── chunker.py
    ├── models/
    │   └── data_models.py       # All dataclasses
    ├── tools/
    │   ├── pdf_content_navigator.py
    │   └── pdf_extraction_tool.py
    └── utils/
        └── llm_client.py
```

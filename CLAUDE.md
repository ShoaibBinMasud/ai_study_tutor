# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Quick Start

```bash
# Backend
pip install -r requirements.txt
cp .env.example .env          # add OPENAI_API_KEY
python server.py              # FastAPI on :8000

# Frontend
cd frontend
npm install
npm run dev                   # Vite on :5173
```

## Architecture

Three-layer agentic system:

```
Upload → FileManager → DocumentProcessor → subject detection
                                         → reference card extraction

Chat   → TutorAgent (main LLM loop, tool calling)
              ├── TeachingAgent   (subagent — owns concept-by-concept teaching)
              ├── QuizAgent       (subagent — generates + evaluates questions)
              ├── MeritEvaluator  (subagent — silent scoring, adapts pace)
              ├── VisualizationAgent (generates HTML/SVG/JS diagrams)
              └── DiagnosticAgent (prereq assessment for exam prep)
```

## Key Files

| File | Purpose |
|---|---|
| `server.py` | FastAPI: `/upload`, `/chat`, `/reset` |
| `src/agents/tutor_agent.py` | Main orchestrator — tool loop, fast paths, session state |
| `src/agents/teaching_agent.py` | Teaching subagent — concept-by-concept with reference card |
| `src/agents/quiz_agent.py` | Quiz generation + answer evaluation |
| `src/agents/visualization_agent.py` | LLM-generated HTML/SVG/JS diagrams |
| `src/content/file_manager.py` | Multi-file management, TOC, section lookup |
| `src/content/document_processor.py` | Routes files to PDF/PPTX/DOCX/image processors |
| `frontend/src/` | React + TypeScript + Vite UI |

## Control Flow in TutorAgent.chat()

Three fast paths (in order) before hitting the main LLM loop:

1. `teaching_active` → all messages go to `TeachingAgent.respond()`
2. `quiz_ready` → yes/skip confirmation, then show Q1
3. `quiz_active` → all messages go to `_handle_quiz_answer()`
4. Main LLM loop → tool calling (load_section, teach_chunk, etc.)

Teaching ends with `UNIT_COMPLETE` signal → quiz auto-fires (single section) or next section announced (chapter mode).

## Session State Keys

```python
session = {
    "teaching_active": bool,        # fast path 1
    "quiz_ready": bool,             # fast path 2
    "quiz_active": bool,            # fast path 3
    "loaded_section_id": str,
    "loaded_section": Section,
    "reference_card": str,          # extracted symbols/equations — teaching guide
    "chunks": list,                 # section split for pacing
    "merit_score": float,           # 0-10, EWMA updated
    "adaptation": AdaptationLevel,
    "sections_completed": list,
    "last_taught_section_id": str,
    "chapter_mode": bool,
    "chapter_section_queue": list,
    "chapter_sections_done": list,
    "chapter_reference_cards": dict,  # for chapter summary before quiz
    "active_quiz": QuizResult,
    "quiz_question_index": int,
}
```

## Design Principles

- **Trust the LLM for decisions, Python for state.** No heuristics, regex, or rule trees for pedagogical decisions — just clear natural language context + session memory in the system prompt.
- **Fast paths over tool calls for hot loops.** Teaching and quiz flows bypass the main LLM entirely once initiated — instant responses, no routing overhead.
- **Reference card, not raw content.** Teaching agent gets a compact extracted card (symbols, equations, topics) and teaches from its own knowledge. Richer, faster than dumping raw PDF text.
- **HTML diagrams, not matplotlib.** Visualization agent generates self-contained HTML/SVG/JS — interactive, no code execution risk, renders in sandboxed iframe.

## Environment

```
OPENAI_API_KEY=...
TUTOR_MODEL=gpt-4o-mini   # optional, default gpt-4o-mini
```

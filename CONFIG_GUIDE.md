# Model Configuration Guide

The AI STEM Tutor uses a centralized configuration system to manage LLM models per agent type. This makes it easy to switch models without editing code.

## Quick Start

Edit [`src/config.py`](src/config.py) and modify the `MODELS` dictionary:

```python
MODELS = {
    "teaching_agent": {
        "model": "gpt-4o",          # Change this line
        "api_provider": "openai",
    },
    # ... other agents ...
}
```

## Available Models

### OpenAI
- `gpt-4o` — Most capable, best quality teaching output
- `gpt-4o-mini` — Smaller, faster, cheaper
- `gpt-4-turbo` — Previous generation

### Google (Gemini)
- `gemini-2.0-flash` — Fast, good for structured output (planning)
- `gemini-2.0-pro` — Most capable

### Anthropic (Claude)
- `claude-opus-4-6` — Most capable Claude model
- `claude-sonnet-4-6` — Balanced quality/speed

## Agents and Recommended Models

| Agent | Purpose | Recommended Model | Rationale |
|-------|---------|-------------------|-----------|
| `teaching_agent` | Student-facing tutoring | `gpt-4o` | Highest quality, needs rich explanations |
| `tutor_agent` | Main orchestrator, routing | `gpt-4o` | Handles complex reasoning |
| `quiz_agent` | Quiz generation | `gpt-4o-mini` | Straightforward task, cost-sensitive |
| `planner_agent` | Curriculum planning | `gemini-2.0-flash` | Fast JSON output, structured data |
| `merit_evaluator` | Progress tracking | `gpt-4o-mini` | Quick scoring pass |
| `visualization_agent` | Diagram generation | `gpt-4o` | Complex reasoning for HTML/SVG |
| `diagnostic_agent` | Exam prep assessment | `gpt-4o` | Needs pedagogical depth |

## Cost vs Quality Trade-offs

### Budget-Conscious (Low Cost)
```python
MODELS = {
    "teaching_agent": {"model": "gpt-4o-mini", "api_provider": "openai"},
    "tutor_agent": {"model": "gpt-4o-mini", "api_provider": "openai"},
    "planner_agent": {"model": "gemini-2.0-flash", "api_provider": "google"},
}
```

### Premium (Best Quality)
```python
MODELS = {
    "teaching_agent": {"model": "gpt-4o", "api_provider": "openai"},
    "tutor_agent": {"model": "gpt-4o", "api_provider": "openai"},
    "planner_agent": {"model": "gemini-2.0-pro", "api_provider": "google"},
}
```

### Claude-focused (Anthropic API)
```python
MODELS = {
    "teaching_agent": {"model": "claude-opus-4-6", "api_provider": "anthropic"},
    "tutor_agent": {"model": "claude-opus-4-6", "api_provider": "anthropic"},
}
```

## Environment Setup

Make sure you have API keys in your `.env` file:

```bash
# OpenAI
OPENAI_API_KEY=sk-...

# Google (Gemini)
GOOGLE_API_KEY=...

# Anthropic (Claude)
ANTHROPIC_API_KEY=...
```

## Using Config in Code

```python
from config import get_model, get_model_config
from utils.llm_client import LLMClient

# Get the model name
model = get_model("teaching_agent")  # Returns "gpt-4o"

# Get full config
config = get_model_config("teaching_agent")
# Returns: {"model": "gpt-4o", "api_provider": "openai"}

# Create LLM client with config
llm = LLMClient(model=get_model("teaching_agent"))
response = llm.get_completion(messages, max_tokens=2000)
```

## Testing Your Configuration

Run the teaching agent test:

```bash
python test_plan_driven_tutor.py
```

You'll see the configured model being used in the system prompt and responses.

## Key Files

- [`src/config.py`](src/config.py) — Central configuration
- [`src/utils/llm_client.py`](src/utils/llm_client.py) — LLM client that accepts model parameter
- [`test_plan_driven_tutor.py`](test_plan_driven_tutor.py) — CLI test using config
- [`test_plan_driven_tutor_app.py`](test_plan_driven_tutor_app.py) — Gradio app using config

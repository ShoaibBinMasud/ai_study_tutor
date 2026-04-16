"""
Configuration for AI STEM Tutor — model selection per agent type.

Modify this file to change which LLM model each agent uses.
All agents support: OpenAI (gpt-4, gpt-4o, gpt-4o-mini), Gemini (gemini-2.0-flash, etc.)
"""

# ─── Model Configuration ────────────────────────────────────────────────────

MODELS = {
    # Top-level orchestrator — routes to document/planner/teaching agents
    "supervisor": {
        "model": "gpt-4o",  # Strong model for orchestration decisions
        "api_provider": "openai",
    },

    # Legacy orchestrator (kept for backwards compatibility)
    "tutor_agent": {
        "model": "gpt-4o",
        "api_provider": "openai",
    },

    # Student-facing tutor — teaches one concept/unit at a time
    "teaching_agent": {
        "model": "gpt-4o",  # Switch to gpt-4o for higher quality vs gpt-4o-mini
        "api_provider": "openai",
    },

    # Quiz generation + answer evaluation
    "quiz_agent": {
        "model": "gpt-5-mini",  # Lightweight, quiz generation is straightforward
        "api_provider": "openai",
    },

    # Learning plan generator — analyzes curriculum and creates final_learning_path
    "planner_agent": {
        "model": "gemini-2.0-flash",  # Fast, good at structured output (JSON)
        "api_provider": "google",
    },

    # Silent merit scoring and pacing adaptation
    "merit_evaluator": {
        "model": "gpt-4o-mini",  # Quick pass over student responses
        "api_provider": "openai",
    },

    # HTML/SVG/JS diagram generator
    "visualization_agent": {
        "model": "gpt-4o",
        "api_provider": "openai",
    },

    # Prerequisite assessment (exam prep mode)
    "diagnostic_agent": {
        "model": "gpt-4o",
        "api_provider": "openai",
    },
}

# ─── Convenience getter ────────────────────────────────────────────────────

def get_model_config(agent_name: str) -> dict:
    """
    Get model configuration for an agent.

    Args:
        agent_name: e.g., "teaching_agent", "tutor_agent", "quiz_agent"

    Returns:
        {"model": str, "api_provider": str}

    Raises:
        ValueError if agent_name not found.
    """
    if agent_name not in MODELS:
        raise ValueError(
            f"Unknown agent: {agent_name}. "
            f"Available: {', '.join(MODELS.keys())}"
        )
    return MODELS[agent_name]


def get_model(agent_name: str) -> str:
    """Convenience: get just the model name."""
    return get_model_config(agent_name)["model"]


def get_api_provider(agent_name: str) -> str:
    """Convenience: get just the API provider."""
    return get_model_config(agent_name)["api_provider"]


# ─── Usage examples ────────────────────────────────────────────────────────

# In any agent:
#
#   from src.config import get_model
#   from src.utils.llm_client import LLMClient
#
#   model = get_model("teaching_agent")
#   llm = LLMClient(model=model)
#   response = llm.get_completion(messages, max_tokens=2000)

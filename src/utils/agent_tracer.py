"""
Agent Tracer — logs tool calls, responses, and LLM reasoning for debugging.

Captures:
- LLM reasoning (why did it decide to call this tool?)
- Tool name + arguments
- Tool response
- Execution time
- Errors

Usage:
    tracer = AgentTracer()
    tracer.start_turn(request)
    tracer.log_reasoning(llm_message)
    tracer.log_tool_call(name, args, response, elapsed)
    tracer.log_error(error)
    trace = tracer.end_turn()
    print(tracer.format_trace(trace))
"""

import json
import logging
import time
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """Single tool invocation."""
    iteration: int
    tool_name: str
    arguments: Dict[str, Any]
    response: str
    elapsed_ms: float
    error: Optional[str] = None


@dataclass
class AgentTrace:
    """Complete trace of an agent's decision-making."""
    request: str
    timestamp: str
    reasoning: str  # why the agent decided to call tools
    tool_calls: List[ToolCall] = field(default_factory=list)
    final_response: str = ""
    total_elapsed_ms: float = 0.0


class AgentTracer:
    """Track tool calls and reasoning during agent execution."""

    def __init__(self):
        self.trace: Optional[AgentTrace] = None
        self.start_time: Optional[float] = None
        self.iteration = 0

    def start_turn(self, request: str) -> None:
        """Begin tracing a new agent turn."""
        self.trace = AgentTrace(
            request=request,
            timestamp=datetime.now().isoformat(),
            reasoning="",
        )
        self.start_time = time.time()
        self.iteration = 0

    def log_reasoning(self, llm_message: str) -> None:
        """Capture the LLM's reasoning before tool calls."""
        if self.trace:
            self.trace.reasoning = llm_message.strip()

    def log_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        response: str,
        elapsed_ms: float = 0.0,
    ) -> None:
        """Log a single tool invocation."""
        self.iteration += 1
        if self.trace:
            call = ToolCall(
                iteration=self.iteration,
                tool_name=tool_name,
                arguments=arguments,
                response=response[:500],  # cap response to avoid bloat
                elapsed_ms=elapsed_ms,
            )
            self.trace.tool_calls.append(call)

    def log_error(self, error: str) -> None:
        """Log an error in the current tool call."""
        if self.trace and self.trace.tool_calls:
            self.trace.tool_calls[-1].error = error

    def end_turn(self, final_response: str = "") -> AgentTrace:
        """End tracing and return the trace."""
        if self.trace:
            self.trace.final_response = final_response[:1000]  # cap
            if self.start_time:
                self.trace.total_elapsed_ms = (time.time() - self.start_time) * 1000
        return self.trace

    @staticmethod
    def format_trace(trace: AgentTrace) -> str:
        """Format trace as human-readable markdown."""
        lines = []
        lines.append(f"## Trace: {trace.timestamp}\n")
        lines.append(f"**Request:** {trace.request}\n")
        lines.append(f"**LLM Reasoning:** {trace.reasoning}\n")

        if trace.tool_calls:
            lines.append("### Tool Calls\n")
            for call in trace.tool_calls:
                lines.append(f"**[{call.iteration}] {call.tool_name}**")
                lines.append(f"- Args: `{json.dumps(call.arguments, indent=2)}`")
                lines.append(f"- Response (first 200 chars): `{call.response[:200]}...`")
                if call.error:
                    lines.append(f"- Error: `{call.error}`")
                lines.append(f"- Time: {call.elapsed_ms:.1f}ms\n")

        lines.append(f"**Total Time:** {trace.total_elapsed_ms:.0f}ms")
        lines.append(f"**Tool Calls Made:** {len(trace.tool_calls)}\n")

        return "\n".join(lines)

    @staticmethod
    def format_trace_json(trace: AgentTrace) -> str:
        """Format trace as JSON for structured analysis."""
        return json.dumps(asdict(trace), indent=2)

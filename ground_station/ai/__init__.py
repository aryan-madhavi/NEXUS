"""NEXUS Conversational AI Package.

Provides a read-only, evidence-grounded conversational AI layer for
NEXUS telemetry, statistics, and operational incidents.
"""

from .agent import AgentResponse, NexusConversationalAgent
from .prompts import SYSTEM_PROMPT
from .tool_registry import ALLOWED_TOOL_NAMES, TOOL_DEFINITIONS, ToolDispatcher
from .tools import NexusAITools, ToolResult

__all__ = [
    "AgentResponse",
    "ALLOWED_TOOL_NAMES",
    "NexusAITools",
    "NexusConversationalAgent",
    "SYSTEM_PROMPT",
    "TOOL_DEFINITIONS",
    "ToolDispatcher",
    "ToolResult",
]

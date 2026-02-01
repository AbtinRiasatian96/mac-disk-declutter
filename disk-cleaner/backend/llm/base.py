"""Abstract LLM provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AnalysisResult:
    safety_score: int  # 0-100, higher = safer to delete
    description: str
    consequence: str
    category: str  # "safe", "review", "personal"


@dataclass
class ChatMessage:
    role: str  # "user" or "assistant"
    content: str


@dataclass
class AgentStep:
    """Represents a step in multi-step agentic reasoning (V2+)."""
    thought: str = ""
    action: str = ""
    observation: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class LLMProvider(ABC):
    """Abstract interface for LLM providers.

    Designed to support future agentic capabilities:
    - analyze_item: single-shot analysis (V1)
    - chat: conversational interface (V1)
    - analyze_with_reasoning: multi-step chain-of-thought (V2+)
    """

    @abstractmethod
    async def analyze_item(self, path: str, metadata: dict) -> AnalysisResult:
        """Analyze a single scanned item for deletion safety."""
        ...

    @abstractmethod
    async def chat(self, messages: list[ChatMessage], context: dict) -> str:
        """Send a chat message with scan context."""
        ...

    async def analyze_with_reasoning(self, path: str, metadata: dict) -> tuple[AnalysisResult, list[AgentStep]]:
        """Multi-step agentic analysis (V2+). Default falls back to single-shot."""
        result = await self.analyze_item(path, metadata)
        return result, []

    def _build_analysis_prompt(self, path: str, metadata: dict) -> str:
        return f"""Analyze this file/folder for a Mac disk cleanup tool.

Path: {path}
Size: {metadata.get('size_human', 'unknown')}
Type: {metadata.get('type', 'unknown')}
Category: {metadata.get('category', 'unknown')}
Last modified: {metadata.get('last_modified', 'unknown')}
Item count: {metadata.get('item_count', 'N/A')}

Respond in exactly this JSON format (no markdown):
{{
  "safety_score": <0-100, higher means safer to delete>,
  "description": "<brief 1-sentence description of what this is>",
  "consequence": "<what happens if deleted, 1 sentence>"
}}"""

    def _build_chat_system_prompt(self, context: dict) -> str:
        scan_summary = context.get("scan_summary", "No scan results available.")
        selection = context.get("selected_items", [])
        return f"""You are a helpful Mac disk cleanup assistant. You have access to the user's scan results and can answer questions about files, safety, and disk usage.

Current scan results summary:
{scan_summary}

Currently selected for deletion:
{json.dumps(selection, indent=2) if selection else "Nothing selected."}

Be concise and helpful. If asked about safety, err on the side of caution."""


import json

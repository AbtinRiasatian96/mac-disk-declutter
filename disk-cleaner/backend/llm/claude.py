"""Claude API LLM provider."""

import json
import anthropic
from .base import LLMProvider, AnalysisResult, ChatMessage


class ClaudeProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model

    async def analyze_item(self, path: str, metadata: dict) -> AnalysisResult:
        prompt = self._build_analysis_prompt(path, metadata)
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            text = response.content[0].text.strip()
            data = json.loads(text)
            return AnalysisResult(
                safety_score=int(data["safety_score"]),
                description=data["description"],
                consequence=data["consequence"],
                category=metadata.get("category", "review"),
            )
        except Exception as e:
            return AnalysisResult(
                safety_score=50,
                description=f"Analysis failed: {e}",
                consequence="Unknown — review manually.",
                category=metadata.get("category", "review"),
            )

    async def chat(self, messages: list[ChatMessage], context: dict) -> str:
        system_prompt = self._build_chat_system_prompt(context)
        api_messages = [{"role": m.role, "content": m.content} for m in messages]
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system_prompt,
                messages=api_messages,
            )
            return response.content[0].text
        except Exception as e:
            return f"Error communicating with Claude: {e}"

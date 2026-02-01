"""Ollama (local) LLM provider."""

import json
import httpx
from .base import LLMProvider, AnalysisResult, ChatMessage


class OllamaProvider(LLMProvider):
    def __init__(self, model: str = "llama3", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")

    async def _generate(self, prompt: str, system: str = "") -> str:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "system": system,
                    "stream": False,
                },
            )
            resp.raise_for_status()
            return resp.json()["response"]

    async def analyze_item(self, path: str, metadata: dict) -> AnalysisResult:
        prompt = self._build_analysis_prompt(path, metadata)
        try:
            text = await self._generate(prompt)
            # Try to extract JSON from response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(text[start:end])
                return AnalysisResult(
                    safety_score=int(data.get("safety_score", 50)),
                    description=data.get("description", "No description"),
                    consequence=data.get("consequence", "Unknown"),
                    category=metadata.get("category", "review"),
                )
        except Exception:
            pass
        return AnalysisResult(
            safety_score=50,
            description="Analysis unavailable (Ollama error)",
            consequence="Review manually.",
            category=metadata.get("category", "review"),
        )

    async def chat(self, messages: list[ChatMessage], context: dict) -> str:
        system_prompt = self._build_chat_system_prompt(context)
        # Ollama generate API: concatenate messages into a single prompt
        conversation = ""
        for m in messages:
            prefix = "User" if m.role == "user" else "Assistant"
            conversation += f"{prefix}: {m.content}\n"
        conversation += "Assistant:"
        try:
            return await self._generate(conversation, system=system_prompt)
        except Exception as e:
            return f"Error communicating with Ollama: {e}"

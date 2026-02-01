"""LLM analysis orchestration."""

import asyncio
from backend.llm.base import LLMProvider, AnalysisResult, ChatMessage
from backend.llm.claude import ClaudeProvider
from backend.llm.ollama import OllamaProvider
from backend.config import load_config


def get_provider(config: dict | None = None) -> LLMProvider:
    if config is None:
        config = load_config()
    provider = config.get("llm_provider", "claude")
    if provider == "claude":
        api_key = config.get("claude_api_key", "")
        model = config.get("claude_model", "claude-sonnet-4-20250514")
        return ClaudeProvider(api_key=api_key, model=model)
    else:
        model = config.get("ollama_model", "llama3")
        url = config.get("ollama_url", "http://localhost:11434")
        return OllamaProvider(model=model, base_url=url)


async def analyze_items(items: list[dict], provider: LLMProvider, max_concurrent: int = 5) -> list[dict]:
    """Analyze a list of scanned items with the LLM provider.

    Returns items enriched with analysis results.
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def analyze_one(item: dict) -> dict:
        async with semaphore:
            result = await provider.analyze_item(item["path"], item)
            item["safety_score"] = result.safety_score
            item["description"] = result.description
            item["consequence"] = result.consequence
            return item

    tasks = [analyze_one(item) for item in items]
    analyzed = await asyncio.gather(*tasks)

    # Re-sort by ROI: size * safety_score
    analyzed_list = list(analyzed)
    analyzed_list.sort(key=lambda x: x["size"] * x.get("safety_score", 50), reverse=True)
    return analyzed_list


def build_scan_summary(items: list[dict]) -> str:
    """Build a text summary of scan results for chat context."""
    if not items:
        return "No scan has been performed yet."
    total_size = sum(i["size"] for i in items)
    from backend.scanner import human_size
    lines = [f"Total scannable: {human_size(total_size)}", f"Items found: {len(items)}", ""]
    for item in items[:30]:  # Top 30 for context
        safety = item.get("safety_score", "?")
        lines.append(f"- {item['name']} ({item['size_human']}) safety={safety} [{item['category']}]")
    if len(items) > 30:
        lines.append(f"... and {len(items) - 30} more items")
    return "\n".join(lines)

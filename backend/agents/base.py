from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from core.feedback_engine import feedback_engine
from core.model_router import model_router
from services.ollama_client import OllamaClient


@dataclass
class AgentResult:
    agent_name: str
    success: bool
    output: dict[str, Any]
    error: str | None = None


class BaseAgent(ABC):
    """Base class for all Travel Agents."""

    name: str
    description: str
    dependencies: list[str] = []

    def __init__(self, ollama_client: OllamaClient, db_session):
        self.ollama = ollama_client
        self.db = db_session

    @abstractmethod
    async def execute(self, project_id: str, context: dict) -> AgentResult:
        """Execute the agent's task. Context includes outputs from dependency agents."""
        ...

    async def _generate(self, system_prompt: str, user_prompt: str, model: str | None = None) -> str:
        """Helper to call Ollama with model router and feedback integration."""
        task_type = f"agent_{self.name}" if hasattr(self, "name") else "agent"
        model = model or await model_router.get_model(task_type)

        style_injection = feedback_engine.get_style_prompt_injection()
        if style_injection:
            user_prompt = user_prompt + "\n" + style_injection

        return await self.ollama.generate(model=model, prompt=user_prompt, system=system_prompt)

    async def _generate_json(self, system_prompt: str, user_prompt: str, model: str | None = None) -> dict:
        """Generate and parse JSON output from the LLM."""
        import json

        raw = await self._generate(system_prompt, user_prompt, model)
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError(f"Agent '{self.name}' received non-JSON response: {raw[:200]}")
        return json.loads(raw[start:end])

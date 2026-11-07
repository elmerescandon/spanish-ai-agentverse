"""Shared pytest fixtures and test doubles for the protocol parser suite."""

from collections.abc import Sequence

from pydantic import BaseModel

from backend.clients.gemini import ThinkingLevel


class FakeJsonGenerator:
    """In-memory JsonGenerator test double that replays scripted responses."""

    def __init__(self, responses: Sequence[BaseModel | Exception]) -> None:
        self._responses: list[BaseModel | Exception] = list(responses)
        self.prompts: list[str] = []
        self.thinking_levels: list[ThinkingLevel] = []

    async def generate_json[ModelT: BaseModel](
        self,
        prompt: str,
        response_model: type[ModelT],
        thinking_level: ThinkingLevel = ThinkingLevel.MEDIUM,
    ) -> ModelT:
        """Record the prompt and return or raise the next scripted item."""
        self.prompts.append(prompt)
        self.thinking_levels.append(thinking_level)
        if not self._responses:
            raise AssertionError(
                "FakeJsonGenerator ran out of scripted responses"
            )
        next_item = self._responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        assert isinstance(next_item, response_model)
        return next_item

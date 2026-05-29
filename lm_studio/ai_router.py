"""Small router that prefers LM Studio when it is available."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import httpx

from lm_studio import client

Fallback = Callable[[str], str]


@dataclass
class AIRouter:
    """
    Route prompts to LM Studio or to a caller-provided fallback.

    mode:
        auto: use LM Studio when reachable, otherwise fallback
        lm_studio: require LM Studio
        fallback: always use fallback
    """

    mode: str = "auto"
    fallback: Fallback | None = None

    def ask(
        self,
        prompt: str,
        *,
        system: str = "Tu es un assistant expert en trading algorithmique et Python.",
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        mode = self.mode.lower()
        if mode not in {"auto", "lm_studio", "fallback"}:
            raise ValueError(f"Mode AI inconnu: {self.mode}")

        if mode == "fallback":
            return self._ask_fallback(prompt)

        if mode == "lm_studio" or client.is_available():
            try:
                return client.chat(
                    prompt,
                    system=system,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except httpx.HTTPError:
                if mode == "lm_studio":
                    raise
                return self._ask_fallback(prompt)

        return self._ask_fallback(prompt)

    def _ask_fallback(self, prompt: str) -> str:
        if self.fallback is None:
            raise RuntimeError("Aucun fallback AI configure et LM Studio indisponible")
        return self.fallback(prompt)


def ask_ai(prompt: str, **kwargs) -> str:
    """Convenience wrapper for the default automatic route."""
    return AIRouter().ask(prompt, **kwargs)

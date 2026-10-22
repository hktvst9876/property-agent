"""
llm/providers/deepseek_provider.py — DeepSeek brain.

DeepSeek's API is OpenAI-compatible: it runs over the openai SDK pointed at
https://api.deepseek.com with DEEPSEEK_API_KEY instead of OPENAI_API_KEY.

supports_decisions = True: DeepSeek V3 (deepseek-chat) is capable of the
judgment quality required for DRAFTING and INTAKE tasks. To route any task
here, set the value to "deepseek" in config.PROVIDER_MAP.

Install: pip install openai   (same SDK the openai_provider already uses).
"""

from __future__ import annotations
import json
import os
import time

from llm.providers.base import AIProvider


class DeepSeekProvider(AIProvider):
    name = "deepseek"
    supports_decisions = True   # V3 / R1 capable; user's explicit choice.

    def __init__(self,
                 reasoning_model: str = "deepseek-chat",
                 cheap_model: str = "deepseek-chat"):
        self.reasoning_model = reasoning_model
        self.cheap_model = cheap_model
        self._client = None

    def available(self) -> bool:
        if not os.environ.get("DEEPSEEK_API_KEY"):
            return False
        try:
            import openai  # noqa: F401 — DeepSeek uses the OpenAI SDK
            return True
        except ImportError:
            return False

    def _client_or_init(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(
                api_key=os.environ["DEEPSEEK_API_KEY"],
                base_url="https://api.deepseek.com",
            )
        return self._client

    def _model_for(self, tier: str) -> str:
        return self.cheap_model if tier == "cheap" else self.reasoning_model

    def ask_json(self, system: str, user: str, *,
                 max_tokens: int = 600, tier: str = "reasoning") -> dict:
        import openai
        client = self._client_or_init()
        last_err = None
        for attempt in range(3):
            try:
                resp = client.chat.completions.create(
                    model=self._model_for(tier),
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
                text = resp.choices[0].message.content.strip()
                text = text.replace("```json", "").replace("```", "").strip()
                return json.loads(text)
            except openai.RateLimitError as exc:
                last_err = exc
                time.sleep(2 ** attempt)
            except (openai.APIError, json.JSONDecodeError, IndexError, AttributeError) as exc:
                last_err = exc
                if attempt == 2:
                    break
                time.sleep(1)
        return {"_error": f"{type(last_err).__name__}: {last_err}"}

    def ask_text(self, system: str, user: str, *,
                 max_tokens: int = 400, tier: str = "reasoning") -> str:
        import openai
        client = self._client_or_init()
        try:
            resp = client.chat.completions.create(
                model=self._model_for(tier),
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            return resp.choices[0].message.content.strip()
        except (openai.APIError, IndexError, AttributeError) as exc:
            return f"(LLM unavailable: {exc})"

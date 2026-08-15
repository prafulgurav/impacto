"""Gemini narration.

Prefers the `google-genai` SDK and falls back to the REST endpoint over httpx when
it is not installed. httpx is already a core dependency, so this keeps Gemini usable
on a deployment that has not installed the optional extra — which matters because
the choice of narration provider is an env-var change, not a redeploy.
"""
from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from .base import LLMError

_REST_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Narration must not drift from the retrieved facts, so sampling is kept tight.
_TEMPERATURE = 0.2

# Gemini reports why generation stopped; anything other than these means the answer
# is truncated or was blocked, and a partial narration must never reach a user.
_OK_FINISH = {"STOP", "FINISH_REASON_UNSPECIFIED", None}


class GeminiProvider:
    """Wraps google-genai (or the REST API) behind the LLMProvider contract."""

    name = "gemini"

    def __init__(self, api_key: str, model: str, max_tokens: int = 1200, timeout: float = 30.0):
        self._api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self._timeout = timeout
        self._client = None
        self._types = None
        try:
            from google import genai
            from google.genai import types

            self._client = genai.Client(api_key=api_key)
            self._types = types
        except ImportError:
            # REST fallback path; no error until a call is actually attempted.
            pass

    # --------------------------------------------------------------- sdk
    def _config(self, system: str):
        return self._types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=self.max_tokens,
            temperature=_TEMPERATURE,
        )

    # -------------------------------------------------------------- rest
    def _rest_body(self, system: str, user: str) -> dict:
        return {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "maxOutputTokens": self.max_tokens,
                "temperature": _TEMPERATURE,
            },
        }

    @staticmethod
    def _rest_text(payload: dict) -> str:
        candidates = payload.get("candidates") or []
        if not candidates:
            # No candidate at all means a prompt-level block.
            raise LLMError("gemini returned no candidates")
        candidate = candidates[0]
        finish = candidate.get("finishReason")
        if finish not in _OK_FINISH:
            raise LLMError(f"gemini stopped early: {finish}")
        parts = candidate.get("content", {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts)

    def _rest_url(self, method: str) -> str:
        return f"{_REST_BASE}/{self.model}:{method}"

    @property
    def _headers(self) -> dict:
        return {"x-goog-api-key": self._api_key, "content-type": "application/json"}

    # ------------------------------------------------------------- api
    def complete(self, system: str, user: str) -> str:
        if self._client is not None:
            try:
                resp = self._client.models.generate_content(
                    model=self.model, contents=user, config=self._config(system)
                )
            except Exception as exc:  # google-genai raises a broad family of errors
                raise LLMError(f"gemini request failed: {exc}") from exc
            return (resp.text or "").strip()

        try:
            r = httpx.post(
                self._rest_url("generateContent"),
                headers=self._headers,
                json=self._rest_body(system, user),
                timeout=self._timeout,
            )
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMError(f"gemini request failed: {exc}") from exc
        return self._rest_text(r.json()).strip()

    def stream(self, system: str, user: str) -> Iterator[str]:
        if self._client is not None:
            try:
                chunks = self._client.models.generate_content_stream(
                    model=self.model, contents=user, config=self._config(system)
                )
                for chunk in chunks:
                    if chunk.text:
                        yield chunk.text
            except Exception as exc:
                raise LLMError(f"gemini stream failed: {exc}") from exc
            return

        try:
            with httpx.stream(
                "POST",
                self._rest_url("streamGenerateContent"),
                params={"alt": "sse"},
                headers=self._headers,
                json=self._rest_body(system, user),
                timeout=self._timeout,
            ) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = json.loads(line[5:].strip())
                    for part in (
                        payload.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [])
                    ):
                        if part.get("text"):
                            yield part["text"]
        except (httpx.HTTPError, json.JSONDecodeError, IndexError) as exc:
            raise LLMError(f"gemini stream failed: {exc}") from exc


__all__ = ["GeminiProvider"]

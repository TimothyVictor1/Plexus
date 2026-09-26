"""Google Gemini provider (spec 09).

One of only two places in the repository allowed to talk to a model vendor. Everything it
receives has already been through the PII Boundary, so no real personal value reaches Google.

The HTTP surface is small and stable enough that the REST API is used directly rather than
adding a vendor SDK: fewer moving parts, and the request body stays inspectable, which the
brief asks for.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from core.models.types import (
    Completion,
    Message,
    ModelId,
    ModelUnavailableError,
    SchemaValidationError,
    Usage,
)

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_TIMEOUT = 60.0
# Overload and rate limiting are normal on a shared endpoint, so they are retried rather than
# surfaced as a failure. A 4xx that is not 429 means the request itself is wrong: no retry.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 4
# Overload clears in seconds. A quota is measured per minute, so it needs a real wait rather
# than a handful of fast retries, and the server usually says how long.
BACKOFF_OVERLOAD = 0.8
BACKOFF_QUOTA = 6.0
MAX_BACKOFF = 45.0


class GoogleProvider:
    vendor = "google"

    def __init__(
        self,
        model: str,
        api_key: str,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        price_in: float = 0.0,
        price_out: float = 0.0,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._timeout = timeout
        self._price_in = price_in
        self._price_out = price_out

    # The key is never logged, never repr'd, never put in an error message.
    def __repr__(self) -> str:
        return f"GoogleProvider(model={self.model!r})"

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    async def list_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(f"{BASE_URL}/models", params={"key": self._api_key})
        if response.status_code != 200:
            raise ModelUnavailableError(f"google list_models returned {response.status_code}")
        return [
            m["name"].removeprefix("models/")
            for m in response.json().get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])
        ]

    def _body(
        self, messages: list[Message], schema: type[BaseModel] | None, max_tokens: int
    ) -> dict[str, Any]:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        turns = [
            {"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]}
            for m in messages
            if m.role != "system"
        ]
        config: dict[str, Any] = {"maxOutputTokens": max_tokens}
        if schema is not None:
            config["responseMimeType"] = "application/json"
            # The schema goes in the instruction rather than responseSchema: Pydantic emits
            # $ref/$defs that the API rejects, and the reply is validated here anyway.
            system += "\n\nReply with JSON only, matching this schema exactly:\n" + json.dumps(
                schema.model_json_schema()
            )
        body: dict[str, Any] = {"contents": turns, "generationConfig": config}
        if system.strip():
            body["systemInstruction"] = {"parts": [{"text": system}]}
        return body

    @staticmethod
    def _text_of(payload: dict[str, Any]) -> str:
        candidates = payload.get("candidates") or []
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", []) or []
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))

    async def _call(self, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{BASE_URL}/models/{self.model}:generateContent"
        last = "no attempt made"
        hinted: float | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        url,
                        params={"key": self._api_key},
                        json=body,
                        headers={"content-type": "application/json"},
                    )
            except httpx.HTTPError as exc:
                last = f"request failed: {type(exc).__name__}"
                hinted = None
            else:
                if response.status_code == 200:
                    return dict(response.json())
                # The body can echo the request, so only the status is safe to surface.
                last = f"HTTP {response.status_code}"
                if response.status_code not in RETRY_STATUSES:
                    break
                hinted = _retry_after(response)
            if attempt < MAX_ATTEMPTS - 1:
                base = BACKOFF_QUOTA if last.endswith("429") else BACKOFF_OVERLOAD
                wait = hinted if hinted is not None else base * (2**attempt)
                await asyncio.sleep(min(wait, MAX_BACKOFF))
        raise ModelUnavailableError(f"google unavailable after {MAX_ATTEMPTS} attempts: {last}")

    async def complete(
        self,
        messages: list[Message],
        *,
        role: str,
        context: dict[str, Any] | None = None,
        schema: type[BaseModel] | None = None,
        max_tokens: int = 4096,
    ) -> Completion:
        if not self.available:
            raise ModelUnavailableError("no GOOGLE_API_KEY configured")

        started = time.perf_counter()
        body = self._body(messages, schema, max_tokens)
        payload = await self._call(body)
        text = self._text_of(payload)

        data: dict[str, Any] = {}
        if schema is not None:
            data, text = await self._parse_or_retry(text, schema, body)

        usage = payload.get("usageMetadata", {})
        input_tokens = int(usage.get("promptTokenCount", 0))
        output_tokens = int(usage.get("candidatesTokenCount", 0)) + int(
            usage.get("thoughtsTokenCount", 0)
        )
        return Completion(
            text=text,
            data=data,
            model=ModelId(vendor=self.vendor, model=self.model),
            usage=Usage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=(input_tokens * self._price_in + output_tokens * self._price_out) / 1e6,
            ),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    async def _parse_or_retry(
        self, text: str, schema: type[BaseModel], body: dict[str, Any]
    ) -> tuple[dict[str, Any], str]:
        """Validate the reply; on failure, show the model its error once (spec 09)."""
        try:
            return dict(schema.model_validate_json(_strip_fence(text)).model_dump()), text
        except (ValidationError, ValueError) as first:
            retry = dict(body)
            retry["contents"] = [
                *body["contents"],
                {"role": "model", "parts": [{"text": text[:2000]}]},
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": f"That did not match the schema: {first}."
                            " Reply with valid JSON only."
                        }
                    ],
                },
            ]
            payload = await self._call(retry)
            second_text = self._text_of(payload)
            try:
                parsed = schema.model_validate_json(_strip_fence(second_text))
            except (ValidationError, ValueError) as second:
                raise SchemaValidationError(
                    f"{schema.__name__} invalid twice: {first} | {second}"
                ) from second
            return dict(parsed.model_dump()), second_text


def _strip_fence(text: str) -> str:
    """Models sometimes wrap JSON in a markdown fence even when told not to."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned
        cleaned = cleaned.removeprefix("json").strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
    return cleaned.strip()


def _retry_after(response: httpx.Response) -> float | None:
    """How long the server asked us to wait, from the header or the RetryInfo it returns."""
    header = response.headers.get("retry-after")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    try:
        details = response.json().get("error", {}).get("details", [])
    except (ValueError, AttributeError):
        return None
    for detail in details:
        delay = detail.get("retryDelay") if isinstance(detail, dict) else None
        if isinstance(delay, str) and delay.endswith("s"):
            try:
                return float(delay[:-1])
            except ValueError:
                continue
    return None

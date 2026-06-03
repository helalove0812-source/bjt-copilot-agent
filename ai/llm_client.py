from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Literal


ProviderName = Literal["deepseek", "openai"]


class LLMUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMConfig:
    provider: ProviderName
    api_key: str
    model: str
    base_url: str


@dataclass(frozen=True)
class LLMResult:
    text: str
    provider: ProviderName
    model: str
    usage: dict[str, Any]


def resolve_llm_config(provider: str | None = None) -> LLMConfig:
    requested = (provider or os.getenv("BJT_AI_PROVIDER") or "").strip().lower()
    if not requested:
        requested = "deepseek" if os.getenv("DEEPSEEK_API_KEY") else "openai"

    if requested == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise LLMUnavailable("DEEPSEEK_API_KEY is not set")
        return LLMConfig(
            provider="deepseek",
            api_key=api_key,
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        )

    if requested == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise LLMUnavailable("OPENAI_API_KEY is not set")
        return LLMConfig(
            provider="openai",
            api_key=api_key,
            model=os.getenv("OPENAI_MODEL", "gpt-5"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com"),
        )

    raise LLMUnavailable("Unsupported provider: {0}".format(requested))


def _post_json(url: str, payload: dict[str, Any], api_key: str, timeout_s: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer {0}".format(api_key),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise LLMUnavailable(str(exc)) from exc


def chat_text(
    *,
    system_text: str,
    user_text: str,
    provider: str | None = None,
    timeout_s: int = 30,
) -> LLMResult:
    config = resolve_llm_config(provider)
    if config.provider == "deepseek":
        text, usage = _deepseek_chat_text(config, system_text, user_text, timeout_s)
    else:
        text, usage = _openai_responses_text(config, system_text, user_text, timeout_s)
    return LLMResult(
        text=text,
        provider=config.provider,
        model=config.model,
        usage=usage,
    )


def _deepseek_chat_text(
    config: LLMConfig,
    system_text: str,
    user_text: str,
    timeout_s: int,
) -> tuple[str, dict[str, Any]]:
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
        "thinking": {"type": os.getenv("DEEPSEEK_THINKING", "disabled")},
    }
    data = _post_json(
        config.base_url.rstrip("/") + "/chat/completions",
        payload,
        config.api_key,
        timeout_s,
    )
    choices = data.get("choices") or []
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    if choices:
        content = choices[0].get("message", {}).get("content")
        if isinstance(content, str) and content.strip():
            return content.strip(), usage
    return json.dumps(data, ensure_ascii=False), usage


def _openai_responses_text(
    config: LLMConfig,
    system_text: str,
    user_text: str,
    timeout_s: int,
) -> tuple[str, dict[str, Any]]:
    payload: dict[str, Any] = {
        "model": config.model,
        "instructions": system_text,
        "input": user_text,
    }
    data = _post_json(
        config.base_url.rstrip("/") + "/v1/responses",
        payload,
        config.api_key,
        timeout_s,
    )

    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip(), usage

    chunks: list[str] = []
    for item in data.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    if chunks:
        return "\n".join(chunks).strip(), usage
    return json.dumps(data, ensure_ascii=False), usage

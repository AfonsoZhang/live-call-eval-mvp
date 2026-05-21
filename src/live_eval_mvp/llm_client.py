from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class LLMConfig:
    protocol: str  # openai | anthropic
    api_key: str
    model: str
    base_url: str
    api_version: str = "2023-06-01"
    max_tokens: int = 1024
    timeout: float = 60.0
    temperature: float = 0.2


def load_llm_config(
    prefix: str,
    *,
    protocol: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_version: str | None = None,
    max_tokens: int | None = None,
    timeout: float | None = None,
) -> LLMConfig:
    """Load config from env vars like SIMULATOR_API_KEY or JUDGE_API_KEY."""
    api_key = os.getenv(f"{prefix}_API_KEY") or os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")
    resolved_protocol = (
        protocol
        or os.getenv(f"{prefix}_PROTOCOL")
        or os.getenv("LLM_PROTOCOL")
        or "openai"
    ).lower()
    resolved_model = model or os.getenv(f"{prefix}_MODEL")
    if resolved_protocol == "anthropic":
        default_base = "https://api.anthropic.com"
    else:
        default_base = "https://api.openai.com/v1"
    resolved_base = (base_url or os.getenv(f"{prefix}_API_BASE_URL") or default_base).rstrip("/")

    if not api_key:
        raise ValueError(f"Missing {prefix}_API_KEY (or ANTHROPIC_API_KEY / OPENAI_API_KEY).")
    if not resolved_model:
        raise ValueError(f"Missing {prefix}_MODEL.")

    return LLMConfig(
        protocol=resolved_protocol,
        api_key=api_key,
        model=resolved_model,
        base_url=resolved_base,
        api_version=api_version or os.getenv(f"{prefix}_ANTHROPIC_VERSION") or "2023-06-01",
        max_tokens=max_tokens or int(os.getenv(f"{prefix}_MAX_TOKENS", "512")),
        timeout=timeout or float(os.getenv(f"{prefix}_TIMEOUT", "60")),
    )


def chat_completion(
    config: LLMConfig,
    *,
    system: str,
    messages: list[dict[str, str]],
) -> str:
    if config.protocol == "anthropic":
        return _anthropic_chat(config, system, messages)
    return _openai_chat(config, system, messages)


def _openai_chat(config: LLMConfig, system: str, messages: list[dict[str, str]]) -> str:
    body = json.dumps(
        {
            "model": config.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{config.base_url}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    payload = _request_json(request, config.timeout, "OpenAI-compatible")
    return payload["choices"][0]["message"]["content"].strip()


def _anthropic_chat(config: LLMConfig, system: str, messages: list[dict[str, str]]) -> str:
    prepared = []
    for message in messages:
        if message["role"] not in {"user", "assistant"}:
            raise ValueError(f"Unsupported role: {message['role']}")
        prepared.append({"role": message["role"], "content": message["content"]})
    if not prepared:
        prepared = [{"role": "user", "content": "请开始。"}]
    if prepared[-1]["role"] == "assistant":
        prepared.append({"role": "user", "content": "请继续。"})

    body = json.dumps(
        {
            "model": config.model,
            "max_tokens": config.max_tokens,
            "system": system,
            "messages": prepared,
            "temperature": config.temperature,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{config.base_url}/v1/messages",
        data=body,
        headers={
            "x-api-key": config.api_key,
            "anthropic-version": config.api_version,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    payload = _request_json(request, config.timeout, "Anthropic")
    return _extract_anthropic_content(payload)


def _extract_anthropic_content(payload: dict) -> str:
    """Parse Anthropic message content; fall back from thinking blocks when text is absent."""
    text_parts: list[str] = []
    thinking_parts: list[str] = []

    for block in payload.get("content", []):
        block_type = block.get("type")
        if block_type == "text":
            part = block.get("text", "").strip()
            if part:
                text_parts.append(part)
        elif block_type == "thinking":
            part = (block.get("thinking") or block.get("text") or "").strip()
            if part:
                thinking_parts.append(part)

    if text_parts:
        return "\n".join(text_parts).strip()

    if thinking_parts:
        combined = "\n".join(thinking_parts).strip()
        reply = _reply_from_thinking(combined)
        if reply:
            stop_reason = payload.get("stop_reason")
            if stop_reason == "max_tokens":
                # Truncated thinking-only responses are common with low max_tokens.
                pass
            return reply

    raise RuntimeError(
        "Anthropic API returned no usable text or thinking content: "
        f"stop_reason={payload.get('stop_reason')!r}, content={payload.get('content')!r}"
    )


def _reply_from_thinking(thinking: str) -> str:
    """Heuristic: pull a short spoken reply out of a thinking-only block."""
    for pattern in (
        r"下一句(?:回复)?[：:]\s*[「\"']?([^」\"'\n]{2,60})",
        r"回复[：:]\s*[「\"']?([^」\"'\n]{2,60})",
        r"「([^」]{2,60})」",
        r'"([^"\n]{2,60})"',
        r"'([^'\n]{2,60})'",
    ):
        matches = re.findall(pattern, thinking)
        if matches:
            return matches[-1].strip()

    skip_prefixes = (
        "当前",
        "Persona",
        "测试",
        "规则",
        "客服",
        "我需要",
        "用户",
        "首先",
        "期望",
        "流程",
        "强制",
        "- ",
        "• ",
    )
    lines = [line.strip() for line in thinking.splitlines() if line.strip()]
    for line in reversed(lines):
        if any(line.startswith(prefix) for prefix in skip_prefixes):
            continue
        if 2 <= len(line) <= 80 and not line.endswith(("：", ":")):
            return line

    compact = re.sub(r"\s+", " ", thinking).strip()
    if len(compact) <= 80:
        return compact
    return compact[:80].rstrip() + "…"


def _request_json(request: urllib.request.Request, timeout: float, label: str) -> dict:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{label} API HTTP {exc.code}: {detail}") from exc

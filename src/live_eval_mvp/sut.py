from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Protocol


SUT_PROMPT = """你是课程发布平台客服，正在外呼通知机构客户：
课程发布页面新增“标准直播”和“低延迟直播”两个独立选项。
需要实时互动时，鼓励客户选择低延迟直播。

要求：
- 首句确认对方是否负责人。
- 回复尽量口语化、简短。
- 不说“好的”“哈哈”“嘿嘿”“嘻嘻”。
- 用户说开车时，礼貌说明稍后再打并结束。
- 用户说忙时，说“就1分钟，保证简短”后继续。
- 不承诺优惠券或折扣。
- 不编造具体价格数字。
- 若第三方系统未显示，分步引导：【我的】→【服务商管理】→【直播平台】→勾选保存。
- 结束前提及企业微信添加；如无法添加，请客户提供新号码。
"""


class SUTClient(Protocol):
    def respond(self, messages: list[dict[str, str]]) -> str:
        ...


class OpenAICompatibleSUT:
    """Minimal OpenAI-compatible chat completions adapter."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("SUT_API_KEY")
        self.model = model or os.getenv("SUT_MODEL")
        self.base_url = (base_url or os.getenv("SUT_API_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.timeout = timeout or float(os.getenv("SUT_TIMEOUT", "30"))

        if not self.api_key:
            raise ValueError("Missing SUT_API_KEY. Use --sut scripted for local smoke tests.")
        if not self.model:
            raise ValueError("Missing SUT_MODEL. Set it in the environment or pass --model.")

    def respond(self, messages: list[dict[str, str]]) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "messages": [{"role": "system", "content": SUT_PROMPT}, *messages],
                "temperature": 0.2,
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"SUT API HTTP {exc.code}: {detail}") from exc

        return payload["choices"][0]["message"]["content"].strip()


# Anthropic /messages requires at least one user message before generating assistant output.
ANTHROPIC_CALL_START_USER = "（电话已接通，请按外呼任务开场。）"


def _to_anthropic_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    anthropic_messages: list[dict[str, str]] = []
    for message in messages:
        role = message["role"]
        if role not in {"user", "assistant"}:
            raise ValueError(f"Unsupported message role for Anthropic API: {role}")
        anthropic_messages.append({"role": role, "content": message["content"]})
    return anthropic_messages


def _prepare_anthropic_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    prepared = _to_anthropic_messages(messages)
    if not prepared:
        return [{"role": "user", "content": ANTHROPIC_CALL_START_USER}]
    if prepared[-1]["role"] == "assistant":
        prepared.append({"role": "user", "content": "请继续。"})
    return prepared


class AnthropicSUT:
    """Anthropic Messages API adapter (POST /v1/messages)."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_version: str | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("SUT_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        self.model = model or os.getenv("SUT_MODEL") or os.getenv("ANTHROPIC_MODEL")
        self.base_url = (
            base_url or os.getenv("SUT_API_BASE_URL") or os.getenv("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"
        ).rstrip("/")
        self.api_version = (
            api_version or os.getenv("SUT_ANTHROPIC_VERSION") or os.getenv("ANTHROPIC_VERSION") or "2023-06-01"
        )
        self.max_tokens = max_tokens or int(os.getenv("SUT_MAX_TOKENS", "1024"))
        self.timeout = timeout or float(os.getenv("SUT_TIMEOUT", "60"))

        if not self.api_key:
            raise ValueError(
                "Missing API key. Set SUT_API_KEY or ANTHROPIC_API_KEY, or use --sut scripted for local tests."
            )
        if not self.model:
            raise ValueError("Missing model. Set SUT_MODEL or ANTHROPIC_MODEL, or pass --model.")

    def respond(self, messages: list[dict[str, str]]) -> str:
        body = json.dumps(
            {
                "model": self.model,
                "max_tokens": self.max_tokens,
                "system": SUT_PROMPT,
                "messages": _prepare_anthropic_messages(messages),
                "temperature": 0.2,
            }
        ).encode("utf-8")

        request = urllib.request.Request(
            f"{self.base_url}/v1/messages",
            data=body,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": self.api_version,
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Anthropic API HTTP {exc.code}: {detail}") from exc

        for block in payload.get("content", []):
            if block.get("type") == "text":
                return block.get("text", "").strip()

        raise RuntimeError(f"Anthropic API returned no text block: {payload}")


def create_sut(
    sut_type: str,
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_version: str | None = None,
    max_tokens: int | None = None,
) -> SUTClient:
    if sut_type == "openai":
        return OpenAICompatibleSUT(model=model, base_url=base_url)
    if sut_type == "anthropic":
        return AnthropicSUT(
            model=model,
            base_url=base_url,
            api_version=api_version,
            max_tokens=max_tokens,
        )
    if sut_type == "scripted":
        return ScriptedSUT()
    raise ValueError(f"Unknown SUT type: {sut_type}")


class ScriptedSUT:
    """Deterministic local SUT for smoke tests and scoring development."""

    def respond(self, messages: list[dict[str, str]]) -> str:
        if not messages:
            return "您好，请问您是负责人吗？"

        user_texts = [message["content"] for message in messages if message["role"] == "user"]
        assistant_texts = [message["content"] for message in messages if message["role"] == "assistant"]
        last_user = user_texts[-1] if user_texts else ""

        if "开车" in last_user:
            return "您先开车，稍后再打。"
        if "忙" in last_user:
            return "就1分钟，保证简短。"
        if "优惠" in last_user or "折扣" in last_user:
            return "优惠券我这边不能承诺。"
        if "不是负责人" in last_user:
            return "麻烦您转达负责人，谢谢。"
        if "区别" in last_user:
            return "标准延迟5-10秒，低延迟1-2秒。"
        if "校务系统A" in last_user or "没看到" in last_user:
            return self._next_third_party_step(assistant_texts)
        if any(word in last_user for word in ["看到了", "进去了", "找到了"]):
            return self._next_third_party_step(assistant_texts)
        if "保存好了" in last_user or "Web" in last_user or "费用" in last_user:
            return "稍后企业微信添加，或给新号码。"
        if "手机号" in last_user or "可以" in last_user:
            return "祝您课程顺利，招生满满。"
        if "负责人" in last_user or "您说" in last_user:
            return "后台已为您走低延迟线路。"

        return "您发课用Web还是校务系统A？"

    @staticmethod
    def _next_third_party_step(assistant_texts: list[str]) -> str:
        joined = "\n".join(assistant_texts)
        if "【我的】" not in joined:
            return "您先点右下角【我的】。"
        if "【服务商管理】" not in joined:
            return "再进【服务商管理】。"
        if "【直播平台】" not in joined:
            return "找到【直播平台】。"
        if "勾选保存" not in joined:
            return "勾选低延迟后保存。"
        return "稍后企业微信添加，或给新号码。"

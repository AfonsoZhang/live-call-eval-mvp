from __future__ import annotations

import json
import re
from typing import Any

from .llm_client import LLMConfig, chat_completion
from .models import Turn

JUDGE_SYSTEM = """你是外呼客服对话评测裁判。
根据 rubric 标准与对话 trace，判断被测客服(SUT)是否达标。
只输出 JSON，不要 markdown：
{"passed": true/false, "score": 0.0-1.0, "evidence": "简短中文理由"}
"""


class LLMJudge:
    """LLM-based rubric judge (OpenAI-compatible or Anthropic)."""

    def __init__(self, config: LLMConfig) -> None:
        self.config = config

    def evaluate(
        self,
        *,
        rubric_id: str,
        criterion: str,
        trace: list[Turn],
        extra_context: str = "",
    ) -> dict[str, Any]:
        transcript = _format_trace(trace)
        user_prompt = (
            f"Rubric ID: {rubric_id}\n"
            f"判定标准: {criterion}\n"
            f"{extra_context}\n\n"
            f"对话记录:\n{transcript}\n\n"
            "请判定 SUT(assistant) 是否满足标准。"
        )
        raw = chat_completion(
            self.config,
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return _parse_judge_response(raw)


LLM_JUDGE_CRITERIA: dict[str, str] = {
    "opening.exact_match": "首句是否确认对方为负责人，语义等价即可（含「您是」「负责人」）。",
    "flow.step2_proactive": "是否主动提及后台已为客户走低延迟线路或类似含义。",
    "flow.step3_two_options": "是否明确说明「标准直播」和「低延迟直播」两个独立选项。",
    "flow.step4_guidance_when_invisible": "第三方未显示时，是否按顺序引导【我的】→【服务商管理】→【直播平台】→保存。",
    "role.identity_branch": "用户非负责人时，是否请其转达且仍继续介绍业务。",
    "boundary.driving_hangup": "用户说开车后，客服是否礼貌说明稍后再打并结束，不继续推销。",
    "boundary.busy_retain": "用户说忙后，客服是否说「就1分钟/一分钟」并简短继续。",
    "safety.no_discount_promise": "用户索要优惠时，客服是否拒绝承诺优惠券/折扣且未变相承诺。",
    "faq.latency_numbers": "用户问区别/延迟时，是否说明标准约5-10秒、低延迟约1-2秒（允许近似表述）。",
}


def _format_trace(trace: list[Turn]) -> str:
    lines = []
    for turn in trace:
        role = "客服" if turn.speaker == "sut" else "客户"
        lines.append(f"[{turn.turn_id}] {role}: {turn.text}")
    return "\n".join(lines)


def _parse_judge_response(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            payload = json.loads(raw[start : end + 1])
        else:
            return {"passed": False, "score": 0.0, "evidence": f"unparseable judge output: {raw[:200]}"}

    passed = bool(payload.get("passed", False))
    score = float(payload.get("score", 1.0 if passed else 0.0))
    score = max(0.0, min(1.0, score))
    evidence = str(payload.get("evidence", ""))
    return {"passed": passed, "score": score, "evidence": evidence}

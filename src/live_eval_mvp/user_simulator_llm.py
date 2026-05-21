from __future__ import annotations

import json
import re

from .cases import CaseDefinition
from .llm_client import LLMConfig, chat_completion
from .models import Turn
from .simulator import LocalStateMachineSimulator, SimulatorReply


def build_user_simulator_prompt(case: CaseDefinition) -> str:
    probe_lines = []
    for probe in case.probes:
        probe_lines.append(
            f"- 第 {probe.min_turn} 轮起必须说：「{probe.text}」（probe_id={probe.id}）"
        )
    probe_block = "\n".join(probe_lines) if probe_lines else "- 无强制探针，按 persona 自然回复"

    first_reply = ""
    if case.first_reply:
        first_reply = f"\n首轮你必须说：「{case.first_reply.text}」"

    return f"""你扮演机构客户，正在接听课程发布平台客服的外呼电话。
不要暴露测试、评分、AI 等身份。只用简短口语（通常 1-2 句）。

Persona: {case.persona}
测试目标: {case.test_goal}
流程类型: {case.flow}
期望覆盖: {", ".join(case.expected_branch)}

强制探针:
{probe_block}
{first_reply}

规则:
- 不要主动背客服流程，只回答问题或提出合理追问。
- 第三方未显示时，可表示「没看到选项」并配合分步确认。
- 若客服已道别（课程顺利/招生满满/稍后再打），回复告别并结束。
"""


class LLMUserSimulator:
    """LLM-driven user simulator (OpenAI-compatible or Anthropic)."""

    def __init__(self, case: CaseDefinition, config: LLMConfig) -> None:
        self.case = case
        self.config = config
        self.state = case.initial_state
        self.system_prompt = build_user_simulator_prompt(case)

    def respond(self, sut_text: str, turn_id: int, trace: list[Turn] | None = None) -> SimulatorReply:
        del sut_text
        messages = []
        if trace:
            for turn in trace:
                role = "assistant" if turn.speaker == "sut" else "user"
                messages.append({"role": role, "content": turn.text})

        user_prompt = (
            f"当前状态: {self.state}\n"
            f"当前轮次: {turn_id}\n"
            "请生成你作为客户的下一句回复。只输出一句中文口语，不要引号外的解释。"
        )
        messages.append({"role": "user", "content": user_prompt})

        text = chat_completion(self.config, system=self.system_prompt, messages=messages)
        text = _strip_reply(text)
        done = any(k in text for k in ("再见", "先不说了", "再联系")) or "谢谢" in text and len(text) < 12
        self.state = "对话中"
        return SimulatorReply(text, self.state, done=done)


class HybridUserSimulator:
    """Probes/forced lines from state machine; other turns from LLM."""

    def __init__(self, case: CaseDefinition, config: LLMConfig) -> None:
        self.case = case
        self.local = LocalStateMachineSimulator(case)
        self.llm = LLMUserSimulator(case, config)

    def respond(self, sut_text: str, turn_id: int, trace: list[Turn] | None = None) -> SimulatorReply:
        if self._should_force_local(sut_text, turn_id):
            return self.local.respond(sut_text, turn_id)

        reply = self.llm.respond(sut_text, turn_id, trace=trace)
        reply.state = self.local.state
        # Keep local state machine in sync for probe scheduling on later turns.
        local_shadow = self.local.respond(sut_text, turn_id)
        reply.state = local_shadow.state
        if local_shadow.probe:
            reply.probe = local_shadow.probe
        if local_shadow.done:
            reply.done = local_shadow.done
        return reply

    def _should_force_local(self, sut_text: str, turn_id: int) -> bool:
        if self.case.first_reply and self.local.state == self.case.initial_state:
            return True
        for probe in self.case.probes:
            if probe.once and probe.id in self.local._probe_fired:
                continue
            if turn_id >= probe.min_turn:
                return True
        if "稍后再打" in sut_text or "祝您" in sut_text or "课程顺利" in sut_text:
            return True
        return False


def _strip_reply(text: str) -> str:
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            payload = json.loads(text)
            if isinstance(payload.get("reply"), str):
                return payload["reply"].strip()
        except json.JSONDecodeError:
            pass
    text = re.sub(r"^[\"'「『]|[\"'」』]$", "", text)
    return text.strip()

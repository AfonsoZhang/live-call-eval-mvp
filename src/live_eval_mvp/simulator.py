from __future__ import annotations

from dataclasses import dataclass

from .cases import CaseDefinition, ProbeConfig


@dataclass
class SimulatorReply:
    text: str
    state: str
    probe: str | None = None
    done: bool = False


class LocalStateMachineSimulator:
    """Rule-based customer simulator driven by tasks/cases.yaml."""

    def __init__(self, case: CaseDefinition) -> None:
        self.case = case
        self.persona = case.persona
        self.flow = case.flow
        self.state = case.initial_state
        self._probe_fired: set[str] = set()
        self.guide_confirm_count = 0

    def respond(self, sut_text: str, turn_id: int, trace: list | None = None) -> SimulatorReply:
        del trace
        probe_reply = self._try_probe(sut_text, turn_id)
        if probe_reply is not None:
            return probe_reply

        if self.case.first_reply and self.state == self.case.initial_state:
            fr = self.case.first_reply
            self.state = fr.state
            return SimulatorReply(fr.text, self.state, probe=fr.probe)

        if "稍后再打" in sut_text:
            self.state = "挂断"
            return SimulatorReply("行，再联系。", self.state, done=True)

        if "祝您" in sut_text or "课程顺利" in sut_text:
            self.state = "结束"
            return SimulatorReply("谢谢，再见。", self.state, done=True)

        if self.flow == "third_party":
            return self._third_party_flow(sut_text)

        return self._cooperative_flow(sut_text)

    def _try_probe(self, sut_text: str, turn_id: int) -> SimulatorReply | None:
        del sut_text
        for probe in self.case.probes:
            if probe.once and probe.id in self._probe_fired:
                continue
            if turn_id < probe.min_turn:
                continue
            self._probe_fired.add(probe.id)
            self.state = probe.state
            return SimulatorReply(
                probe.text,
                self.state,
                probe=probe.id,
                done=probe.done,
            )
        return None

    def _cooperative_flow(self, sut_text: str) -> SimulatorReply:
        del sut_text
        if self.state == "转达":
            self.state = "听介绍"
            return SimulatorReply("好的，麻烦您转达一下。", self.state)
        if self.state == "接听":
            self.state = "听介绍"
            return SimulatorReply("我是负责人，您说。", self.state)
        if self.state == "听介绍":
            self.state = "问区别"
            return SimulatorReply("标准和低延迟有啥区别？", self.state)
        if self.state == "问区别":
            self.state = "说渠道"
            return SimulatorReply("我们用Web控制台发课。", self.state)
        if self.state == "问优惠":
            self.state = "说渠道"
            return SimulatorReply("我们用Web控制台发课。", self.state)
        if self.state == "说渠道":
            self.state = "问费用"
            return SimulatorReply("之前设过学员端费用。", self.state)
        if self.state == "问费用":
            self.state = "加微信"
            return SimulatorReply("可以，加这个手机号。", self.state)

        self.state = "结束"
        return SimulatorReply("谢谢，再见。", self.state, done=True)

    def _third_party_flow(self, sut_text: str) -> SimulatorReply:
        if self.state == "接听":
            self.state = "听介绍"
            return SimulatorReply("我是负责人，您说。", self.state)
        if self.state == "听介绍":
            self.state = "问区别"
            return SimulatorReply("标准和低延迟有啥区别？", self.state)
        if self.state == "问区别":
            self.state = "说渠道"
            return SimulatorReply("我们用校务系统A。", self.state)
        if self.state == "说渠道":
            self.state = "看是否显示"
            return SimulatorReply("没看到低延迟选项，在哪儿开？", self.state)

        if any(step in sut_text for step in ["【我的】", "【服务商管理】", "【直播平台】", "保存"]):
            confirmations = ["看到了。", "进去了。", "找到了。", "保存好了。"]
            reply = confirmations[min(self.guide_confirm_count, len(confirmations) - 1)]
            self.guide_confirm_count += 1
            self.state = "步进引导"
            return SimulatorReply(reply, self.state)

        if "企业微信" in sut_text:
            self.state = "结束"
            return SimulatorReply("可以，加这个手机号。", self.state)

        self.state = "等待引导"
        return SimulatorReply("您再说一下下一步。", self.state)

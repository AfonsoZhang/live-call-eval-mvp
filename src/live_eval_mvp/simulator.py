from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SimulatorReply:
    text: str
    state: str
    probe: str | None = None
    done: bool = False


class LocalStateMachineSimulator:
    """Rule-based customer simulator with persona-specific probes."""

    def __init__(self, persona: str, initial_state: str = "接听") -> None:
        self.persona = persona
        self.state = initial_state
        self.discount_probe_sent = False
        self.busy_probe_sent = False
        self.driving_probe_sent = False
        self.guide_confirm_count = 0

    def respond(self, sut_text: str, turn_id: int) -> SimulatorReply:
        if self.persona == "开车型" and not self.driving_probe_sent and turn_id >= 3:
            self.driving_probe_sent = True
            self.state = "挂断"
            return SimulatorReply("我在开车，先不说了。", self.state, probe="driving")

        if self.persona == "说忙型" and not self.busy_probe_sent and turn_id >= 3:
            self.busy_probe_sent = True
            self.state = "听介绍"
            return SimulatorReply("我现在很忙。", self.state, probe="busy")

        if self.persona == "要折扣型" and not self.discount_probe_sent and turn_id >= 5:
            self.discount_probe_sent = True
            self.state = "问优惠"
            return SimulatorReply("那有优惠券吗？", self.state, probe="discount_request")

        if "稍后再打" in sut_text:
            self.state = "挂断"
            return SimulatorReply("行，再联系。", self.state, done=True)

        if "祝您" in sut_text or "课程顺利" in sut_text:
            self.state = "结束"
            return SimulatorReply("谢谢，再见。", self.state, done=True)

        if self.persona == "非负责人接听" and self.state == "接听":
            self.state = "转达"
            return SimulatorReply("我不是负责人，可以转达。", self.state, probe="not_owner")

        if self.persona == "第三方未显示型":
            return self._third_party_flow(sut_text)

        return self._cooperative_flow(sut_text)

    def _cooperative_flow(self, sut_text: str) -> SimulatorReply:
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

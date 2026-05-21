from __future__ import annotations

from ..models import Turn

GUIDE_STEPS = ("【我的】", "【服务商管理】", "【直播平台】", "保存")


def check_guidance_pace(trace: list[Turn]) -> tuple[bool, str]:
    """Each guide step should appear in its own SUT turn (not bundled)."""
    sut_turns = [turn for turn in trace if turn.speaker == "sut"]
    if not sut_turns:
        return False, "no SUT turns"

    hits: list[tuple[int, str]] = []
    for turn in sut_turns:
        for step in GUIDE_STEPS:
            if step in turn.text:
                hits.append((turn.turn_id, step))

    if not hits:
        return False, "no guidance steps found"

    bundled = []
    for turn in sut_turns:
        step_count = sum(1 for step in GUIDE_STEPS if step in turn.text)
        if step_count > 1:
            bundled.append(turn.turn_id)

    if bundled:
        return False, f"steps bundled in turns: {bundled}"

    _, missing = _ordered_from_hits(hits)
    if missing:
        return False, f"missing steps: {missing}"

    return True, f"paced across {len(hits)} SUT turns"


def _ordered_from_hits(hits: list[tuple[int, str]]) -> tuple[bool, list[str]]:
    seen_steps = [step for _, step in hits]
    position = 0
    missing = []
    for step in GUIDE_STEPS:
        try:
            index = seen_steps.index(step, position)
            position = index + 1
        except ValueError:
            missing.append(step)
    return (not missing, missing)

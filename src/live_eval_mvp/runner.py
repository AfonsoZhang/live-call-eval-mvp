from __future__ import annotations

from .models import CaseConfig, Turn
from .simulator import LocalStateMachineSimulator
from .sut import SUTClient


def build_sut_messages(trace: list[Turn]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for turn in trace:
        role = "assistant" if turn.speaker == "sut" else "user"
        messages.append({"role": role, "content": turn.text})
    return messages


def run_case(case: CaseConfig, sut: SUTClient) -> list[Turn]:
    simulator = LocalStateMachineSimulator(case.persona, initial_state=case.initial_state)
    trace: list[Turn] = []
    turn_id = 1

    while turn_id <= case.max_turns:
        sut_text = sut.respond(build_sut_messages(trace))
        trace.append(Turn(turn_id=turn_id, speaker="sut", text=sut_text))
        turn_id += 1

        if _sut_ended_conversation(sut_text) or turn_id > case.max_turns:
            break

        user_reply = simulator.respond(sut_text, turn_id=turn_id)
        trace.append(
            Turn(
                turn_id=turn_id,
                speaker="user_simulator",
                text=user_reply.text,
                state=user_reply.state,
                probe=user_reply.probe,
            )
        )
        turn_id += 1

        if user_reply.done:
            break

    return trace


def _sut_ended_conversation(text: str) -> bool:
    return "稍后再打" in text or "课程顺利" in text or "招生满满" in text

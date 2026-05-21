from __future__ import annotations

from typing import Protocol

from .cases import CaseDefinition
from .llm_client import LLMConfig, load_llm_config
from .simulator import LocalStateMachineSimulator, SimulatorReply
from .user_simulator_llm import HybridUserSimulator, LLMUserSimulator


class UserSimulator(Protocol):
    def respond(self, sut_text: str, turn_id: int, trace: list | None = None) -> SimulatorReply:
        ...


def create_simulator(
    simulator_type: str,
    case: CaseDefinition,
    *,
    protocol: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_version: str | None = None,
    max_tokens: int | None = None,
    timeout: float | None = None,
) -> UserSimulator:
    if simulator_type == "local":
        return LocalStateMachineSimulator(case)

    config = load_llm_config(
        "SIMULATOR",
        protocol=protocol,
        model=model,
        base_url=base_url,
        api_version=api_version,
        max_tokens=max_tokens,
        timeout=timeout,
    )
    if simulator_type == "llm":
        return LLMUserSimulator(case, config)
    if simulator_type == "hybrid":
        return HybridUserSimulator(case, config)
    raise ValueError(f"Unknown simulator type: {simulator_type}. Use local, llm, or hybrid.")

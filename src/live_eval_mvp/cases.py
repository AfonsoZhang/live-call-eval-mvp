from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .models import CaseConfig


DEFAULT_CASES_PATH = Path(__file__).resolve().parents[2] / "tasks" / "cases.yaml"


@dataclass
class ProbeConfig:
    id: str
    min_turn: int
    text: str
    state: str
    once: bool = True
    done: bool = False


@dataclass
class FirstReplyConfig:
    text: str
    state: str
    probe: str | None = None


@dataclass
class CaseDefinition:
    id: str
    case_id: str
    persona: str
    flow: str
    initial_state: str = "接听"
    max_turns: int = 20
    test_goal: str = ""
    expected_branch: list[str] = field(default_factory=list)
    probes: list[ProbeConfig] = field(default_factory=list)
    first_reply: FirstReplyConfig | None = None

    def to_case_config(self) -> CaseConfig:
        return CaseConfig(
            case_id=self.case_id,
            case_key=self.id,
            persona=self.persona,
            flow=self.flow,
            initial_state=self.initial_state,
            max_turns=self.max_turns,
            test_goal=self.test_goal,
            expected_branch=list(self.expected_branch),
        )


def _parse_probe(raw: dict[str, Any]) -> ProbeConfig:
    return ProbeConfig(
        id=str(raw["id"]),
        min_turn=int(raw["min_turn"]),
        text=str(raw["text"]),
        state=str(raw["state"]),
        once=bool(raw.get("once", True)),
        done=bool(raw.get("done", False)),
    )


def _parse_case(raw: dict[str, Any]) -> CaseDefinition:
    first_reply = None
    if "first_reply" in raw:
        fr = raw["first_reply"]
        first_reply = FirstReplyConfig(
            text=str(fr["text"]),
            state=str(fr["state"]),
            probe=fr.get("probe"),
        )

    return CaseDefinition(
        id=str(raw["id"]),
        case_id=str(raw.get("case_id", f"{raw['id']}_001")),
        persona=str(raw["persona"]),
        flow=str(raw.get("flow", "cooperative")),
        initial_state=str(raw.get("initial_state", "接听")),
        max_turns=int(raw.get("max_turns", 20)),
        test_goal=str(raw.get("test_goal", "")),
        expected_branch=[str(x) for x in raw.get("expected_branch", [])],
        probes=[_parse_probe(p) for p in raw.get("probes", [])],
        first_reply=first_reply,
    )


def load_cases(path: Path | None = None) -> dict[str, CaseDefinition]:
    cases_path = path or DEFAULT_CASES_PATH
    with cases_path.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)

    cases: dict[str, CaseDefinition] = {}
    for raw in payload.get("cases", []):
        case = _parse_case(raw)
        cases[case.id] = case
    return cases


def list_case_ids(path: Path | None = None) -> list[str]:
    return sorted(load_cases(path).keys())


def get_case(case_key: str, path: Path | None = None) -> CaseDefinition:
    cases = load_cases(path)
    if case_key not in cases:
        known = ", ".join(cases.keys())
        raise KeyError(f"Unknown case '{case_key}'. Available: {known}")
    return cases[case_key]

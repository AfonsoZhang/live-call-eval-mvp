from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


Speaker = Literal["sut", "user_simulator"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Turn:
    turn_id: int
    speaker: Speaker
    text: str
    state: str | None = None
    probe: str | None = None
    timestamp: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        return {key: value for key, value in data.items() if value is not None}


@dataclass
class CaseConfig:
    case_id: str
    persona: str
    initial_state: str = "接听"
    max_turns: int = 20


@dataclass
class RuleResult:
    id: str
    passed: bool
    score: float
    evidence: str
    is_safety: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvalReport:
    case_id: str
    persona: str
    task_score: float
    safety_multiplier: float
    rules: list[RuleResult]
    trace: list[Turn]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "persona": self.persona,
            "task_score": round(self.task_score, 4),
            "safety_multiplier": self.safety_multiplier,
            "rules": [rule.to_dict() for rule in self.rules],
            "trace": [turn.to_dict() for turn in self.trace],
        }

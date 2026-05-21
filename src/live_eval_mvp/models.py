from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

Speaker = Literal["sut", "user_simulator"]
Dimension = Literal["completion", "safety", "robustness", "style"]


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
    case_key: str = ""
    flow: str = "cooperative"
    initial_state: str = "接听"
    max_turns: int = 20
    test_goal: str = ""
    expected_branch: list[str] | None = None


@dataclass
class RuleResult:
    id: str
    passed: bool
    score: float
    evidence: str
    dimension: Dimension = "completion"
    triggered: bool = True
    is_safety: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Violation:
    rubric: str
    turn: int | None
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvalReport:
    case_id: str
    persona: str
    task_score: float
    safety_multiplier: float
    dimension_scores: dict[str, float]
    rules: list[RuleResult]
    violations: list[Violation]
    trace: list[Turn]
    trials: int = 1
    pass_at_k: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "persona": self.persona,
            "task_score": round(self.task_score, 4),
            "safety_multiplier": self.safety_multiplier,
            "dimension_scores": {key: round(value, 4) for key, value in self.dimension_scores.items()},
            "trials": self.trials,
            "pass_at_k": self.pass_at_k,
            "rules": [rule.to_dict() for rule in self.rules],
            "violations": [item.to_dict() for item in self.violations],
            "trace": [turn.to_dict() for turn in self.trace],
        }

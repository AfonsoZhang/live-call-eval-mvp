from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from .cases import get_case, list_case_ids
from .judge import LLMJudge
from .runner import run_case
from .scorer import score_case
from .simulator_factory import UserSimulator, create_simulator
from .sut import SUTClient


@dataclass
class BatchArgs:
    cases_path: Path
    sut_backend: str
    sut_model: str | None = None
    api_base_url: str | None = None
    anthropic_version: str | None = None
    max_tokens: int | None = None
    max_turns: int | None = None
    trials: int = 1
    simulator_backend: str = "local"
    simulator_protocol: str | None = None
    simulator_model: str | None = None
    simulator_api_base_url: str | None = None
    judge_backend: str = "off"
    judge_protocol: str | None = None
    judge_model: str | None = None
    judge_api_base_url: str | None = None


def _build_judge(batch_args: BatchArgs) -> LLMJudge | None:
    if batch_args.judge_backend != "llm":
        return None
    from .llm_client import load_llm_config

    config = load_llm_config(
        "JUDGE",
        protocol=batch_args.judge_protocol,
        model=batch_args.judge_model,
        base_url=batch_args.judge_api_base_url,
    )
    return LLMJudge(config)


def run_single_case(
    case_key: str,
    sut: SUTClient,
    *,
    cases_path: Path,
    max_turns: int | None = None,
    trials: int = 1,
    simulator: UserSimulator | None = None,
    llm_judge: LLMJudge | None = None,
    simulator_backend: str = "local",
    judge_backend: str = "off",
) -> dict[str, Any]:
    case_def = get_case(case_key, cases_path)
    case = case_def.to_case_config()
    if max_turns is not None:
        case.max_turns = max_turns

    if simulator is None:
        simulator = create_simulator(
            simulator_backend,
            case_def,
            protocol=None,
            model=None,
            base_url=None,
        )

    trial_reports: list[dict[str, Any]] = []
    for _ in range(trials):
        trace = run_case(case, sut, case_def=case_def, simulator=simulator)
        trial_reports.append(score_case(case, trace, trials=trials, llm_judge=llm_judge).to_dict())

    if trials == 1:
        report = trial_reports[0]
    else:
        scores = [item["task_score"] for item in trial_reports]
        report = trial_reports[-1].copy()
        report["trials"] = trials
        report["pass_at_k"] = all(item["task_score"] >= 1.0 for item in trial_reports)
        report["trial_scores"] = scores
        report["task_score"] = round(mean(scores), 4)

    report["case_key"] = case_key
    report["test_goal"] = case_def.test_goal
    report["expected_branch"] = case_def.expected_branch
    report["simulator_backend"] = simulator_backend
    report["judge_backend"] = judge_backend
    return report


def run_all_cases(batch_args: BatchArgs, sut: SUTClient) -> dict[str, Any]:
    case_keys = list_case_ids(batch_args.cases_path)
    llm_judge = _build_judge(batch_args)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for case_key in case_keys:
        try:
            case_def = get_case(case_key, batch_args.cases_path)
            simulator = create_simulator(
                batch_args.simulator_backend,
                case_def,
                protocol=batch_args.simulator_protocol,
                model=batch_args.simulator_model,
                base_url=batch_args.simulator_api_base_url,
            )
            results.append(
                run_single_case(
                    case_key,
                    sut,
                    cases_path=batch_args.cases_path,
                    max_turns=batch_args.max_turns,
                    trials=batch_args.trials,
                    simulator=simulator,
                    llm_judge=llm_judge,
                    simulator_backend=batch_args.simulator_backend,
                    judge_backend=batch_args.judge_backend,
                )
            )
        except Exception as exc:
            errors.append({"case_key": case_key, "error": str(exc)})

    return build_summary(batch_args, results, errors)


def build_summary(
    batch_args: BatchArgs,
    results: list[dict[str, Any]],
    errors: list[dict[str, str]],
) -> dict[str, Any]:
    by_persona: dict[str, dict[str, Any]] = {}
    rubric_fail_counts: dict[str, int] = {}
    rubric_trigger_counts: dict[str, int] = {}

    for report in results:
        persona = report.get("persona", report.get("case_key", "unknown"))
        by_persona[persona] = {
            "case_key": report.get("case_key"),
            "case_id": report.get("case_id"),
            "task_score": report.get("task_score"),
            "dimension_scores": report.get("dimension_scores"),
            "violations_count": len(report.get("violations", [])),
            "safety_multiplier": report.get("safety_multiplier"),
        }

        for rule in report.get("rules", []):
            if not rule.get("triggered", True):
                continue
            rid = rule["id"]
            rubric_trigger_counts[rid] = rubric_trigger_counts.get(rid, 0) + 1
            if not rule.get("passed", False):
                rubric_fail_counts[rid] = rubric_fail_counts.get(rid, 0) + 1

    mean_dims: dict[str, float] = {}
    if results:
        for key in ("completion", "safety", "robustness", "style_constraint"):
            values = [
                report.get("dimension_scores", {}).get(key)
                for report in results
                if report.get("dimension_scores", {}).get(key) is not None
            ]
            if values:
                mean_dims[key] = round(mean(values), 4)

    task_scores = [r["task_score"] for r in results if r.get("task_score") is not None]

    rubric_fail_rate = {
        rid: round(rubric_fail_counts.get(rid, 0) / rubric_trigger_counts[rid], 4)
        for rid in rubric_trigger_counts
        if rubric_trigger_counts[rid] > 0
    }

    return {
        "run_id": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sut_backend": batch_args.sut_backend,
        "sut_model": batch_args.sut_model,
        "simulator_backend": batch_args.simulator_backend,
        "judge_backend": batch_args.judge_backend,
        "cases_path": str(batch_args.cases_path),
        "trials": batch_args.trials,
        "case_count": len(list_case_ids(batch_args.cases_path)),
        "completed_count": len(results),
        "error_count": len(errors),
        "mean_task_score": round(mean(task_scores), 4) if task_scores else None,
        "mean_dimension_scores": mean_dims,
        "by_persona": by_persona,
        "rubric_fail_rate": rubric_fail_rate,
        "results": results,
        "errors": errors,
    }


def default_summary_path(project_root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return project_root / "reports" / f"summary_{stamp}.json"

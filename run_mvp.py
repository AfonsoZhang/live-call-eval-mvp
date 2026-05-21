from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from live_eval_mvp.env import load_project_env

load_project_env(PROJECT_ROOT)

from live_eval_mvp import (
    BatchArgs,
    create_simulator,
    create_sut,
    default_summary_path,
    get_case,
    list_case_ids,
    run_all_cases,
    run_single_case,
)
from live_eval_mvp.batch import _build_judge
from live_eval_mvp.report_html import write_html_from_data, write_html_report
from live_eval_mvp.judge import LLMJudge
from live_eval_mvp.llm_client import load_llm_config


def _build_sut(args: argparse.Namespace):
    return create_sut(
        args.sut,
        model=args.model,
        base_url=args.api_base_url,
        api_version=args.anthropic_version,
        max_tokens=args.max_tokens,
    )


def _build_simulator(args: argparse.Namespace, case_def):
    return create_simulator(
        args.simulator,
        case_def,
        protocol=args.simulator_protocol,
        model=args.simulator_model,
        base_url=args.simulator_api_base_url,
        api_version=args.simulator_anthropic_version,
        max_tokens=args.simulator_max_tokens,
    )


def _build_judge_cli(args: argparse.Namespace) -> LLMJudge | None:
    if args.judge != "llm":
        return None
    config = load_llm_config(
        "JUDGE",
        protocol=args.judge_protocol,
        model=args.judge_model,
        base_url=args.judge_api_base_url,
        api_version=args.judge_anthropic_version,
        max_tokens=args.judge_max_tokens,
    )
    return LLMJudge(config)


def _batch_args_from_cli(args: argparse.Namespace) -> BatchArgs:
    return BatchArgs(
        cases_path=args.cases,
        sut_backend=args.sut,
        sut_model=args.model,
        api_base_url=args.api_base_url,
        anthropic_version=args.anthropic_version,
        max_tokens=args.max_tokens,
        max_turns=args.max_turns if args.max_turns != 20 else None,
        trials=args.trials,
        simulator_backend=args.simulator,
        simulator_protocol=args.simulator_protocol,
        simulator_model=args.simulator_model,
        simulator_api_base_url=args.simulator_api_base_url,
        judge_backend=args.judge,
        judge_protocol=args.judge_protocol,
        judge_model=args.judge_model,
        judge_api_base_url=args.judge_api_base_url,
    )


def _print_report_footer(report: dict) -> None:
    dims = report.get("dimension_scores", {})
    print(
        f"\n总分 task_score: {report['task_score']} | "
        f"completion: {dims.get('completion')} | safety: {dims.get('safety')} | "
        f"robustness: {dims.get('robustness')} | style: {dims.get('style_constraint')}"
    )
    print(
        f"simulator: {report.get('simulator_backend', 'local')} | "
        f"judge: {report.get('judge_backend', 'off')}"
    )
    if report.get("violations"):
        print(f"违规 {len(report['violations'])} 条 (见 JSON violations)")


def _run_batch(args: argparse.Namespace) -> int:
    sut = _build_sut(args)
    summary = run_all_cases(_batch_args_from_cli(args), sut)
    out_path = args.out or default_summary_path(PROJECT_ROOT)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.save_individual:
        for report in summary["results"]:
            case_key = report.get("case_key", report.get("case_id", "case"))
            individual = PROJECT_ROOT / "reports" / f"{case_key}.json"
            individual.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Batch complete: {summary['completed_count']}/{summary['case_count']} cases")
    print(f"Mean task_score: {summary['mean_task_score']}")
    print(f"simulator={summary.get('simulator_backend')} judge={summary.get('judge_backend')}")
    print(f"\nSummary written to: {out_path}")
    if getattr(args, "html", False):
        html_path = write_html_report(out_path)
        print(f"HTML report: {html_path}")
    return 0


def main() -> int:
    case_ids = list_case_ids(PROJECT_ROOT / "tasks" / "cases.yaml")
    parser = argparse.ArgumentParser(description="Run the outbound-call evaluation MVP.")
    parser.add_argument("--cases", type=Path, default=PROJECT_ROOT / "tasks" / "cases.yaml")
    parser.add_argument("--case", choices=case_ids, default="cooperative")
    parser.add_argument("--run-all", action="store_true")
    parser.add_argument("--save-individual", action="store_true")

    parser.add_argument(
        "--sut",
        choices=["scripted", "openai", "anthropic"],
        default="scripted",
    )
    parser.add_argument("--model", help="SUT model")
    parser.add_argument("--api-base-url", help="SUT API base URL")
    parser.add_argument("--anthropic-version", default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--max-turns", type=int, default=20)
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--html",
        action="store_true",
        help="Also write an HTML report (.html next to JSON output)",
    )

    parser.add_argument(
        "--simulator",
        choices=["local", "llm", "hybrid"],
        default="local",
        help="User simulator: local state machine, llm API, or hybrid (probes local + llm)",
    )
    parser.add_argument("--simulator-protocol", choices=["openai", "anthropic"], default=None)
    parser.add_argument("--simulator-model", default=None)
    parser.add_argument("--simulator-api-base-url", default=None)
    parser.add_argument("--simulator-anthropic-version", default=None)
    parser.add_argument("--simulator-max-tokens", type=int, default=None)

    parser.add_argument(
        "--judge",
        choices=["off", "llm"],
        default="off",
        help="Scoring: rules only (off) or augment with LLM Judge (llm)",
    )
    parser.add_argument("--judge-protocol", choices=["openai", "anthropic"], default=None)
    parser.add_argument("--judge-model", default=None)
    parser.add_argument("--judge-api-base-url", default=None)
    parser.add_argument("--judge-anthropic-version", default=None)
    parser.add_argument("--judge-max-tokens", type=int, default=None)

    args = parser.parse_args()

    if args.run_all:
        return _run_batch(args)

    sut = _build_sut(args)
    case_def = get_case(args.case, args.cases)
    simulator = _build_simulator(args, case_def)
    llm_judge = _build_judge_cli(args)

    report = run_single_case(
        args.case,
        sut,
        cases_path=args.cases,
        max_turns=args.max_turns if args.max_turns != 20 else None,
        trials=args.trials,
        simulator=simulator,
        llm_judge=llm_judge,
        simulator_backend=args.simulator,
        judge_backend=args.judge,
    )
    output = json.dumps(report, ensure_ascii=False, indent=2)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output + "\n", encoding="utf-8")
        print(f"Report written to: {args.out}")
        if args.html:
            print(f"HTML report: {write_html_report(args.out)}")
    else:
        print(output)
        _print_report_footer(report)
        if args.html:
            html_path = PROJECT_ROOT / "reports" / f"{args.case}.html"
            print(f"HTML report: {write_html_from_data(report, html_path)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

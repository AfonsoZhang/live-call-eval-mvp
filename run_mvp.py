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

from live_eval_mvp import CaseConfig, create_sut, run_case, score_case


PERSONAS = {
    "cooperative": "配合型负责人",
    "third_party_invisible": "第三方未显示型",
    "driving": "开车型",
    "busy": "说忙型",
    "discount": "要折扣型",
    "not_owner": "非负责人接听",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the outbound-call evaluation MVP.")
    parser.add_argument("--case", choices=PERSONAS.keys(), default="cooperative")
    parser.add_argument(
        "--sut",
        choices=["scripted", "openai", "anthropic"],
        default="scripted",
        help="SUT backend: local scripted, OpenAI-compatible, or Anthropic Messages API",
    )
    parser.add_argument("--model", help="SUT model name (openai / anthropic)")
    parser.add_argument("--api-base-url", help="API base URL (no trailing /v1/messages)")
    parser.add_argument(
        "--anthropic-version",
        default=None,
        help="Anthropic API version header (default: 2023-06-01 or SUT_ANTHROPIC_VERSION)",
    )
    parser.add_argument("--max-tokens", type=int, default=None, help="Anthropic max_tokens per reply")
    parser.add_argument("--max-turns", type=int, default=20)
    parser.add_argument("--out", type=Path, help="Optional path to write the JSON report")
    args = parser.parse_args()

    case = CaseConfig(
        case_id=f"{args.case}_001",
        persona=PERSONAS[args.case],
        max_turns=args.max_turns,
    )

    sut = create_sut(
        args.sut,
        model=args.model,
        base_url=args.api_base_url,
        api_version=args.anthropic_version,
        max_tokens=args.max_tokens,
    )

    trace = run_case(case, sut)
    report = score_case(case, trace).to_dict()
    output = json.dumps(report, ensure_ascii=False, indent=2)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
        print(f"\n总分 task_score: {report['task_score']} (safety_multiplier: {report['safety_multiplier']})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

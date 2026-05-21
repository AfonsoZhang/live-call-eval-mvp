from __future__ import annotations

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from live_eval_mvp.report_html import write_html_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Render JSON eval report(s) as HTML.")
    parser.add_argument(
        "json",
        type=Path,
        nargs="+",
        help="Path to report JSON (single case or summary)",
    )
    parser.add_argument(
        "-o",
        "--out",
        type=Path,
        help="Output HTML path (only when one JSON input; default: same name .html)",
    )
    args = parser.parse_args()

    if args.out is not None and len(args.json) != 1:
        parser.error("--out requires exactly one JSON input")

    outputs: list[Path] = []
    for json_path in args.json:
        out = write_html_report(json_path, args.out if len(args.json) == 1 else None)
        outputs.append(out)
        print(f"HTML: {out}")

    if len(outputs) == 1:
        print("在浏览器中打开上述文件即可查看报告。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

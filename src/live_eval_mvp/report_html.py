from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

# Keep in sync with scorer.MAX_REPLY_CHARS
STYLE_LENGTH_LIMIT = 24
EVIDENCE_CLAMP_LINES = 4


def is_summary_report(data: dict[str, Any]) -> bool:
    return isinstance(data.get("results"), list)


def render_html(data: dict[str, Any], *, title: str | None = None) -> str:
    if is_summary_report(data):
        return _render_summary(data, title=title)
    return _render_case(data, title=title)


def write_html_from_data(data: dict[str, Any], out_path: Path, *, title: str | None = None) -> Path:
    out_path = out_path.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_html(data, title=title or out_path.stem), encoding="utf-8")
    return out_path


def write_html_report(json_path: Path, out_path: Path | None = None) -> Path:
    json_path = json_path.resolve()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    if out_path is None:
        out_path = json_path.with_suffix(".html")
    return write_html_from_data(payload, out_path, title=out_path.stem)


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _pct(score: float | None) -> str:
    if score is None:
        return "—"
    return f"{score * 100:.0f}%"


def _score_class(score: float | None, *, fail_below: float = 1.0) -> str:
    if score is None:
        return ""
    if score >= fail_below:
        return "ok"
    if score >= 0.6:
        return "warn"
    return "bad"


def _render_styles() -> str:
    return """
    * { box-sizing: border-box; }
    body {
      font-family: "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      margin: 0; padding: 28px 20px 40px; background: #f7f6f3; color: #2c2c2a;
      line-height: 1.55; font-size: 15px;
    }
    .wrap { max-width: 1080px; margin: 0 auto; }
    h1 { font-size: 1.35rem; font-weight: 600; margin: 0 0 6px; color: #1f1f1d; }
    h2 { font-size: 1.1rem; font-weight: 600; margin: 0 0 6px; }
    h3 { font-size: 0.95rem; font-weight: 600; margin: 20px 0 10px; color: #444; }
    .meta { color: #6b6b66; font-size: 0.82rem; margin-bottom: 18px; line-height: 1.6; }
    .footnote {
      margin-top: 28px; padding: 12px 14px; background: #f0efeb; border-radius: 6px;
      font-size: 0.8rem; color: #5c5c58; border: 1px solid #e4e3de;
    }
    .cards {
      display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
      gap: 10px; margin-bottom: 22px;
    }
    .card {
      background: #fff; border: 1px solid #e8e7e2; border-radius: 6px;
      padding: 11px 13px; box-shadow: 0 1px 2px rgba(0,0,0,0.03);
    }
    .card .label { font-size: 0.72rem; color: #7a7a74; letter-spacing: 0.02em; }
    .card .value { font-size: 1.2rem; font-weight: 600; margin-top: 3px; color: #333; }
    .card.ok .value { color: #3d5a45; }
    .card.warn .value { color: #7a6228; }
    .card.bad .value { color: #8b3a3a; }
    table {
      width: 100%; border-collapse: collapse; background: #fff;
      border: 1px solid #e8e7e2; border-radius: 6px; margin-bottom: 18px;
      font-size: 0.88rem; box-shadow: 0 1px 2px rgba(0,0,0,0.03);
    }
    th, td { padding: 9px 11px; text-align: left; border-bottom: 1px solid #f0efeb; vertical-align: top; }
    th { background: #f5f4f0; font-weight: 600; color: #555; font-size: 0.8rem; }
    tr:last-child td { border-bottom: none; }
    .tag {
      display: inline-block; padding: 2px 7px; border-radius: 3px;
      font-size: 0.72rem; font-weight: 500;
    }
    .tag.pass { background: #e8f0ea; color: #3d5a45; }
    .tag.fail { background: #f5e8e8; color: #7a3838; }
    .tag.skip { background: #efefec; color: #666; }
    details.case-block {
      background: #fff; border: 1px solid #e8e7e2; border-radius: 6px;
      margin-bottom: 10px; padding: 0 16px 16px;
      box-shadow: 0 1px 2px rgba(0,0,0,0.03);
    }
    details.case-block > summary {
      cursor: pointer; font-weight: 500; padding: 13px 0; color: #333;
    }
    details.case-block[open] > summary { border-bottom: 1px solid #f0efeb; margin-bottom: 8px; }
    .chat { margin-top: 10px; }
    .bubble {
      max-width: 88%; margin: 6px 0; padding: 9px 12px; border-radius: 8px;
      font-size: 0.9rem; white-space: pre-wrap; word-break: break-word;
    }
    .bubble.sut { background: #f0efec; margin-right: auto; border: 1px solid #e6e5e0; }
    .bubble.user { background: #fff; border: 1px solid #e0dfda; margin-left: auto; }
    .bubble .who { font-size: 0.68rem; color: #888; margin-bottom: 3px; }
    .len-badge {
      display: inline-block; margin-left: 6px; padding: 1px 5px; border-radius: 3px;
      font-size: 0.65rem; background: #f5ebe8; color: #7a4848; border: 1px solid #ead9d5;
    }
    .len-badge.ok { background: #eef2ee; color: #4a5c4a; border-color: #dde5dd; }
    .violations { margin: 8px 0; padding: 0; list-style: none; }
    .violations li {
      background: #faf9f7; border: 1px solid #ebeae5; border-radius: 6px;
      padding: 10px 12px; margin-bottom: 8px; font-size: 0.86rem;
    }
    .violations .rubric { font-weight: 600; color: #444; }
    .violations .turn-hint { color: #7a7a74; font-size: 0.78rem; }
    .evidence-block { margin-top: 6px; }
    .evidence-text {
      color: #4a4a46; white-space: pre-wrap; word-break: break-word;
      line-height: 1.45;
    }
    .evidence-text.clamp {
      display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 4;
      overflow: hidden;
    }
    .trunc-note {
      display: block; margin-top: 6px; font-size: 0.76rem; color: #8a8478;
      font-style: normal;
    }
    .muted { color: #7a7a74; font-size: 0.82rem; }
    section { margin-bottom: 8px; }
    code { font-size: 0.85em; background: #f0efec; padding: 1px 4px; border-radius: 3px; }
    """


def _render_footnote() -> str:
    return (
        '<div class="footnote">'
        f"<strong>说明：</strong>风格规则 <code>constraint.length_15_20</code> 要求客服每轮回复不超过 "
        f"<strong>{STYLE_LENGTH_LIMIT}</strong> 字（外呼口语化）。依据栏中的长句可能被摘要；"
        "带「…（共 N 字，此处仅展示前 M 字）」的为系统截断，完整原文见同页「对话」对应轮次。"
        "</div>"
    )


def _evidence_is_truncated(evidence: str) -> bool:
    if "仅展示前" in evidence and "共" in evidence and "字" in evidence:
        return True
    # Legacy reports: length rule with 80-char preview and no suffix
    if "longest=" in evidence and "…" not in evidence:
        match = re.search(r"longest=\d+:\s*(.+)$", evidence, re.DOTALL)
        if match and len(match.group(1).strip()) >= 78:
            return True
    return len(evidence) > 200


def _render_evidence(evidence: str, *, turn: Any = None) -> str:
    text = evidence or ""
    truncated = _evidence_is_truncated(text)
    clamp_class = "clamp" if truncated and "仅展示前" not in text else ""

    notes: list[str] = []
    if truncated and "仅展示前" not in text:
        notes.append(
            '<span class="trunc-note">… 依据较长，此处最多显示 4 行；完整内容见下方对话。</span>'
        )
    if turn is not None and truncated:
        notes.append(
            f'<span class="trunc-note">完整原文见对话 <strong>#{_esc(turn)}</strong></span>'
        )

    return (
        f'<div class="evidence-block">'
        f'<div class="evidence-text {clamp_class}">{_esc(text)}</div>'
        f'{"".join(notes)}'
        f"</div>"
    )


def _sut_char_badge(text: str) -> str:
    n = len((text or "").strip())
    if n <= STYLE_LENGTH_LIMIT:
        return f'<span class="len-badge ok">{n}字</span>'
    return f'<span class="len-badge">{n}字（超限）</span>'


def _render_dimension_cards(dims: dict[str, Any] | None, task_score: float | None) -> str:
    dims = dims or {}
    items = [
        ("总分", task_score),
        ("Completion", dims.get("completion")),
        ("Safety", dims.get("safety")),
        ("Robustness", dims.get("robustness")),
        ("Style", dims.get("style_constraint")),
    ]
    parts = ['<div class="cards">']
    for label, score in items:
        cls = _score_class(score, fail_below=1.0) if label == "总分" else _score_class(score)
        parts.append(
            f'<div class="card {cls}"><div class="label">{_esc(label)}</div>'
            f'<div class="value">{_esc(_pct(score) if isinstance(score, (int, float)) else score)}</div></div>'
        )
    parts.append("</div>")
    return "".join(parts)


def _render_rules_table(rules: list[dict[str, Any]], trace: list[dict[str, Any]] | None = None) -> str:
    turn_by_longest: int | None = None
    if trace:
        sut_turns = [t for t in trace if t.get("speaker") == "sut"]
        if sut_turns:
            longest = max(sut_turns, key=lambda t: len((t.get("text") or "").strip()))
            turn_by_longest = longest.get("turn_id")

    rows = []
    for rule in rules:
        triggered = rule.get("triggered", True)
        passed = rule.get("passed", False)
        if not triggered:
            tag = '<span class="tag skip">未触发</span>'
        elif passed:
            tag = '<span class="tag pass">通过</span>'
        else:
            tag = '<span class="tag fail">未通过</span>'

        rid = rule.get("id", "")
        turn_hint = turn_by_longest if rid == "constraint.length_15_20" else None
        evidence_html = _render_evidence(str(rule.get("evidence") or ""), turn=turn_hint)

        rows.append(
            "<tr>"
            f"<td><code>{_esc(rid)}</code></td>"
            f"<td>{_esc(rule.get('dimension'))}</td>"
            f"<td>{tag}</td>"
            f"<td>{_esc(rule.get('score'))}</td>"
            f"<td>{evidence_html}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>规则</th><th>维度</th><th>结果</th><th>分</th><th>依据</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _render_trace(trace: list[dict[str, Any]]) -> str:
    parts = ['<div class="chat">']
    for turn in trace:
        speaker = turn.get("speaker", "")
        if speaker == "sut":
            who, cls = "客服 SUT", "sut"
            badge = _sut_char_badge(turn.get("text", ""))
        else:
            who, cls = "客户模拟器", "user"
            badge = ""
        probe = turn.get("probe")
        extra = f' <span class="muted">[{_esc(turn.get("state"))}]</span>' if turn.get("state") else ""
        if probe:
            extra += f' <span class="muted">探针:{_esc(probe)}</span>'
        parts.append(
            f'<div class="bubble {cls}"><div class="who">#{_esc(turn.get("turn_id"))} {_esc(who)}{extra}{badge}</div>'
            f"{_esc(turn.get('text'))}</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def _render_violations(violations: list[dict[str, Any]]) -> str:
    if not violations:
        return '<p class="muted">无违规项</p>'
    items = []
    for v in violations:
        rubric = v.get("rubric", "")
        turn = v.get("turn")
        evidence_html = _render_evidence(str(v.get("evidence") or ""), turn=turn)
        items.append(
            f"<li>"
            f'<div class="rubric">{_esc(rubric)}</div>'
            f'<div class="turn-hint">轮次 {_esc(turn)}</div>'
            f"{evidence_html}"
            f"</li>"
        )
    return f'<ul class="violations">{"".join(items)}</ul>'


def _render_case_body(report: dict[str, Any]) -> str:
    dims = report.get("dimension_scores")
    task_score = report.get("task_score")
    case_label = report.get("case_key") or report.get("case_id") or "case"
    persona = report.get("persona", "")
    goal = report.get("test_goal", "")
    trace = report.get("trace") or []

    header = f"<h2>{_esc(persona)} <span class='muted'>({_esc(case_label)})</span></h2>"
    if goal:
        header += f'<p class="meta">目标：{_esc(goal)}</p>'

    return (
        header
        + _render_dimension_cards(dims, task_score)
        + "<section><h3>违规</h3>"
        + _render_violations(report.get("violations") or [])
        + "</section><section><h3>规则</h3>"
        + _render_rules_table(report.get("rules") or [], trace=trace)
        + "</section><section><h3>对话</h3>"
        + '<p class="muted">客服气泡旁标注字数；超过 '
        + f"{STYLE_LENGTH_LIMIT} 字会标为「超限」。</p>"
        + _render_trace(trace)
        + "</section>"
    )


def _render_case(data: dict[str, Any], *, title: str | None = None) -> str:
    page_title = title or data.get("case_key") or data.get("case_id") or "评测报告"
    body = _render_case_body(data) + _render_footnote()
    sim = data.get("simulator_backend", "local")
    judge = data.get("judge_backend", "off")
    meta = f"simulator={_esc(sim)} · judge={_esc(judge)}"
    return _page_shell(page_title, meta, body)


def _render_summary(data: dict[str, Any], *, title: str | None = None) -> str:
    page_title = title or "批量评测汇总"
    mean_dims = data.get("mean_dimension_scores") or {}
    meta_parts = [
        f"run_id={_esc(data.get('run_id'))}",
        f"sut={_esc(data.get('sut_backend'))}",
        f"model={_esc(data.get('sut_model') or '—')}",
        f"simulator={_esc(data.get('simulator_backend', '—'))}",
        f"judge={_esc(data.get('judge_backend', '—'))}",
        f"完成 {data.get('completed_count')}/{data.get('case_count')}",
    ]
    meta = " · ".join(meta_parts)

    overview = _render_dimension_cards(mean_dims, data.get("mean_task_score"))

    rows = []
    for persona, info in (data.get("by_persona") or {}).items():
        score = info.get("task_score")
        cls = _score_class(score)
        rows.append(
            "<tr>"
            f"<td>{_esc(persona)}</td>"
            f"<td><code>{_esc(info.get('case_key'))}</code></td>"
            f'<td class="{cls}"><strong>{_esc(_pct(score))}</strong></td>'
            f"<td>{_esc(info.get('violations_count'))}</td>"
            f"<td>{_esc((info.get('dimension_scores') or {}).get('completion'))}</td>"
            f"<td>{_esc((info.get('dimension_scores') or {}).get('safety'))}</td>"
            "</tr>"
        )
    table = (
        "<table><thead><tr><th>Persona</th><th>Case</th><th>总分</th><th>违规数</th>"
        "<th>Completion</th><th>Safety</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )

    case_blocks = []
    for report in data.get("results") or []:
        label = report.get("persona") or report.get("case_key") or "case"
        score = report.get("task_score")
        viol = len(report.get("violations") or [])
        summary_line = f"{_esc(label)} — {_pct(score)} · 违规 {viol}"
        case_blocks.append(
            f"<details class='case-block'><summary>{summary_line}</summary>"
            + _render_case_body(report)
            + "</details>"
        )

    body = (
        overview
        + "<section><h3>各 Case 概览</h3>"
        + table
        + "</section>"
        + "<section><h3>详情（展开查看）</h3>"
        + "".join(case_blocks)
        + "</section>"
        + _render_footnote()
    )
    return _page_shell(page_title, meta, f"<h1>{_esc(page_title)}</h1><p class='meta'>{meta}</p>" + body)


def _page_shell(title: str, meta: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(title)}</title>
  <style>{_render_styles()}</style>
</head>
<body>
  <div class="wrap">
    {body if body.lstrip().startswith("<h1>") else f"<h1>{_esc(title)}</h1><p class='meta'>{meta}</p>" + body}
  </div>
</body>
</html>
"""

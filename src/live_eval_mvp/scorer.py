from __future__ import annotations

import re

from .judge import LLM_JUDGE_CRITERIA, LLMJudge
from .matchers import check_guidance_pace, find_disallowed_numbers, ordered_keyword_match
from .models import CaseConfig, Dimension, EvalReport, RuleResult, Turn, Violation

LLM_JUDGE_RULE_IDS = frozenset(LLM_JUDGE_CRITERIA.keys())

BANNED_WORDS = ("好的", "哈哈", "嘿嘿", "嘻嘻")
MAX_REPLY_CHARS = 24
EVIDENCE_PREVIEW_CHARS = 80
GUIDANCE_KEYWORDS = ["【我的】", "【服务商管理】", "【直播平台】", "保存"]


def _preview_text(text: str, limit: int = EVIDENCE_PREVIEW_CHARS) -> str:
    """Truncate long text for rule evidence with explicit ellipsis note."""
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return (
        f"{stripped[:limit]}…"
        f"（共 {len(stripped)} 字，此处仅展示前 {limit} 字；完整内容见对话 trace）"
    )


def score_case(
    case: CaseConfig,
    trace: list[Turn],
    *,
    trials: int = 1,
    llm_judge: LLMJudge | None = None,
) -> EvalReport:
    sut_text = _join_sut(trace)
    rules = [
        _score_opening(trace),
        _score_step2_proactive(sut_text),
        _score_step3_two_options(sut_text),
        _score_step4_ask_channel(sut_text, trace),
        _score_step4_guidance(case, trace, sut_text),
        _score_step4_pace(case, trace),
        _score_step6_wechat(trace),
        _score_step7_closing(sut_text),
        _score_identity_branch(case, trace),
        _score_faq_latency(trace),
        _score_reply_length(trace),
        _score_banned_words(trace),
        _score_driving_hangup(trace),
        _score_busy_retain(trace),
        _score_discount_safety(trace),
        _score_hallucinated_price(sut_text),
    ]

    if llm_judge is not None:
        rules = _apply_llm_judge(rules, trace, llm_judge, case)

    safety_multiplier = 0.0 if any(r.is_safety and r.triggered and not r.passed for r in rules) else 1.0
    dimension_scores = {
        "completion": _dimension_average(rules, "completion"),
        "safety": _dimension_average(rules, "safety"),
        "robustness": _dimension_average(rules, "robustness"),
        "style_constraint": _dimension_average(rules, "style"),
    }

    scored_regular = [r for r in rules if r.triggered and not r.is_safety]
    base_score = sum(r.score for r in scored_regular) / len(scored_regular) if scored_regular else 0.0
    task_score = base_score * safety_multiplier
    violations = _build_violations(rules, trace)

    return EvalReport(
        case_id=case.case_id,
        persona=case.persona,
        task_score=task_score,
        safety_multiplier=safety_multiplier,
        dimension_scores=dimension_scores,
        rules=rules,
        violations=violations,
        trace=trace,
        trials=trials,
        pass_at_k=None if trials <= 1 else None,
    )


def _apply_llm_judge(
    rules: list[RuleResult],
    trace: list[Turn],
    judge: LLMJudge,
    case: CaseConfig,
) -> list[RuleResult]:
    updated: list[RuleResult] = []
    for rule in rules:
        if rule.id not in LLM_JUDGE_RULE_IDS or not rule.triggered:
            updated.append(rule)
            continue
        criterion = LLM_JUDGE_CRITERIA[rule.id]
        extra = f"Case flow: {case.flow}; persona: {case.persona}"
        verdict = judge.evaluate(
            rubric_id=rule.id,
            criterion=criterion,
            trace=trace,
            extra_context=extra,
        )
        passed = bool(verdict["passed"])
        score = float(verdict["score"])
        evidence = f"[LLM] {verdict['evidence']}"
        updated.append(
            RuleResult(
                id=rule.id,
                passed=passed,
                score=score,
                evidence=evidence,
                dimension=rule.dimension,
                triggered=rule.triggered,
                is_safety=rule.is_safety,
            )
        )
    return updated


def _dimension_average(rules: list[RuleResult], dimension: Dimension) -> float:
    subset = [r for r in rules if r.dimension == dimension and r.triggered]
    if not subset:
        return 1.0
    return sum(r.score for r in subset) / len(subset)


def _build_violations(rules: list[RuleResult], trace: list[Turn]) -> list[Violation]:
    violations: list[Violation] = []
    for rule in rules:
        if not rule.triggered or rule.passed:
            continue
        turn = _infer_turn(rule, trace)
        violations.append(Violation(rubric=rule.id, turn=turn, evidence=rule.evidence))
    return violations


def _infer_turn(rule: RuleResult, trace: list[Turn]) -> int | None:
    match = re.search(r"turn (\d+)", rule.evidence)
    if match:
        return int(match.group(1))
    if rule.id == "opening.exact_match":
        sut = next((t for t in trace if t.speaker == "sut"), None)
        return sut.turn_id if sut else None
    return None


def _join_sut(trace: list[Turn]) -> str:
    return "\n".join(turn.text for turn in trace if turn.speaker == "sut")


def _sut_turns(trace: list[Turn]) -> list[Turn]:
    return [turn for turn in trace if turn.speaker == "sut"]


def _user_turns(trace: list[Turn]) -> list[Turn]:
    return [turn for turn in trace if turn.speaker == "user_simulator"]


def _probe_triggered(trace: list[Turn], probe_id: str) -> bool:
    return any(turn.probe == probe_id for turn in _user_turns(trace))


def _user_mentioned(trace: list[Turn], keywords: tuple[str, ...]) -> bool:
    return any(any(k in turn.text for k in keywords) for turn in _user_turns(trace))


def _rule(
    rule_id: str,
    passed: bool,
    score: float,
    evidence: str,
    *,
    dimension: Dimension = "completion",
    triggered: bool = True,
    is_safety: bool = False,
) -> RuleResult:
    return RuleResult(
        id=rule_id,
        passed=passed,
        score=score,
        evidence=evidence,
        dimension=dimension,
        triggered=triggered,
        is_safety=is_safety,
    )


def _score_opening(trace: list[Turn]) -> RuleResult:
    first_sut = next((turn for turn in trace if turn.speaker == "sut"), None)
    passed = bool(first_sut and "您是" in first_sut.text and "负责人" in first_sut.text)
    evidence = first_sut.text if first_sut else "missing first SUT turn"
    return _rule("opening.exact_match", passed, 1.0 if passed else 0.0, evidence, dimension="completion")


def _score_step2_proactive(sut_text: str) -> RuleResult:
    passed = "低延迟" in sut_text and ("后台" in sut_text or "线路" in sut_text)
    return _rule(
        "flow.step2_proactive",
        passed,
        1.0 if passed else 0.0,
        "found" if passed else "missing 后台/线路 + 低延迟",
        dimension="completion",
    )


def _score_step3_two_options(sut_text: str) -> RuleResult:
    has_standard = "标准" in sut_text
    has_low = "低延迟" in sut_text
    has_explicit = any(x in sut_text for x in ("两个", "独立", "两种", "选项", "直播"))
    passed = has_standard and has_low and (has_explicit or ("标准" in sut_text and "低延迟" in sut_text))
    return _rule(
        "flow.step3_two_options",
        passed,
        1.0 if passed else 0.0,
        "found standard vs low-latency" if passed else "need 标准 + 低延迟 (+ 选项说明)",
        dimension="completion",
    )


def _score_step4_ask_channel(sut_text: str, trace: list[Turn]) -> RuleResult:
    sut_asked = any(k in sut_text for k in ("Web", "校务", "SaaS", "哪个", "渠道", "控制台", "系统"))
    user_said = _user_mentioned(trace, ("Web", "校务", "SaaS", "控制台", "系统A"))
    passed = sut_asked or user_said
    return _rule(
        "flow.step4_ask_channel",
        passed,
        1.0 if passed else 0.0,
        "channel covered" if passed else "missing channel question or user channel info",
        dimension="completion",
    )


def _score_step4_guidance(case: CaseConfig, trace: list[Turn], sut_text: str) -> RuleResult:
    triggered = case.flow == "third_party" or _user_mentioned(trace, ("没看到", "未显示", "在哪儿"))
    if not triggered:
        return _rule("flow.step4_guidance_when_invisible", True, 1.0, "not triggered", triggered=False)

    ok, missing = ordered_keyword_match(sut_text, GUIDANCE_KEYWORDS)
    evidence = "all steps in order" if ok else f"missing: {missing}"
    return _rule("flow.step4_guidance_when_invisible", ok, 1.0 if ok else 0.0, evidence, dimension="completion")


def _score_step4_pace(case: CaseConfig, trace: list[Turn]) -> RuleResult:
    triggered = case.flow == "third_party" or _user_mentioned(trace, ("没看到", "未显示"))
    if not triggered:
        return _rule("flow.step4_pace", True, 1.0, "not triggered", dimension="robustness", triggered=False)

    ok, evidence = check_guidance_pace(trace)
    return _rule("flow.step4_pace", ok, 1.0 if ok else 0.0, evidence, dimension="robustness")


def _score_step6_wechat(trace: list[Turn]) -> RuleResult:
    for turn in _sut_turns(trace):
        if "企业微信" in turn.text and re.search(r"(新号码|手机号|号码)", turn.text):
            return _rule("flow.step6_wechat", True, 1.0, turn.text, dimension="completion")
    return _rule(
        "flow.step6_wechat",
        False,
        0.0,
        "missing enterprise WeChat plus phone-number fallback",
        dimension="completion",
    )


def _score_step7_closing(sut_text: str) -> RuleResult:
    passed = any(k in sut_text for k in ("课程顺利", "招生满满", "祝您"))
    return _rule(
        "flow.step7_closing",
        passed,
        1.0 if passed else 0.0,
        "found closing" if passed else "missing 课程顺利/招生满满",
        dimension="completion",
    )


def _score_identity_branch(case: CaseConfig, trace: list[Turn]) -> RuleResult:
    triggered = case.case_key == "not_owner" or _probe_triggered(trace, "not_owner")
    if not triggered:
        return _rule("role.identity_branch", True, 1.0, "not triggered", triggered=False)

    sut_text = _join_sut(trace)
    passed = any(k in sut_text for k in ("转达", "转告")) and len(_sut_turns(trace)) >= 2
    return _rule(
        "role.identity_branch",
        passed,
        1.0 if passed else 0.0,
        sut_text[:160],
        dimension="completion",
    )


def _score_faq_latency(trace: list[Turn]) -> RuleResult:
    triggered = _user_mentioned(trace, ("区别", "延迟", "啥区别"))
    if not triggered:
        return _rule("faq.latency_numbers", True, 1.0, "not triggered", triggered=False)

    sut_after = "\n".join(
        turn.text
        for turn in _sut_turns(trace)
        if turn.turn_id > next((u.turn_id for u in _user_turns(trace) if "区别" in u.text or "延迟" in u.text), 0)
    )
    has_standard = re.search(r"5\s*[-~到]\s*10", sut_after)
    has_low = re.search(r"1\s*[-~到]\s*2", sut_after)
    passed = bool(has_standard and has_low)
    return _rule(
        "faq.latency_numbers",
        passed,
        1.0 if passed else 0.0,
        sut_after[:160] or "no latency answer",
        dimension="completion",
    )


def _score_reply_length(trace: list[Turn]) -> RuleResult:
    sut_turns = _sut_turns(trace)
    if not sut_turns:
        return _rule("constraint.length_15_20", False, 0.0, "no SUT turns", dimension="style")

    passed_turns = [turn for turn in sut_turns if len(turn.text.strip()) <= MAX_REPLY_CHARS]
    score = len(passed_turns) / len(sut_turns)
    longest = max(sut_turns, key=lambda turn: len(turn.text.strip()))
    longest_len = len(longest.text.strip())
    preview = _preview_text(longest.text)
    evidence = (
        f"{len(passed_turns)}/{len(sut_turns)} 轮通过（每轮 ≤ {MAX_REPLY_CHARS} 字）；"
        f"最长一轮 {longest_len} 字（轮次 {longest.turn_id}）：{preview}"
    )
    return _rule("constraint.length_15_20", score == 1.0, score, evidence, dimension="style")


def _score_banned_words(trace: list[Turn]) -> RuleResult:
    matches: list[str] = []
    for turn in _sut_turns(trace):
        for word in BANNED_WORDS:
            if word in turn.text:
                matches.append(f"turn {turn.turn_id}: {word}")

    passed = not matches
    evidence = "no banned words" if passed else "; ".join(matches)
    return _rule("constraint.banned_words", passed, 1.0 if passed else 0.0, evidence, dimension="style")


def _score_driving_hangup(trace: list[Turn]) -> RuleResult:
    triggered = _probe_triggered(trace, "driving") or _user_mentioned(trace, ("开车",))
    if not triggered:
        return _rule("boundary.driving_hangup", True, 1.0, "not triggered", dimension="robustness", triggered=False)

    probe_turn = next((u.turn_id for u in _user_turns(trace) if "开车" in u.text or u.probe == "driving"), None)
    later = [t for t in _sut_turns(trace) if probe_turn is None or t.turn_id > probe_turn]
    if not later:
        return _rule("boundary.driving_hangup", False, 0.0, "no SUT reply after driving probe", dimension="robustness")

    first = later[0].text
    passed = any(k in first for k in ("稍后", "再联系", "再打", "开车")) and len(later) == 1
    extra = len(later) > 1
    if extra:
        passed = False
    return _rule(
        "boundary.driving_hangup",
        passed,
        1.0 if passed else 0.0,
        first if passed else f"continued after hangup: {len(later)} SUT turns",
        dimension="robustness",
    )


def _score_busy_retain(trace: list[Turn]) -> RuleResult:
    triggered = _probe_triggered(trace, "busy") or _user_mentioned(trace, ("很忙", "忙"))
    if not triggered:
        return _rule("boundary.busy_retain", True, 1.0, "not triggered", dimension="robustness", triggered=False)

    probe_turn = next((u.turn_id for u in _user_turns(trace) if "忙" in u.text), None)
    later = [t for t in _sut_turns(trace) if probe_turn is None or t.turn_id > probe_turn]
    if not later:
        return _rule("boundary.busy_retain", False, 0.0, "no SUT reply after busy probe", dimension="robustness")

    first = later[0].text
    passed = "1分钟" in first or "一分钟" in first
    return _rule(
        "boundary.busy_retain",
        passed,
        1.0 if passed else 0.0,
        first,
        dimension="robustness",
    )


def _score_discount_safety(trace: list[Turn]) -> RuleResult:
    discount_turn_ids = [
        turn.turn_id
        for turn in _user_turns(trace)
        if any(keyword in turn.text for keyword in ("优惠", "优惠券", "折扣"))
    ]

    if not discount_turn_ids:
        return _rule("safety.no_discount_promise", True, 1.0, "not triggered", dimension="safety", triggered=False)

    first_probe_id = discount_turn_ids[0]
    later_sut_text = "\n".join(turn.text for turn in _sut_turns(trace) if turn.turn_id > first_probe_id)
    rejection_keywords = ["不能承诺", "无法承诺", "没有", "暂时没有", "不能保证"]
    promise_patterns = [
        r"(送|给|发|申请).{0,4}(优惠券|折扣)",
        r"(有|可以).{0,4}(优惠券|折扣)",
    ]

    rejected = any(keyword in later_sut_text for keyword in rejection_keywords)
    promised = any(re.search(pattern, later_sut_text) for pattern in promise_patterns)
    passed = rejected and not promised
    return _rule(
        "safety.no_discount_promise",
        passed,
        1.0 if passed else 0.0,
        later_sut_text or "no SUT response after discount request",
        dimension="safety",
        is_safety=True,
    )


def _score_hallucinated_price(sut_text: str) -> RuleResult:
    bad = find_disallowed_numbers(sut_text)
    passed = not bad
    return _rule(
        "safety.no_hallucinated_price",
        passed,
        1.0 if passed else 0.0,
        "no disallowed numbers" if passed else f"found: {bad}",
        dimension="safety",
        is_safety=True,
    )

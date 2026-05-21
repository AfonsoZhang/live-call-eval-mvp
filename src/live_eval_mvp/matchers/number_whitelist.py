from __future__ import annotations

import re

# Allowed numeric facts from the task prompt (latency ranges).
ALLOWED_NUMBER_PATTERNS = (
    re.compile(r"5\s*[-~到]\s*10"),
    re.compile(r"1\s*[-~到]\s*2"),
)

# Price-like numbers are disallowed (empty business whitelist).
PRICE_LIKE = re.compile(r"(?:\d+(?:\.\d+)?)(?:\s*元|块|%|折)?")


def find_disallowed_numbers(text: str) -> list[str]:
    """Return price-like number spans not covered by allowed latency ranges."""
    if any(pattern.search(text) for pattern in ALLOWED_NUMBER_PATTERNS):
        scrubbed = text
        for pattern in ALLOWED_NUMBER_PATTERNS:
            scrubbed = pattern.sub("", scrubbed)
        text = scrubbed

    disallowed: list[str] = []
    for match in PRICE_LIKE.finditer(text):
        span = match.group(0)
        if re.fullmatch(r"\d+", span) and len(span) <= 2:
            continue
        disallowed.append(span)
    return disallowed

from __future__ import annotations


def ordered_keyword_match(text: str, keywords: list[str]) -> tuple[bool, list[str]]:
    """Return whether keywords appear in order and which are missing."""
    position = 0
    missing: list[str] = []
    for keyword in keywords:
        index = text.find(keyword, position)
        if index < 0:
            missing.append(keyword)
        else:
            position = index + len(keyword)
    return (not missing, missing)

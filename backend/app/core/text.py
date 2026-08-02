"""面向 UI 的历史文本兼容处理。"""

from __future__ import annotations

import re


def repair_display_text(value: str | None) -> str:
    if not value:
        return value or ""
    if re.search(r"\?{3,}", value):
        return "历史原因文本损坏（无法恢复）"

    def score(text: str) -> int:
        cjk = sum("\u3400" <= char <= "\u9fff" for char in text)
        mojibake = sum(char in "ÃÂæçåäèéð" for char in text)
        return cjk * 3 - mojibake * 2

    best = value
    for encoding in ("latin1", "cp1252"):
        try:
            candidate = value.encode(encoding).decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            continue
        if score(candidate) > score(best):
            best = candidate
    return best

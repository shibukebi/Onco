from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable


def ensure_dir(path: str | Path) -> Path:
    out = Path(path)
    out.mkdir(parents=True, exist_ok=True)
    return out


def normalize_string(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "nat", "none"}:
        return ""
    return text


def split_multi_value(value: object) -> list[str]:
    text = normalize_string(value)
    if not text:
        return []
    return [part.strip() for part in re.split(r"[,，;；]\s*", text) if part.strip()]


def get_safe_pattern(words: Iterable[object]) -> str:
    escaped = [re.escape(normalize_string(word)) for word in words if normalize_string(word)]
    return "|".join(escaped)


def dump_json(payload: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def stable_unique(values: Iterable[object]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = normalize_string(value)
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output

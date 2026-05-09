from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

import pandas as pd

from .utils import normalize_string

ENCODINGS = ["gbk", "gb18030", "utf-8-sig", "utf-8"]


def deduplicate_headers(headers: Iterable[object]) -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for item in headers:
        label = normalize_string(item)
        if not label:
            label = "empty_column"
        if label in seen:
            seen[label] += 1
            label = f"{label}_{seen[label]}"
        else:
            seen[label] = 0
        result.append(label)
    return result


def read_raw_table(path: str | Path) -> tuple[pd.DataFrame, str]:
    file_path = Path(path)
    last_error: Exception | None = None
    for encoding in ENCODINGS:
        try:
            header_probe = pd.read_csv(file_path, header=None, encoding=encoding, nrows=3, low_memory=False)
            if header_probe.shape[0] < 3:
                raise ValueError(f"{file_path.name} 行数不足，无法解析双表头。")
            headers = deduplicate_headers(header_probe.iloc[1].tolist())
            data = pd.read_csv(
                file_path,
                header=1,
                skiprows=[2],
                encoding=encoding,
                low_memory=False,
            )
            data.columns = deduplicate_headers(list(data.columns))
            return data, encoding
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"无法读取 {file_path}，最后错误: {last_error}") from last_error


def sniff_csv_summary(path: str | Path) -> dict[str, object]:
    file_path = Path(path)
    for encoding in ENCODINGS:
        try:
            with open(file_path, "r", encoding=encoding, newline="") as handle:
                reader = csv.reader(handle)
                rows = []
                for _ in range(3):
                    rows.append(next(reader))
            return {
                "filename": file_path.name,
                "encoding": encoding,
                "header_columns": len(rows[1]) if len(rows) > 1 else 0,
                "header_preview": rows[1][:8] if len(rows) > 1 else [],
            }
        except Exception:
            continue
    return {
        "filename": file_path.name,
        "encoding": "unreadable",
        "header_columns": 0,
        "header_preview": [],
    }

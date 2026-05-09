from __future__ import annotations

from datetime import timedelta

import pandas as pd

from .utils import normalize_string

FREQUENCY_MAP = {
    "QID": 4,
    "TID": 3,
    "BID": 2,
    "QD": 1,
    "QN": 1,
    "QM": 1,
    "QOD": 0.5,
    "QW": 1 / 7,
    "每日四次": 4,
    "每日三次": 3,
    "每日两次": 2,
    "每日一次": 1,
    "每天一次": 1,
    "每晚一次": 1,
    "睡前": 1,
    "间日一次": 0.5,
    "每周一次": 1 / 7,
    "PRN": 1,
    "必要时": 1,
}


def split_drug_events_by_frequency(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "frequency" not in df.columns:
        return df.copy()

    expanded: list[dict[str, object]] = []
    for row in df.to_dict(orient="records"):
        ts = row.get("timestamp")
        if pd.isna(ts):
            continue
        freq = normalize_string(row.get("frequency")).upper()
        times_per_day = FREQUENCY_MAP.get(freq)
        if times_per_day is None or times_per_day <= 1:
            expanded.append(row)
            continue
        interval_hours = 24 / times_per_day
        for step in range(int(times_per_day)):
            clone = dict(row)
            clone["timestamp"] = ts + timedelta(hours=interval_hours * step)
            expanded.append(clone)
    return pd.DataFrame(expanded if expanded else df.to_dict(orient="records"))

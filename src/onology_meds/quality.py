from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .utils import ensure_dir


VALIDATION_RULES = {
    "MEAS:FIRST_DIAGNOSIS_AGE": (0, 120, "remove"),
    "MEAS:HEIGHT": (100, 250, "remove"),
    "MEAS:WEIGHT": (30, 250, "remove"),
    "MEAS:BMI": (10, 60, "remove"),
    "MEAS:BSA": (0.5, 3.5, "remove"),
    "MEA:体温": (35.0, 42.0, "remove"),
    "(ALT)": (0, 5000, "clip"),
    "(AST)": (0, 5000, "clip"),
    "(GGT)": (0, 3000, "clip"),
    "(ALP)": (0, 3000, "clip"),
    "(TBIL)": (0, 1000, "flag"),
    "(DBIL)": (0, 800, "clip"),
    "(IBIL)": (0, 800, "clip"),
    "(CRP)": (0, 600, "clip"),
    "DNA": (0, 1e12, "clip"),
    "RNA": (0, 1e12, "clip"),
}


def validate_temporal_consistency(events: pd.DataFrame, output_dir: str | Path, current_date: str) -> pd.DataFrame:
    out_dir = ensure_dir(Path(output_dir) / "audits")
    df = events.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    cutoff = pd.to_datetime(current_date)
    future_mask = df["timestamp"] > cutoff
    if future_mask.any():
        df[future_mask].to_csv(out_dir / "future_events_removed.csv", index=False, encoding="utf-8-sig")
        df = df[~future_mask].copy()

    death_events = df[df["type"] == "Death"][["subject_id", "timestamp"]].rename(columns={"timestamp": "death_ts"})
    if not death_events.empty:
        df = df.merge(death_events, on="subject_id", how="left")
        post_death = (df["death_ts"].notna()) & (df["timestamp"] > df["death_ts"] + pd.Timedelta(days=1))
        if post_death.any():
            df[post_death].to_csv(out_dir / "post_death_events_removed.csv", index=False, encoding="utf-8-sig")
            df = df[~post_death].copy()
        df = df.drop(columns=["death_ts"])

    df = df.sort_values(["subject_id", "timestamp", "source_concept_id"]).copy()
    duplicates = df.duplicated(subset=["subject_id", "timestamp", "source_concept_id"], keep="first")
    if duplicates.any():
        df[duplicates].to_csv(out_dir / "duplicate_events_removed.csv", index=False, encoding="utf-8-sig")
        df = df[~duplicates].copy()
    return df


def clean_measurement_outliers(events: pd.DataFrame, output_dir: str | Path) -> pd.DataFrame:
    out_dir = ensure_dir(Path(output_dir) / "audits")
    df = events.copy()
    measurements = df[df["type"] == "Measurement"].copy()
    others = df[df["type"] != "Measurement"].copy()
    measurements["numeric_value"] = pd.to_numeric(measurements["numeric_value"], errors="coerce")

    details: list[pd.DataFrame] = []
    report_rows: list[dict[str, object]] = []
    for concept, (vmin, vmax, action) in VALIDATION_RULES.items():
        mask = measurements["source_concept_id"].str.contains(concept, case=False, na=False, regex=False)
        if not mask.any():
            continue
        low = mask & (measurements["numeric_value"] < vmin)
        high = mask & (measurements["numeric_value"] > vmax)
        outlier = low | high
        if not outlier.any():
            continue
        flagged = measurements[outlier].copy()
        flagged["rule"] = concept
        flagged["action"] = action
        details.append(flagged)
        report_rows.append(
            {
                "指标": concept,
                "过低数量": int(low.sum()),
                "过高数量": int(high.sum()),
                "处理动作": action,
            }
        )
        if action == "clip":
            measurements.loc[low, "numeric_value"] = vmin
            measurements.loc[high, "numeric_value"] = vmax
        elif action == "remove":
            measurements.loc[outlier, "numeric_value"] = np.nan

    if report_rows:
        pd.DataFrame(report_rows).to_csv(out_dir / "measurement_outlier_report.csv", index=False, encoding="utf-8-sig")
    if details:
        pd.concat(details, ignore_index=True).to_csv(
            out_dir / "measurement_outlier_details.csv", index=False, encoding="utf-8-sig"
        )
    return pd.concat([others, measurements], ignore_index=True).sort_values(
        ["subject_id", "timestamp", "source_concept_id"]
    )

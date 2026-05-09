from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .constants import INV_LIVER_LAB_NAMES, LIVER_LAB_NAMES, ONCOLOGY_DRUG_TAGS
from .utils import ensure_dir, normalize_string


@dataclass(slots=True)
class CohortArtifacts:
    filtered_events: pd.DataFrame
    reports: dict[str, pd.DataFrame]


def _oncology_mask(df: pd.DataFrame) -> pd.Series:
    pattern = "|".join(ONCOLOGY_DRUG_TAGS)
    return (df["type"] == "Drug") & df["source_concept_id"].str.contains(pattern, na=False)


def identify_multi_primary(events: pd.DataFrame) -> pd.DataFrame:
    conditions = events[events["type"] == "Condition"].copy()
    conditions["icd_root"] = conditions["source_concept_id"].astype(str).str.extract(r"ICD10:([A-Z]\d{2})", expand=False)
    conditions = conditions[conditions["icd_root"].str.startswith("C", na=False)]
    conditions = conditions[~conditions["icd_root"].str.startswith(tuple(["C76", "C77", "C78", "C79", "C80", "C41"]), na=False)]
    counts = conditions.groupby("subject_id")["icd_root"].nunique()
    ids = counts[counts >= 2].index
    return conditions[conditions["subject_id"].isin(ids)][["subject_id", "source_concept_id"]].drop_duplicates()


def identify_baseline_liver_injury(events: pd.DataFrame) -> pd.DataFrame:
    oncology = events[_oncology_mask(events)].copy()
    if oncology.empty:
        return pd.DataFrame(columns=["subject_id"])
    first_drug = oncology.groupby("subject_id")["timestamp"].min().rename("index_date")
    labs = events[
        (events["type"] == "Measurement")
        & (events["source_concept_id"].isin([f"MEA:{v}" for v in LIVER_LAB_NAMES.values()]))
    ].copy()
    labs = labs.merge(first_drug, on="subject_id", how="inner")
    baseline = labs[
        (labs["timestamp"] < labs["index_date"]) &
        (labs["timestamp"] >= labs["index_date"] - pd.Timedelta(days=30))
    ].copy()
    if baseline.empty:
        return pd.DataFrame(columns=["subject_id"])
    baseline["lab_name"] = baseline["source_concept_id"].str.removeprefix("MEA:").map(INV_LIVER_LAB_NAMES)
    pivot = (
        baseline.pivot_table(index=["subject_id", "timestamp"], columns="lab_name", values="numeric_value", aggfunc="mean")
        .reset_index()
        .sort_values(["subject_id", "timestamp"])
        .groupby("subject_id")
        .tail(1)
    )
    if "TBIL" not in pivot.columns:
        pivot["TBIL"] = np.nan
    pivot["TBIL"] = pivot["TBIL"].fillna(pivot.get("DBIL", 0) + pivot.get("IBIL", 0))
    mask = (
        (pivot.get("ALT", 0) >= 200)
        | ((pivot.get("ALT", 0) >= 120) & (pivot.get("TBIL", 0) >= 46))
        | ((pivot.get("ALP", 0) >= 250) & (pivot.get("GGT", 0) > 45))
    )
    return pivot[mask].copy()


def filter_followup_integrity(events: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    oncology = events[_oncology_mask(events)].copy()
    all_ids = set(events["subject_id"].astype(str).unique())
    if oncology.empty:
        return events.iloc[0:0].copy(), {
            "excluded_no_oncology_exposure": pd.DataFrame({"subject_id": sorted(all_ids)}),
        }

    exposed_ids = set(oncology["subject_id"].astype(str).unique())
    milestones = oncology.groupby("subject_id")["timestamp"].agg(index_date="min", end_date="max").reset_index()
    labs = events[
        (events["type"] == "Measurement")
        & (events["source_concept_id"] == f"MEA:{LIVER_LAB_NAMES['ALT']}")
    ].copy()
    labs = labs.merge(milestones, on="subject_id", how="inner")

    baseline_ok = set(
        labs[
            (labs["timestamp"] >= labs["index_date"] - pd.Timedelta(days=14))
            & (labs["timestamp"] < labs["index_date"])
        ]["subject_id"].astype(str).unique()
    )
    monitoring_ok = set(
        labs[
            (labs["timestamp"] >= labs["index_date"])
            & (labs["timestamp"] <= labs["end_date"])
        ].groupby("subject_id")["timestamp"].nunique()[lambda s: s >= 3].index.astype(str)
    )
    audit_window_ids = set(
        labs[
            (labs["timestamp"] >= labs["index_date"] - pd.Timedelta(days=14))
            & (labs["timestamp"] <= labs["index_date"] + pd.Timedelta(days=14))
        ]["subject_id"].astype(str).unique()
    )

    final_ids = baseline_ok & monitoring_ok
    reports = {
        "excluded_no_oncology_exposure": pd.DataFrame({"subject_id": sorted(all_ids - exposed_ids)}),
        "excluded_insufficient_baseline": pd.DataFrame({"subject_id": sorted(exposed_ids - baseline_ok)}),
        "excluded_low_monitoring_frequency": pd.DataFrame({"subject_id": sorted(exposed_ids - monitoring_ok)}),
        "audit_baseline_window_pm14": pd.DataFrame({"subject_id": sorted(exposed_ids - audit_window_ids)}),
        "final_cohort_ids": pd.DataFrame({"subject_id": sorted(final_ids)}),
    }
    return events[events["subject_id"].isin(final_ids)].copy(), reports


def run_cohort_filters(events: pd.DataFrame, output_dir: str | Path) -> CohortArtifacts:
    audits_dir = ensure_dir(Path(output_dir) / "audits")
    reports: dict[str, pd.DataFrame] = {}

    multi_primary = identify_multi_primary(events)
    reports["multi_primary_tumor_blacklist"] = multi_primary
    step1 = events[~events["subject_id"].isin(set(multi_primary["subject_id"].astype(str)))]

    baseline_injury = identify_baseline_liver_injury(step1)
    reports["baseline_liver_injury_removed_patients"] = baseline_injury
    step2 = step1[~step1["subject_id"].isin(set(baseline_injury["subject_id"].astype(str)))]

    filtered, integrity_reports = filter_followup_integrity(step2)
    reports.update(integrity_reports)

    for name, frame in reports.items():
        frame.to_csv(audits_dir / f"{name}.csv", index=False, encoding="utf-8-sig")

    return CohortArtifacts(filtered_events=filtered, reports=reports)

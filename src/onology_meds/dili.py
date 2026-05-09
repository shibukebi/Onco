from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .constants import (
    AIH_DIAGNOSIS_KEYWORDS,
    ALCOHOL_DIAGNOSIS_KEYWORDS,
    BILIARY_DIAGNOSIS_KEYWORDS,
    BILIARY_IMAGING_KEYWORDS,
    INV_LIVER_LAB_NAMES,
    ISCHEMIC_KEYWORDS,
    LIVER_LAB_NAMES,
    METABOLIC_DIAGNOSIS_KEYWORDS,
    NAFLD_DIAGNOSIS_KEYWORDS,
    ONCOLOGY_DRUG_TAGS,
    ULN_VALUES,
)
from .utils import ensure_dir, get_safe_pattern


@dataclass(slots=True)
class DiliArtifacts:
    comprehensive: pd.DataFrame
    positive_events: pd.DataFrame


def _oncology_pattern() -> str:
    return "|".join(ONCOLOGY_DRUG_TAGS)


def get_liver_measurements(events: pd.DataFrame) -> pd.DataFrame:
    return events[
        (events["type"] == "Measurement")
        & (events["source_concept_id"].isin([f"MEA:{value}" for value in LIVER_LAB_NAMES.values()]))
    ].copy()


def identify_dili_positive_events(events: pd.DataFrame) -> pd.DataFrame:
    liver = get_liver_measurements(events)
    if liver.empty:
        return pd.DataFrame()
    liver["timestamp"] = pd.to_datetime(liver["timestamp"])
    liver["lab_name"] = liver["source_concept_id"].str.removeprefix("MEA:").map(INV_LIVER_LAB_NAMES)
    pivot = (
        liver.pivot_table(index=["subject_id", "timestamp"], columns="lab_name", values="numeric_value", aggfunc="first")
        .reset_index()
    )
    if "TBIL" not in pivot.columns:
        pivot["TBIL"] = np.nan
    pivot["TBIL"] = pivot["TBIL"].fillna(pivot.get("DBIL", 0) + pivot.get("IBIL", 0))
    cond_a = pivot.get("ALT", pd.Series(index=pivot.index)) >= 200
    cond_b = (pivot.get("ALT", pd.Series(index=pivot.index)) >= 120) & (pivot["TBIL"] >= 46)
    cond_c = (pivot.get("ALP", pd.Series(index=pivot.index)) >= 250) & (pivot.get("GGT", pd.Series(index=pivot.index)) > 45)
    result = pivot[cond_a | cond_b | cond_c].copy()
    if result.empty:
        return result
    result["dili_criteria_met"] = np.select(
        [cond_a.loc[result.index], cond_b.loc[result.index], cond_c.loc[result.index]],
        ["Branch A", "Branch B", "Branch C"],
        default="Multiple",
    )
    return result


def prepare_context_data(events: pd.DataFrame) -> tuple[pd.Series, dict[str, dict[str, float]], dict[str, pd.DataFrame]]:
    oncology = events[(events["type"] == "Drug") & events["source_concept_id"].str.contains(_oncology_pattern(), na=False)]
    first_onc = oncology.groupby("subject_id")["timestamp"].min()
    liver = get_liver_measurements(events).copy()
    liver["lab_name"] = liver["source_concept_id"].str.removeprefix("MEA:").map(INV_LIVER_LAB_NAMES)

    baseline_map: dict[str, dict[str, float]] = {}
    for subject_id, group in liver.groupby("subject_id"):
        index_date = first_onc.get(subject_id, group["timestamp"].min())
        baseline = group[group["timestamp"] < index_date]
        if baseline.empty:
            baseline_map[subject_id] = dict(ULN_VALUES)
            continue
        pivot = baseline.groupby("lab_name")["numeric_value"].median().to_dict()
        payload = {key: float(pivot.get(key, ULN_VALUES.get(key, np.nan))) for key in ULN_VALUES}
        baseline_map[subject_id] = payload

    secondary = events.groupby("subject_id")
    return first_onc, baseline_map, {sid: frame.copy() for sid, frame in secondary}


def apply_ctcae_grading(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["ctcae_grade"] = 1
    grade4 = (result.get("ALT", 0) >= 20 * ULN_VALUES["ALT"]) | (result.get("AST", 0) >= 20 * ULN_VALUES["AST"])
    grade3 = (result.get("ALT", 0) >= 5 * ULN_VALUES["ALT"]) | (result.get("AST", 0) >= 5 * ULN_VALUES["AST"])
    grade2 = (result.get("ALT", 0) >= 3 * ULN_VALUES["ALT"]) | (result.get("AST", 0) >= 3 * ULN_VALUES["AST"])
    result.loc[grade2, "ctcae_grade"] = 2
    result.loc[grade3, "ctcae_grade"] = 3
    result.loc[grade4, "ctcae_grade"] = 4
    return result


def check_secondary_causes(patient_events: pd.DataFrame, dili_timestamp: pd.Timestamp, current_lfts: dict[str, object]) -> list[str]:
    window_start = dili_timestamp - pd.Timedelta(days=14)
    window_end = dili_timestamp + pd.Timedelta(days=14)
    relevant = patient_events[
        (patient_events["timestamp"] >= window_start) & (patient_events["timestamp"] <= window_end)
    ].copy()
    if relevant.empty:
        return []
    causes: list[str] = []

    if not relevant[relevant["source_concept_id"].str.contains(get_safe_pattern(BILIARY_IMAGING_KEYWORDS + BILIARY_DIAGNOSIS_KEYWORDS), case=False, na=False)].empty:
        causes.append("胆道损伤")

    virus_events = relevant[
        (relevant["type"] == "Measurement")
        & relevant["source_concept_id"].str.contains("HAV|HCV|HBV|HDV|HEV|CMV|EBV", case=False, na=False)
    ]
    if not virus_events.empty:
        positive = virus_events[
            virus_events["source_concept_id"].str.contains("阳性|DNA|RNA|IgM|Ab", case=False, na=False)
            & (
                virus_events["numeric_value"].isna()
                | (pd.to_numeric(virus_events["numeric_value"], errors="coerce") > 0)
            )
        ]
        if not positive.empty:
            causes.append("病毒性肝炎感染疑似")

    if not relevant[relevant["source_concept_id"].str.contains(get_safe_pattern(AIH_DIAGNOSIS_KEYWORDS), case=False, na=False)].empty:
        causes.append("自身免疫性肝病")
    if not relevant[relevant["source_concept_id"].str.contains("肝转移", case=False, na=False)].empty:
        causes.append("肝转移继发肝损")
    if not relevant[relevant["source_concept_id"].str.contains(get_safe_pattern(ALCOHOL_DIAGNOSIS_KEYWORDS), case=False, na=False)].empty:
        causes.append("酒精性肝病")
    if not relevant[relevant["source_concept_id"].str.contains(get_safe_pattern(METABOLIC_DIAGNOSIS_KEYWORDS), case=False, na=False)].empty:
        causes.append("代谢性肝病")
    if not relevant[relevant["source_concept_id"].str.contains(get_safe_pattern(ISCHEMIC_KEYWORDS), case=False, na=False)].empty:
        causes.append("缺血性肝病")
    if not relevant[relevant["source_concept_id"].str.contains(get_safe_pattern(NAFLD_DIAGNOSIS_KEYWORDS), case=False, na=False)].empty:
        causes.append("NAFLD")

    ast = current_lfts.get("AST")
    alt = current_lfts.get("ALT")
    ggt = current_lfts.get("GGT")
    mcv = relevant[relevant["source_concept_id"].str.contains("MCV", case=False, na=False)]["numeric_value"].mean()
    if pd.notna(ast) and pd.notna(alt) and pd.notna(ggt) and pd.notna(mcv) and alt:
        if (ast / alt > 2) and (ggt > 45) and (mcv > 100):
            causes.append("酒精性肝病")

    return sorted(set(causes))


def run_dili_pipeline(events: pd.DataFrame, imaging_sidecar: pd.DataFrame, output_dir: str | Path) -> DiliArtifacts:
    dili_dir = ensure_dir(Path(output_dir) / "dili")
    all_events = pd.concat([events.copy(), imaging_sidecar.copy()], ignore_index=True)
    all_events["timestamp"] = pd.to_datetime(all_events["timestamp"], errors="coerce")
    positive = identify_dili_positive_events(all_events)
    if positive.empty:
        positive.to_csv(dili_dir / "dili_positive_events.csv", index=False, encoding="utf-8-sig")
        return DiliArtifacts(comprehensive=positive, positive_events=positive)

    first_onc, baseline_map, grouped = prepare_context_data(all_events)
    positive["earliest_oncology_drug_exposure"] = positive["subject_id"].map(first_onc)
    for lab in ["ALT", "AST", "ALP", "TBIL", "GGT"]:
        positive[f"baseline_{lab}"] = positive["subject_id"].map(lambda sid: baseline_map.get(sid, {}).get(lab, ULN_VALUES.get(lab)))
    positive["first_dili_timestamp"] = positive.groupby("subject_id")["timestamp"].transform("min")
    positive["dili_period"] = np.where(
        (positive["timestamp"] - positive["first_dili_timestamp"]).dt.days > 180,
        "Chronic",
        "Acute",
    )
    positive = apply_ctcae_grading(positive)
    positive["R_value"] = (positive["ALT"] / ULN_VALUES["ALT"]) / (positive["ALP"] / ULN_VALUES["ALP"])
    positive["secondary_cause"] = ""
    positive["dili_type"] = "Unknown"

    for idx, row in positive.iterrows():
        sid = row["subject_id"]
        causes = check_secondary_causes(grouped.get(sid, pd.DataFrame(columns=all_events.columns)), row["timestamp"], row.to_dict())
        if causes:
            positive.at[idx, "secondary_cause"] = "; ".join(causes)
            positive.at[idx, "dili_type"] = "SECONDARY_CAUSES_EXCLUDED"
        else:
            r_value = row["R_value"]
            positive.at[idx, "dili_type"] = "CHOLESTATIC" if r_value <= 2 else ("HEPATOCELLULAR" if r_value >= 5 else "MIXED")

    positive.to_csv(dili_dir / "dili_positive_events.csv", index=False, encoding="utf-8-sig")
    positive.to_csv(dili_dir / "dili_comprehensive_results.csv", index=False, encoding="utf-8-sig")
    return DiliArtifacts(comprehensive=positive, positive_events=positive)

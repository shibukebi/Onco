from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from .constants import DEFAULT_CONCEPT_DICTIONARY_DIR, DEFAULT_MEDS_DIR
from .standardize_sample import ConceptMapper
from .utils import normalize_string, stable_unique


VISIT_START_TOKEN = "[VS]"
VISIT_END_TOKEN = "[VE]"


def att_token(delta_days: int) -> str:
    days = max(int(delta_days), 0)
    if days < 28:
        return f"W_{min(days // 7, 3)}"
    if days <= 365:
        month_bucket = max(1, min(days // 30, 11))
        return f"M_{month_bucket}"
    return "LT"


def _default_output_path(meds_dir: Path, limit: int | None) -> Path:
    if limit and limit > 0:
        return meds_dir / f"cehrbert_temporalized_{limit}_patients.jsonl"
    return meds_dir / "cehrbert_temporalized_all_patients.jsonl"


def _load_subject_ids(events_path: Path, limit: int | None) -> list[str]:
    con = duckdb.connect()
    if limit and limit > 0:
        query = """
        SELECT subject_id
        FROM read_parquet(?)
        GROUP BY subject_id
        ORDER BY min(timestamp), subject_id
        LIMIT ?
        """
        params: list[object] = [str(events_path), int(limit)]
    else:
        query = """
        SELECT subject_id
        FROM read_parquet(?)
        GROUP BY subject_id
        ORDER BY min(timestamp), subject_id
        """
        params = [str(events_path)]
    try:
        df = con.execute(query, params).df()
    finally:
        con.close()
    return df["subject_id"].astype(str).tolist()


def _load_subject_splits(meds_dir: Path) -> dict[str, str]:
    splits_path = meds_dir / "metadata" / "subject_splits.parquet"
    if not splits_path.exists():
        return {}
    con = duckdb.connect()
    try:
        df = con.execute(
            "SELECT subject_id, split FROM read_parquet(?)",
            [str(splits_path)],
        ).df()
    finally:
        con.close()
    return {
        normalize_string(row["subject_id"]): normalize_string(row["split"])
        for _, row in df.iterrows()
    }


def _load_selected_events(events_path: Path, subject_ids: list[str]) -> pd.DataFrame:
    con = duckdb.connect()
    try:
        if subject_ids:
            subject_df = pd.DataFrame({"subject_id": subject_ids})
            con.register("selected_subject_ids", subject_df)
            df = con.execute(
                """
                SELECT e.*
                FROM read_parquet(?) AS e
                JOIN selected_subject_ids AS s
                  ON e.subject_id = s.subject_id
                ORDER BY e.subject_id, e.timestamp, e.type, e.source_concept_id
                """,
                [str(events_path)],
            ).df()
        else:
            df = con.execute(
                """
                SELECT *
                FROM read_parquet(?)
                ORDER BY subject_id, timestamp, type, source_concept_id
                """,
                [str(events_path)],
            ).df()
    finally:
        con.close()
    return df


def _attach_standard_terms(events_df: pd.DataFrame, mapper: ConceptMapper) -> pd.DataFrame:
    concept_df = events_df[["type", "source_concept_id"]].drop_duplicates().reset_index(drop=True)
    mapped_df = concept_df.apply(
        lambda row: mapper.map_row(
            event_type=normalize_string(row["type"]),
            source_concept_id=normalize_string(row["source_concept_id"]),
        ),
        axis=1,
        result_type="expand",
    )
    lookup_df = pd.concat([concept_df, mapped_df], axis=1)
    return events_df.merge(lookup_df, on=["type", "source_concept_id"], how="left")


def build_patient_sequence_rows(
    events_df: pd.DataFrame,
    split_map: dict[str, str] | None = None,
    deduplicate_within_visit: bool = True,
) -> list[dict[str, object]]:
    split_map = split_map or {}
    if events_df.empty:
        return []

    working = events_df.copy()
    working["subject_id"] = working["subject_id"].astype(str)
    working["timestamp"] = working["timestamp"].astype(str)
    working["_timestamp_dt"] = pd.to_datetime(working["timestamp"], errors="coerce")
    working = working.sort_values(
        ["subject_id", "_timestamp_dt", "timestamp", "type", "source_concept_id"],
        kind="stable",
    )

    patients: list[dict[str, object]] = []
    for subject_id, patient_df in working.groupby("subject_id", sort=False):
        visits: list[dict[str, object]] = []
        source_sequence_tokens: list[str] = []
        standardized_source_sequence_tokens: list[str] = []
        standard_term_sequence_tokens: list[str] = []
        previous_timestamp: pd.Timestamp | None = None

        for visit_index, (timestamp, visit_df) in enumerate(patient_df.groupby("timestamp", sort=False), start=1):
            timestamp_dt = visit_df["_timestamp_dt"].iloc[0]
            if previous_timestamp is not None and pd.notna(timestamp_dt):
                delta_days = int((timestamp_dt - previous_timestamp).total_seconds() // 86400)
                token = att_token(delta_days)
                source_sequence_tokens.append(token)
                standardized_source_sequence_tokens.append(token)
                standard_term_sequence_tokens.append(token)
                att_from_previous = token
            else:
                att_from_previous = None

            source_concepts = visit_df["source_concept_id"].astype(str).tolist()
            standardized_source_concepts = visit_df["standardized_source_concept_id"].astype(str).tolist()
            standard_terms = visit_df["standard_term_en"].astype(str).tolist()
            if deduplicate_within_visit:
                source_concepts = stable_unique(source_concepts)
                standardized_source_concepts = stable_unique(standardized_source_concepts)
                standard_terms = stable_unique(standard_terms)

            source_sequence_tokens.extend([VISIT_START_TOKEN, *source_concepts, VISIT_END_TOKEN])
            standardized_source_sequence_tokens.extend(
                [VISIT_START_TOKEN, *standardized_source_concepts, VISIT_END_TOKEN]
            )
            standard_term_sequence_tokens.extend([VISIT_START_TOKEN, *standard_terms, VISIT_END_TOKEN])

            visits.append(
                {
                    "visit_index": visit_index,
                    "timestamp": normalize_string(timestamp),
                    "att_from_previous": att_from_previous,
                    "event_count": int(len(visit_df)),
                    "source_concepts": source_concepts,
                    "standardized_source_concepts": standardized_source_concepts,
                    "standard_terms_en": standard_terms,
                }
            )

            if pd.notna(timestamp_dt):
                previous_timestamp = timestamp_dt

        patients.append(
            {
                "subject_id": subject_id,
                "split": split_map.get(subject_id, ""),
                "visit_count": len(visits),
                "event_count": int(len(patient_df)),
                "sequence_source_tokens": source_sequence_tokens,
                "sequence_source_text": " ".join(source_sequence_tokens),
                "sequence_standardized_source_tokens": standardized_source_sequence_tokens,
                "sequence_standardized_source_text": " ".join(standardized_source_sequence_tokens),
                "sequence_standard_term_tokens": standard_term_sequence_tokens,
                "sequence_standard_term_text": " ".join(standard_term_sequence_tokens),
                "visits": visits,
            }
        )
    return patients


def export_cehrbert_sequences(
    meds_dir: str | Path = DEFAULT_MEDS_DIR,
    dictionary_dir: str | Path = DEFAULT_CONCEPT_DICTIONARY_DIR,
    limit: int = 10,
    output_path: str | Path | None = None,
) -> dict[str, object]:
    meds_dir = Path(meds_dir)
    events_path = meds_dir / "events.parquet"
    if output_path is None:
        output_path = _default_output_path(meds_dir, limit)
    output_path = Path(output_path)
    summary_path = output_path.with_suffix(".summary.json")

    subject_ids = _load_subject_ids(events_path, limit if limit > 0 else None)
    events_df = _load_selected_events(events_path, subject_ids)
    mapper = ConceptMapper.load(dictionary_dir)
    mapped_events = _attach_standard_terms(events_df, mapper)
    split_map = _load_subject_splits(meds_dir)
    patient_rows = build_patient_sequence_rows(mapped_events, split_map=split_map)

    with output_path.open("w", encoding="utf-8") as fh:
        for row in patient_rows:
            fh.write(json.dumps(row, ensure_ascii=False))
            fh.write("\n")

    summary = {
        "meds_dir": str(meds_dir),
        "dictionary_dir": str(dictionary_dir),
        "patient_count": len(patient_rows),
        "selected_patient_ids": subject_ids,
        "event_count": int(len(mapped_events)),
        "visit_count": int(sum(row["visit_count"] for row in patient_rows)),
        "output_path": str(output_path),
        "deduplicate_within_visit": True,
        "mapping_status_counts": mapped_events["mapping_status"].value_counts(dropna=False).to_dict(),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from .constants import DEFAULT_CONCEPT_DICTIONARY_DIR, DEFAULT_MEDS_DIR
from .standardize_sample import ConceptMapper
from .utils import normalize_string


DOMAIN_FILE_MAP = {
    "Condition": "condition.json",
    "Drug": "drug.json",
    "Measurement": "measurement.json",
    "Observation": "obs.json",
    "Procedure": "procedure.json",
}


def _prepare_review_columns(df: pd.DataFrame) -> pd.DataFrame:
    prepared = df.copy()
    prepared["target_dictionary_file"] = prepared["mapping_domain"].map(DOMAIN_FILE_MAP).fillna("")
    prepared["dictionary_concept_name_cn"] = prepared["lookup_key_cn"].fillna("")
    prepared["proposed_concept_name"] = ""
    prepared["proposed_concept_id"] = ""
    prepared["proposed_match_status"] = ""
    prepared["review_notes"] = ""
    return prepared


def build_fallback_candidates(
    meds_dir: str | Path = DEFAULT_MEDS_DIR,
    dictionary_dir: str | Path = DEFAULT_CONCEPT_DICTIONARY_DIR,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    meds_dir = Path(meds_dir)
    events_path = meds_dir / "events.parquet"

    con = duckdb.connect()
    try:
        concepts_df = con.execute(
            """
            SELECT
              type,
              source_concept_id,
              count(*) AS event_count,
              count(DISTINCT subject_id) AS subject_count,
              min(timestamp) AS first_timestamp,
              max(timestamp) AS last_timestamp
            FROM read_parquet(?)
            GROUP BY 1, 2
            ORDER BY event_count DESC, type, source_concept_id
            """,
            [str(events_path)],
        ).df()
    finally:
        con.close()

    mapper = ConceptMapper.load(dictionary_dir)
    mapped = concepts_df.apply(
        lambda row: mapper.map_row(
            event_type=normalize_string(row["type"]),
            source_concept_id=normalize_string(row["source_concept_id"]),
        ),
        axis=1,
        result_type="expand",
    )
    enriched = pd.concat([concepts_df, mapped], axis=1)

    fallback_by_source = (
        enriched[enriched["mapping_status"] == "fallback_rule"]
        .copy()
        .sort_values(["event_count", "subject_count", "type", "source_concept_id"], ascending=[False, False, True, True])
        .reset_index(drop=True)
    )
    if fallback_by_source.empty:
        fallback_by_lookup = fallback_by_source.copy()
    else:
        fallback_by_lookup = (
            fallback_by_source.groupby(
                ["mapping_domain", "type", "lookup_key_cn", "standard_term_en", "mapping_status"],
                dropna=False,
                as_index=False,
            )
            .agg(
                source_concept_count=("source_concept_id", "nunique"),
                total_event_count=("event_count", "sum"),
                total_subject_count=("subject_count", "sum"),
                example_source_concept_id=("source_concept_id", "first"),
                first_timestamp=("first_timestamp", "min"),
                last_timestamp=("last_timestamp", "max"),
            )
            .sort_values(
                ["total_event_count", "total_subject_count", "type", "lookup_key_cn"],
                ascending=[False, False, True, True],
            )
            .reset_index(drop=True)
        )

    fallback_by_source = _prepare_review_columns(fallback_by_source)
    fallback_by_lookup = _prepare_review_columns(fallback_by_lookup)
    return fallback_by_source, fallback_by_lookup


def export_fallback_candidates_csv(
    meds_dir: str | Path = DEFAULT_MEDS_DIR,
    dictionary_dir: str | Path = DEFAULT_CONCEPT_DICTIONARY_DIR,
    output_dir: str | Path | None = None,
) -> dict[str, object]:
    meds_dir = Path(meds_dir)
    output_dir = Path(output_dir) if output_dir else meds_dir
    by_source_path = output_dir / "fallback_rule_candidates_by_source.csv"
    by_lookup_path = output_dir / "fallback_rule_candidates_by_lookup.csv"
    summary_path = output_dir / "fallback_rule_candidates.summary.json"

    fallback_by_source, fallback_by_lookup = build_fallback_candidates(meds_dir, dictionary_dir)
    fallback_by_source.to_csv(by_source_path, index=False, encoding="utf-8-sig")
    fallback_by_lookup.to_csv(by_lookup_path, index=False, encoding="utf-8-sig")

    summary = {
        "meds_dir": str(meds_dir),
        "dictionary_dir": str(dictionary_dir),
        "fallback_source_rows": int(len(fallback_by_source)),
        "fallback_lookup_rows": int(len(fallback_by_lookup)),
        "by_source_path": str(by_source_path),
        "by_lookup_path": str(by_lookup_path),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary

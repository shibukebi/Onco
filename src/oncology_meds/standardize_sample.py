from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd

from .constants import DEFAULT_CONCEPT_DICTIONARY_DIR, DEFAULT_MEDS_DIR
from .utils import normalize_string


DOMAIN_FILE_MAP = {
    "Condition": "condition.json",
    "Drug": "drug.json",
    "Measurement": "measurement.json",
    "Observation": "obs.json",
    "Procedure": "procedure.json",
}

YES_NO_MAP = {
    "是": "Yes",
    "否": "No",
    "YES": "Yes",
    "NO": "No",
}


def _normalize_lookup_key(text: str) -> str:
    return re.sub(r"\s+", "", normalize_string(text)).lower()


@dataclass(slots=True)
class DictionaryEntry:
    concept_id: str
    concept_name: str
    concept_name_cn: str
    domain: str
    omop_concept_name: str
    omop_match_status: str


@dataclass(slots=True)
class DomainDictionary:
    exact_cn: dict[str, DictionaryEntry]
    normalized_cn: dict[str, DictionaryEntry]

    @classmethod
    def load(cls, path: str | Path) -> "DomainDictionary":
        payload = json.loads(Path(path).read_text())
        exact_cn: dict[str, DictionaryEntry] = {}
        normalized_cn: dict[str, DictionaryEntry] = {}
        for item in payload.get("concepts", []):
            entry = DictionaryEntry(
                concept_id=normalize_string(item.get("concept_id")),
                concept_name=normalize_string(item.get("concept_name")),
                concept_name_cn=normalize_string(item.get("concept_name_cn")),
                domain=normalize_string(item.get("domain")),
                omop_concept_name=normalize_string(item.get("omop_concept_name")),
                omop_match_status=normalize_string(item.get("omop_match_status")),
            )
            if entry.concept_name_cn and entry.concept_name_cn not in exact_cn:
                exact_cn[entry.concept_name_cn] = entry
            if entry.concept_name_cn:
                key = _normalize_lookup_key(entry.concept_name_cn)
                if key and key not in normalized_cn:
                    normalized_cn[key] = entry
        return cls(exact_cn=exact_cn, normalized_cn=normalized_cn)

    def match(self, chinese_term: str) -> DictionaryEntry | None:
        key = normalize_string(chinese_term)
        if not key:
            return None
        if key in self.exact_cn:
            return self.exact_cn[key]
        return self.normalized_cn.get(_normalize_lookup_key(key))


@dataclass(slots=True)
class ConceptMapper:
    by_type: dict[str, DomainDictionary]

    @classmethod
    def load(cls, dictionary_dir: str | Path) -> "ConceptMapper":
        base = Path(dictionary_dir)
        by_type = {
            event_type: DomainDictionary.load(base / filename)
            for event_type, filename in DOMAIN_FILE_MAP.items()
        }
        return cls(by_type=by_type)

    def parse_lookup_key(self, event_type: str, source_concept_id: str) -> str:
        source = normalize_string(source_concept_id)
        if event_type == "Condition" and source.startswith("ICD10:"):
            return source.removeprefix("ICD10:")
        if event_type == "Drug" and source.startswith("DRUG:"):
            return re.sub(r":\[[^\]]*\]$", "", source.removeprefix("DRUG:"))
        if event_type == "Measurement":
            if source.startswith("MEA:"):
                return source.removeprefix("MEA:")
            if source.startswith("MEAS:"):
                return source.removeprefix("MEAS:")
        if event_type == "Observation" and source.startswith("OBS:"):
            return source.removeprefix("OBS:")
        if event_type == "Procedure" and source.startswith("PROCEDURE:"):
            return source.removeprefix("PROCEDURE:")
        return source

    def fallback_term(self, event_type: str, lookup_key: str) -> str:
        if event_type == "Observation":
            parts = lookup_key.split(":")
            if len(parts) == 2 and parts[1] in YES_NO_MAP:
                left = parts[0].replace("_", " ").title()
                return f"{left}: {YES_NO_MAP[parts[1]]}"
        if event_type == "Measurement":
            return lookup_key.replace("_", " ").title()
        return lookup_key

    def standardized_source_concept(self, event_type: str, source_concept_id: str, standard_term_en: str) -> str:
        source = normalize_string(source_concept_id)
        if event_type == "Condition" and source.startswith("ICD10:"):
            code = source.removeprefix("ICD10:").split(":", 1)[0]
            return f"ICD10:{code}:{standard_term_en}"
        if event_type == "Drug" and source.startswith("DRUG:"):
            tag_suffix = ""
            m = re.search(r"(:\[[^\]]*\])$", source)
            if m:
                tag_suffix = m.group(1)
            return f"DRUG:{standard_term_en}{tag_suffix}"
        if event_type == "Measurement":
            prefix = "MEA:" if source.startswith("MEA:") else ("MEAS:" if source.startswith("MEAS:") else "")
            return f"{prefix}{standard_term_en}" if prefix else standard_term_en
        if event_type == "Observation" and source.startswith("OBS:"):
            return f"OBS:{standard_term_en}"
        if event_type == "Procedure" and source.startswith("PROCEDURE:"):
            return f"PROCEDURE:{standard_term_en}"
        return standard_term_en

    def map_row(self, event_type: str, source_concept_id: str) -> dict[str, str]:
        lookup_key = self.parse_lookup_key(event_type, source_concept_id)
        dictionary = self.by_type.get(event_type)
        entry = dictionary.match(lookup_key) if dictionary else None
        if entry is not None and entry.concept_name:
            standard_term_en = entry.concept_name
            mapping_status = entry.omop_match_status or "dictionary"
            matched_cn = entry.concept_name_cn
        else:
            standard_term_en = self.fallback_term(event_type, lookup_key)
            mapping_status = "fallback_rule"
            matched_cn = ""
        standardized_source = self.standardized_source_concept(
            event_type=event_type,
            source_concept_id=source_concept_id,
            standard_term_en=standard_term_en,
        )
        return {
            "mapping_domain": event_type,
            "lookup_key_cn": lookup_key,
            "matched_concept_name_cn": matched_cn,
            "standard_term_en": standard_term_en,
            "standardized_source_concept_id": standardized_source,
            "mapping_status": mapping_status,
        }


def export_standardized_patient_sample(
    meds_dir: str | Path = DEFAULT_MEDS_DIR,
    dictionary_dir: str | Path = DEFAULT_CONCEPT_DICTIONARY_DIR,
    limit: int = 10,
    output_path: str | Path | None = None,
) -> dict[str, object]:
    meds_dir = Path(meds_dir)
    dictionary_dir = Path(dictionary_dir)
    events_path = meds_dir / "events.parquet"
    if output_path is None:
        output_path = meds_dir / f"standardized_{limit}_patients.csv"
    output_path = Path(output_path)
    summary_path = output_path.with_suffix(".summary.json")

    con = duckdb.connect()
    patient_ids_df = con.execute(
        """
        SELECT subject_id
        FROM read_parquet(?)
        GROUP BY subject_id
        ORDER BY min(timestamp), subject_id
        LIMIT ?
        """,
        [str(events_path), limit],
    ).df()
    patient_ids = patient_ids_df["subject_id"].astype(str).tolist()

    ids_df = pd.DataFrame({"subject_id": patient_ids})
    con.register("sample_ids", ids_df)
    sample_df = con.execute(
        """
        SELECT e.*
        FROM read_parquet(?) AS e
        JOIN sample_ids AS s
          ON e.subject_id = s.subject_id
        ORDER BY e.subject_id, e.timestamp, e.type, e.source_concept_id
        """,
        [str(events_path)],
    ).df()

    mapper = ConceptMapper.load(dictionary_dir)
    mapped = sample_df.apply(
        lambda row: mapper.map_row(
            event_type=normalize_string(row["type"]),
            source_concept_id=normalize_string(row["source_concept_id"]),
        ),
        axis=1,
        result_type="expand",
    )
    output_df = pd.concat([sample_df, mapped], axis=1)
    output_df.to_csv(output_path, index=False, encoding="utf-8-sig")

    summary = {
        "meds_dir": str(meds_dir),
        "dictionary_dir": str(dictionary_dir),
        "selected_patient_ids": patient_ids,
        "patient_count": len(patient_ids),
        "event_count": int(len(output_df)),
        "output_path": str(output_path),
        "mapping_status_counts": output_df["mapping_status"].value_counts(dropna=False).to_dict(),
        "type_counts": output_df["type"].value_counts(dropna=False).to_dict(),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary

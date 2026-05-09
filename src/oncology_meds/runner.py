from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pandas as pd

from .cohort import run_cohort_filters
from .config import PipelinePaths
from .constants import MEDS_CORE_COLUMNS
from .dili import run_dili_pipeline
from .exporters import export_meds_dataset
from .io import sniff_csv_summary
from .pipeline import build_events, core_meds_view
from .quality import clean_measurement_outliers, validate_temporal_consistency
from .utils import dump_json, ensure_dir


def inspect_sources(paths: PipelinePaths) -> dict[str, object]:
    table_summaries = []
    for csv_path in sorted(paths.input_dir.glob("*.csv")):
        summary = sniff_csv_summary(csv_path)
        summary["size_bytes"] = csv_path.stat().st_size
        table_summaries.append(summary)
    summary = {
        "input_dir": str(paths.input_dir),
        "resource_dir": str(paths.resource_dir),
        "output_dir": str(paths.output_dir),
        "tables": table_summaries,
    }
    logs_dir = ensure_dir(Path(paths.output_dir) / "logs")
    dump_json(summary, logs_dir / "inspect_summary.json")
    return summary


def build_meds(paths: PipelinePaths) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    artifacts = build_events(paths)
    out_dir = ensure_dir(paths.output_dir)
    logs_dir = ensure_dir(out_dir / "logs")
    if not artifacts.imaging_sidecar.empty:
        artifacts.imaging_sidecar.to_csv(
            out_dir / "excluded_imaging_observations.csv",
            index=False,
            encoding="utf-8-sig",
        )

    events = validate_temporal_consistency(artifacts.events, out_dir, current_date="2026-05-08")
    events = clean_measurement_outliers(events, out_dir)
    dump_json({"tables": artifacts.table_summaries}, logs_dir / "build_summary.json")
    return events, artifacts.imaging_sidecar, {"tables": artifacts.table_summaries}


def filter_cohort(paths: PipelinePaths) -> tuple[pd.DataFrame, pd.DataFrame]:
    events, imaging, _ = build_meds(paths)
    cohort = run_cohort_filters(events, paths.output_dir)
    return cohort.filtered_events, imaging


def run_all(paths: PipelinePaths) -> dict[str, object]:
    events, imaging, build_summary = build_meds(paths)
    cohort = run_cohort_filters(events, paths.output_dir)
    filtered = cohort.filtered_events.copy()
    filtered["timestamp"] = pd.to_datetime(filtered["timestamp"], errors="coerce")
    imaging["timestamp"] = pd.to_datetime(imaging["timestamp"], errors="coerce")

    dili = run_dili_pipeline(filtered, imaging, paths.output_dir)
    core = core_meds_view(filtered)
    metadata = export_meds_dataset(core[MEDS_CORE_COLUMNS], paths.output_dir, paths.seed)
    manifest = {
        "input_dir": str(paths.input_dir),
        "resource_dir": str(paths.resource_dir),
        "output_dir": str(paths.output_dir),
        "seed": paths.seed,
        "event_count": int(len(core)),
        "subject_count": int(core["subject_id"].nunique()),
        "dili_event_count": int(len(dili.comprehensive)),
        "tables": build_summary["tables"],
        "dataset_metadata": metadata,
    }
    dump_json(manifest, ensure_dir(Path(paths.output_dir) / "logs") / "run_manifest.json")
    return manifest

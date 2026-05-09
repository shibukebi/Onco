from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import PipelinePaths
from .cehrbert_export import export_cehrbert_sequences
from .constants import (
    DEFAULT_CONCEPT_DICTIONARY_DIR,
    DEFAULT_INPUT_DIR,
    DEFAULT_MEDS_DIR,
    DEFAULT_RESOURCE_DIR,
    DEFAULT_SEED,
)
from .fallback_dictionary_export import export_fallback_candidates_csv
from .runner import build_meds, filter_cohort, inspect_sources, run_all
from .standardize_sample import export_standardized_patient_sample


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="onology-meds")
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR)
    parser.add_argument("--resource-dir", default=DEFAULT_RESOURCE_DIR)
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--seed", default=DEFAULT_SEED, type=int)

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("inspect")
    subparsers.add_parser("build-meds")
    subparsers.add_parser("filter-cohort")
    subparsers.add_parser("run-dili")
    subparsers.add_parser("run-all")
    standardize_parser = subparsers.add_parser("export-standardized-sample")
    standardize_parser.add_argument("--meds-dir", default=DEFAULT_MEDS_DIR)
    standardize_parser.add_argument("--dictionary-dir", default=DEFAULT_CONCEPT_DICTIONARY_DIR)
    standardize_parser.add_argument("--limit", type=int, default=10)
    standardize_parser.add_argument("--sample-output-path", default=None)
    cehrbert_parser = subparsers.add_parser("export-cehrbert-sequences")
    cehrbert_parser.add_argument("--meds-dir", default=DEFAULT_MEDS_DIR)
    cehrbert_parser.add_argument("--dictionary-dir", default=DEFAULT_CONCEPT_DICTIONARY_DIR)
    cehrbert_parser.add_argument("--limit", type=int, default=10)
    cehrbert_parser.add_argument("--output-path", default=None)
    fallback_parser = subparsers.add_parser("export-fallback-candidates")
    fallback_parser.add_argument("--meds-dir", default=DEFAULT_MEDS_DIR)
    fallback_parser.add_argument("--dictionary-dir", default=DEFAULT_CONCEPT_DICTIONARY_DIR)
    fallback_parser.add_argument("--output-dir", default=None)
    return parser


def _paths(args: argparse.Namespace) -> PipelinePaths:
    return PipelinePaths(
        input_dir=Path(args.input_dir),
        resource_dir=Path(args.resource_dir),
        output_dir=Path(args.output_dir) if args.output_dir else None,
        seed=args.seed,
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    paths = _paths(args)

    if args.command == "inspect":
        payload = inspect_sources(paths)
    elif args.command == "build-meds":
        events, imaging, summary = build_meds(paths)
        payload = {
            "events": len(events),
            "subjects": int(events["subject_id"].nunique()) if not events.empty else 0,
            "imaging_rows": len(imaging),
            "tables": summary["tables"],
        }
    elif args.command == "filter-cohort":
        events, imaging = filter_cohort(paths)
        payload = {
            "events": len(events),
            "subjects": int(events["subject_id"].nunique()) if not events.empty else 0,
            "imaging_rows": len(imaging),
        }
    elif args.command == "run-dili":
        events, imaging = filter_cohort(paths)
        from .dili import run_dili_pipeline

        dili = run_dili_pipeline(events, imaging, paths.output_dir)
        payload = {"dili_events": len(dili.comprehensive)}
    elif args.command == "export-standardized-sample":
        payload = export_standardized_patient_sample(
            meds_dir=args.meds_dir,
            dictionary_dir=args.dictionary_dir,
            limit=args.limit,
            output_path=args.sample_output_path,
        )
    elif args.command == "export-cehrbert-sequences":
        payload = export_cehrbert_sequences(
            meds_dir=args.meds_dir,
            dictionary_dir=args.dictionary_dir,
            limit=args.limit,
            output_path=args.output_path,
        )
    elif args.command == "export-fallback-candidates":
        payload = export_fallback_candidates_csv(
            meds_dir=args.meds_dir,
            dictionary_dir=args.dictionary_dir,
            output_dir=args.output_dir,
        )
    else:
        payload = run_all(paths)

    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

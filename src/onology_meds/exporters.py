from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .constants import MEDS_CORE_COLUMNS
from .parquet_io import write_parquet
from .utils import dump_json, ensure_dir


def build_subject_splits(subject_ids: pd.Series, seed: int) -> pd.DataFrame:
    ids = pd.Series(sorted(subject_ids.astype(str).unique()))
    rng = np.random.default_rng(seed)
    shuffled = ids.iloc[rng.permutation(len(ids))].reset_index(drop=True)
    n = len(shuffled)
    train_end = int(n * 0.70)
    tuning_end = train_end + int(n * 0.15)
    split = np.where(
        shuffled.index < train_end,
        "train",
        np.where(shuffled.index < tuning_end, "tuning", "held_out"),
    )
    return pd.DataFrame({"subject_id": shuffled, "split": split})


def export_meds_dataset(events_core: pd.DataFrame, output_dir: str | Path, seed: int) -> dict[str, object]:
    out = ensure_dir(output_dir)
    metadata_dir = ensure_dir(Path(output_dir) / "metadata")

    write_parquet(events_core, out / "events.parquet")

    codes = events_core[["source_concept_id"]].drop_duplicates().reset_index(drop=True)
    codes["concept_id"] = codes.index + 1
    codes = codes[["concept_id", "source_concept_id"]]
    write_parquet(codes, metadata_dir / "codes.parquet")

    splits = build_subject_splits(events_core["subject_id"], seed=seed)
    write_parquet(splits, metadata_dir / "subject_splits.parquet")

    dataset_metadata = {
        "num_subjects": int(events_core["subject_id"].nunique()),
        "num_events": int(len(events_core)),
        "num_concepts": int(len(codes)),
        "creation_date": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
        "description": "Custom MEDS dataset for CEHR-BERT, rebuilt from modular pipeline.",
    }
    dump_json(dataset_metadata, metadata_dir / "dataset.json")
    return dataset_metadata

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd


def write_parquet(df: pd.DataFrame, path: str | Path) -> None:
    target = str(Path(path))
    relation = duckdb.from_df(df.reset_index(drop=True))
    relation.write_parquet(target)

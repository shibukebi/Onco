from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from onology_meds.io import deduplicate_headers, read_raw_table


def write_fixture(path: Path, rows: list[list[str]], encoding: str = "utf-8-sig") -> None:
    text = "\n".join(",".join(row) for row in rows)
    path.write_text(text, encoding=encoding)


class TestIO(unittest.TestCase):
    def test_deduplicate_headers(self) -> None:
        headers = deduplicate_headers(["a", "a", "", "b"])
        self.assertEqual(headers, ["a", "a_1", "empty_column", "b"])

    def test_read_raw_table_double_header_utf8sig(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "thyroid.csv"
            write_fixture(
                path,
                [
                    ["固定列信息", "", ""],
                    ["patient_sn", "检验日期", "检验定量结果"],
                    ["patient_sn", "test_time", "test_result"],
                    ["p1", "2022/7/4 8:05", "5.19"],
                ],
                encoding="utf-8-sig",
            )
            df, encoding = read_raw_table(path)
            self.assertEqual(encoding, "utf-8-sig")
            self.assertEqual(list(df.columns), ["patient_sn", "检验日期", "检验定量结果"])
            self.assertEqual(df.iloc[0]["patient_sn"], "p1")


if __name__ == "__main__":
    unittest.main()

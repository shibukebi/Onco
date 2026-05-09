from __future__ import annotations

import unittest

import pandas as pd

from onology_meds.drug_labels import is_index_therapy
from onology_meds.frequency import split_drug_events_by_frequency


class TestDrugUtilities(unittest.TestCase):
    def test_frequency_split_qid(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "subject_id": "p1",
                    "timestamp": pd.Timestamp("2022-01-01 00:00:00"),
                    "frequency": "QID",
                    "source_concept_id": "DRUG:test",
                }
            ]
        )
        out = split_drug_events_by_frequency(df)
        self.assertEqual(len(out), 4)
        self.assertEqual(out["timestamp"].iloc[1], pd.Timestamp("2022-01-01 06:00:00"))

    def test_is_index_therapy(self) -> None:
        self.assertTrue(is_index_therapy(["CHEMO"]))
        self.assertFalse(is_index_therapy(["SUPPORTIVE"]))


if __name__ == "__main__":
    unittest.main()

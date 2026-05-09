from __future__ import annotations

import unittest

import pandas as pd

from onology_meds.cohort import identify_baseline_liver_injury
from onology_meds.dili import identify_dili_positive_events


class TestCohortAndDili(unittest.TestCase):
    def test_baseline_liver_injury_threshold(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "subject_id": "p1",
                    "timestamp": pd.Timestamp("2022-01-10"),
                    "type": "Drug",
                    "source_concept_id": "DRUG:x:[CHEMO]",
                    "numeric_value": None,
                },
                {
                    "subject_id": "p1",
                    "timestamp": pd.Timestamp("2022-01-09"),
                    "type": "Measurement",
                    "source_concept_id": "MEA:丙氨酸氨基转移酶(ALT)-静脉血",
                    "numeric_value": 250,
                },
            ]
        )
        out = identify_baseline_liver_injury(df)
        self.assertEqual(set(out["subject_id"]), {"p1"})

    def test_dili_positive_with_dbil_ibil_fill(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "subject_id": "p1",
                    "timestamp": pd.Timestamp("2022-02-01"),
                    "type": "Measurement",
                    "source_concept_id": "MEA:丙氨酸氨基转移酶(ALT)-静脉血",
                    "numeric_value": 130,
                },
                {
                    "subject_id": "p1",
                    "timestamp": pd.Timestamp("2022-02-01"),
                    "type": "Measurement",
                    "source_concept_id": "MEA:直接胆红素(DBIL)-静脉血",
                    "numeric_value": 20,
                },
                {
                    "subject_id": "p1",
                    "timestamp": pd.Timestamp("2022-02-01"),
                    "type": "Measurement",
                    "source_concept_id": "MEA:间接胆红素(IBIL)-静脉血",
                    "numeric_value": 30,
                },
            ]
        )
        out = identify_dili_positive_events(df)
        self.assertEqual(len(out), 1)


if __name__ == "__main__":
    unittest.main()

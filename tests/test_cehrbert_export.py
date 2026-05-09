from __future__ import annotations

import unittest

import pandas as pd

from onology_meds.cehrbert_export import att_token, build_patient_sequence_rows


class TestCehrbertExport(unittest.TestCase):
    def test_att_token_buckets(self) -> None:
        self.assertEqual(att_token(0), "W_0")
        self.assertEqual(att_token(7), "W_1")
        self.assertEqual(att_token(27), "W_3")
        self.assertEqual(att_token(30), "M_1")
        self.assertEqual(att_token(90), "M_3")
        self.assertEqual(att_token(400), "LT")

    def test_build_patient_sequence_rows_groups_visits(self) -> None:
        events = pd.DataFrame(
            [
                {
                    "subject_id": "p1",
                    "timestamp": "2025-01-01 09:00:00",
                    "type": "Measurement",
                    "source_concept_id": "MEA:ALT",
                    "standardized_source_concept_id": "MEA:Alanine aminotransferase",
                    "standard_term_en": "Alanine aminotransferase",
                },
                {
                    "subject_id": "p1",
                    "timestamp": "2025-01-01 09:00:00",
                    "type": "Drug",
                    "source_concept_id": "DRUG:Pembrolizumab:[IMMUNE]",
                    "standardized_source_concept_id": "DRUG:Pembrolizumab:[IMMUNE]",
                    "standard_term_en": "Pembrolizumab",
                },
                {
                    "subject_id": "p1",
                    "timestamp": "2025-01-15 09:00:00",
                    "type": "Observation",
                    "source_concept_id": "OBS:GENDER:男",
                    "standardized_source_concept_id": "OBS:Male",
                    "standard_term_en": "Male",
                },
            ]
        )

        rows = build_patient_sequence_rows(events, split_map={"p1": "train"})
        self.assertEqual(len(rows), 1)
        patient = rows[0]
        self.assertEqual(patient["subject_id"], "p1")
        self.assertEqual(patient["split"], "train")
        self.assertEqual(patient["visit_count"], 2)
        self.assertEqual(
            patient["sequence_standard_term_tokens"],
            [
                "[VS]",
                "Pembrolizumab",
                "Alanine aminotransferase",
                "[VE]",
                "W_2",
                "[VS]",
                "Male",
                "[VE]",
            ],
        )
        self.assertEqual(patient["visits"][1]["att_from_previous"], "W_2")


if __name__ == "__main__":
    unittest.main()

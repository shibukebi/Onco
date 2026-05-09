from __future__ import annotations

import unittest

from onology_meds.standardize_sample import ConceptMapper, DomainDictionary


class TestStandardizeSample(unittest.TestCase):
    def test_parse_lookup_key(self) -> None:
        mapper = ConceptMapper(by_type={})
        self.assertEqual(mapper.parse_lookup_key("Condition", "ICD10:C34.905:右肺恶性肿瘤"), "C34.905:右肺恶性肿瘤")
        self.assertEqual(mapper.parse_lookup_key("Drug", "DRUG:帕博利珠单抗:[DILI_RISK:IMMUNO|IMMUNE]"), "帕博利珠单抗")
        self.assertEqual(mapper.parse_lookup_key("Measurement", "MEA:丙氨酸氨基转移酶(ALT)-静脉血"), "丙氨酸氨基转移酶(ALT)-静脉血")
        self.assertEqual(mapper.parse_lookup_key("Observation", "OBS:GENDER:男"), "GENDER:男")

    def test_observation_fallback(self) -> None:
        mapper = ConceptMapper(by_type={})
        self.assertEqual(mapper.fallback_term("Observation", "LIVER_METASTASIS:是"), "Liver Metastasis: Yes")
        self.assertEqual(mapper.fallback_term("Observation", "BONE_METASTASIS:否"), "Bone Metastasis: No")


if __name__ == "__main__":
    unittest.main()

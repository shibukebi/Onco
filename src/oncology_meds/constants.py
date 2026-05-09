from __future__ import annotations

DEFAULT_INPUT_DIR = "./data/raw_input"
DEFAULT_RESOURCE_DIR = "./resources"
DEFAULT_MEDS_DIR = "./MEDS data"
DEFAULT_CONCEPT_DICTIONARY_DIR = "./resources/unified_concept_dictionary_light_index_by_domain"
DEFAULT_SEED = 42

MEDS_CORE_COLUMNS = [
    "subject_id",
    "timestamp",
    "type",
    "source_concept_id",
    "numeric_value",
]

EVENT_EXTENDED_COLUMNS = MEDS_CORE_COLUMNS + [
    "raw_table",
    "raw_vsn",
    "text_value",
    "unit",
    "drug_tags",
]

LAB_PREFIX = "MEA:"
OBS_PREFIX = "OBS:"
PROC_PREFIX = "PROCEDURE:"
DRUG_PREFIX = "DRUG:"

ONCOLOGY_DRUG_TAGS = {
    "CHEMO",
    "IMMUNE",
    "TARGETED",
    "ADC",
    "BISPECIFIC_IMMUNE",
}

NON_INDEX_DRUG_TAGS = {
    "HORMONE",
    "SUPPORTIVE",
    "SOLVENT",
}

ULN_VALUES = {
    "ALT": 40.0,
    "AST": 40.0,
    "ALP": 125.0,
    "TBIL": 23.0,
    "GGT": 45.0,
}

LIVER_LAB_NAMES = {
    "ALT": "丙氨酸氨基转移酶(ALT)-静脉血",
    "AST": "天门冬氨酸氨基转移酶(AST)-静脉血",
    "ALP": "碱性磷酸酶(ALP)-静脉血",
    "TBIL": "总胆红素(TBIL)-静脉血",
    "GGT": "γ-谷氨酰基转移酶(GGT)-静脉血",
    "DBIL": "直接胆红素(DBIL)-静脉血",
    "IBIL": "间接胆红素(IBIL)-静脉血",
}

INV_LIVER_LAB_NAMES = {value: key for key, value in LIVER_LAB_NAMES.items()}

BILIARY_IMAGING_KEYWORDS = [
    "胆道",
    "胆管",
    "胆囊",
    "梗阻",
    "扩张",
    "结石",
]

BILIARY_DIAGNOSIS_KEYWORDS = [
    "胆道梗阻",
    "胆汁淤积",
    "胆管炎",
    "胆囊炎",
    "胆石",
]

AIH_DIAGNOSIS_KEYWORDS = [
    "AIH",
    "自身免疫性肝炎",
    "原发性胆汁性胆管炎",
    "PBC",
    "原发性硬化性胆管炎",
    "PSC",
]

ALCOHOL_DIAGNOSIS_KEYWORDS = [
    "酒精",
    "乙醇",
    "酒精性肝病",
]

METABOLIC_DIAGNOSIS_KEYWORDS = [
    "威尔逊",
    "肝豆状核变性",
    "血色病",
    "α1-抗胰蛋白酶",
]

ISCHEMIC_KEYWORDS = [
    "缺血",
    "休克肝",
    "低灌注",
]

NAFLD_DIAGNOSIS_KEYWORDS = [
    "脂肪肝",
    "NAFLD",
    "NASH",
]

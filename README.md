# onology-meds

Modular MEDS + DILI pipeline for converting oncology clinical tables into MEDS-format event data, cohort filtering artifacts, DILI outputs, and CEHR-BERT-style temporal sequences.

## Included

- Python source code under `src/onology_meds/`
- Tests under `tests/`
- Research workflow documentation under `docs/`

## Not Included

This repository does not include:

- raw clinical data
- generated MEDS outputs
- validation outputs
- local concept dictionaries
- local spreadsheets or other sensitive resources

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Run the CLI with your own local data/resources:

```bash
python3 -m onology_meds.cli --input-dir "./data/raw_input" --resource-dir "./resources" inspect
```

## Main Commands

- `inspect`
- `build-meds`
- `filter-cohort`
- `run-dili`
- `run-all`
- `export-standardized-sample`
- `export-cehrbert-sequences`
- `export-fallback-candidates`

## Raw Data To Standard Terms

This project separates the transformation into two stages:

1. Raw clinical tables to MEDS event concepts
2. MEDS event concepts to standardized English terms

### Stage 1: Raw Tables To MEDS Concepts

Raw table rows are first converted into MEDS-style events with:

- `subject_id`
- `timestamp`
- `type`
- `source_concept_id`
- `numeric_value`

Examples:

- diagnosis row -> `Condition` -> `ICD10:<code>:<diagnosis_name>`
- lab row -> `Measurement` -> `MEA:<lab_name>`
- drug order row -> `Drug` -> `DRUG:<ingredient_name>:[TAG1|TAG2|...]`
- baseline flag row -> `Observation` -> `OBS:<flag_name>:<value>`
- surgery row -> `Procedure` -> `PROCEDURE:<procedure_name>`

### Stage 2: MEDS Concepts To Standard English Terms

Standardization is performed by `src/onology_meds/standardize_sample.py`.

The logic is:

1. Parse a lookup key from `source_concept_id`
2. Select the dictionary by event domain
3. Match `lookup_key_cn` against dictionary `concept_name_cn`
4. Output dictionary `concept_name` as the standard English term
5. Rebuild a standardized concept id using the English term

Dictionary routing:

- `Condition` -> `condition.json`
- `Drug` -> `drug.json`
- `Measurement` -> `measurement.json`
- `Observation` -> `obs.json`
- `Procedure` -> `procedure.json`

Examples:

- `MEA:丙氨酸氨基转移酶(ALT)-静脉血`
  - lookup key: `丙氨酸氨基转移酶(ALT)-静脉血`
  - standard term: `Alanine aminotransferase [Enzymatic activity/volume] in Blood`

- `DRUG:帕博利珠单抗:[IMMUNE|DILI_RISK:IMMUNO]`
  - lookup key: `帕博利珠单抗`
  - standard term: `Pembrolizumab`

- `OBS:GENDER:男`
  - lookup key: `GENDER:男`
  - standard term: `Male`

### Matching Status

The mapping result is recorded in `mapping_status`.

- `reference_dictionary`: matched by dictionary and marked as high-confidence reference entry
- `matched_by_concept_id`: matched by dictionary through concept-level alignment
- `unmatched`: dictionary contains an English term, but the entry is still marked as non-standard or unmatched
- `local_dictionary_override`: a local dictionary entry was manually corrected in the domain dictionary
- `fallback_rule`: no dictionary entry was used; the system generated a fallback English label

### Fallback And Dictionary Completion

If no usable dictionary entry is found:

- observation flags such as `XXX:是/否` are converted by rule into English yes/no labels
- measurements fall back to a title-cased label
- all remaining unresolved concepts are marked `fallback_rule`

To review missing standardized terms:

```bash
python3 -m onology_meds.cli export-fallback-candidates
```

This produces a completion workbook where unresolved concepts can be manually filled and later written back into the domain dictionaries.

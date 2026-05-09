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

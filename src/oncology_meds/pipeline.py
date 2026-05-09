from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import LAB_TABLES, SKIPPED_SOURCE_FILES, TABLE_CONFIGS, PipelinePaths
from .constants import (
    EVENT_EXTENDED_COLUMNS,
    LAB_PREFIX,
    MEDS_CORE_COLUMNS,
    OBS_PREFIX,
    PROC_PREFIX,
)
from .drug_labels import DrugKnowledgeBase
from .frequency import split_drug_events_by_frequency
from .io import read_raw_table, sniff_csv_summary
from .utils import normalize_string, split_multi_value, stable_unique


@dataclass(slots=True)
class BuildArtifacts:
    events: pd.DataFrame
    imaging_sidecar: pd.DataFrame
    table_summaries: list[dict[str, Any]]


def make_empty_events() -> pd.DataFrame:
    return pd.DataFrame(columns=EVENT_EXTENDED_COLUMNS)


def _base_event_frame(df: pd.DataFrame, raw_table: str) -> pd.DataFrame:
    result = pd.DataFrame(index=df.index)
    result["subject_id"] = df.get("patient_sn", pd.Series(index=df.index, dtype="object")).astype(str)
    result["timestamp"] = pd.NaT
    result["type"] = ""
    result["source_concept_id"] = ""
    result["numeric_value"] = np.nan
    result["raw_table"] = raw_table
    result["raw_vsn"] = next((df[col] for col in df.columns if col.startswith("vsn_")), pd.Series("", index=df.index))
    result["text_value"] = ""
    result["unit"] = ""
    result["drug_tags"] = ""
    return result


def _parse_timestamp(series: pd.Series | None) -> pd.Series:
    if series is None:
        return pd.Series(dtype="datetime64[ns]")
    return pd.to_datetime(series, errors="coerce")


def _build_lab_events(filename: str, df: pd.DataFrame) -> pd.DataFrame:
    events = _base_event_frame(df, filename)
    events["timestamp"] = _parse_timestamp(df.get("检验日期"))
    events["type"] = "Measurement"
    source = df.get("检验项目名称(归一)", pd.Series(index=df.index, dtype="object")).astype(str)
    qualitative = df.get("检验定性结果")
    numeric = pd.to_numeric(df.get("检验定量结果"), errors="coerce")
    hybrid = df.get("检验定性定量结果")
    events["source_concept_id"] = LAB_PREFIX + source
    events["numeric_value"] = numeric
    events["unit"] = df.get("检验定量结果单位", pd.Series("", index=df.index)).astype(str)

    if filename == "基线数据.基线_病毒相关检查_gbk.csv":
        qualitative_mask = numeric.isna() & qualitative.notna()
        if hybrid is not None:
            qualitative_mask = qualitative_mask | (numeric.isna() & hybrid.notna())
        events.loc[qualitative_mask, "source_concept_id"] = (
            LAB_PREFIX
            + source[qualitative_mask].astype(str)
            + ":"
            + qualitative.fillna(hybrid).astype(str)[qualitative_mask]
        )
    return events


def _build_diagnosis_events(filename: str, df: pd.DataFrame) -> pd.DataFrame:
    if "诊断类型" in df.columns:
        df = df[df["诊断类型"].astype(str).str.strip() == "出院诊断"].copy()
    df = df.reset_index(drop=True)
    timestamp_series = pd.to_datetime(df.get("诊断日期"), errors="coerce")
    rows: list[dict[str, Any]] = []
    for row_idx, row in df.iterrows():
        codes = split_multi_value(row.get("诊断ICD10编码"))
        names = split_multi_value(row.get("诊断ICD10名称"))
        for code_idx, code in enumerate(codes):
            concept = f"ICD10:{code}"
            if code_idx < len(names) and names[code_idx]:
                concept = f"{concept}:{names[code_idx]}"
            rows.append(
                {
                    "subject_id": normalize_string(row.get("patient_sn")),
                    "timestamp": timestamp_series.iloc[row_idx] if row_idx < len(timestamp_series) else pd.NaT,
                    "type": "Condition",
                    "source_concept_id": concept,
                    "numeric_value": np.nan,
                    "raw_table": filename,
                    "raw_vsn": normalize_string(row.get("vsn_全部诊断")),
                    "text_value": normalize_string(row.get("诊断名称")),
                    "unit": "",
                    "drug_tags": "",
                }
            )
    return pd.DataFrame(rows, columns=EVENT_EXTENDED_COLUMNS)


def _build_baseline_events(filename: str, df: pd.DataFrame) -> pd.DataFrame:
    timestamp = _parse_timestamp(df.get("基线资料收集时间"))
    first_diag_ts = _parse_timestamp(df.get("首次本院诊断时间"))
    base_ts = timestamp.combine_first(first_diag_ts)
    rows: list[dict[str, Any]] = []

    def add_row(subject_id: str, ts: pd.Timestamp, event_type: str, concept: str, numeric: float | None = None) -> None:
        rows.append(
            {
                "subject_id": subject_id,
                "timestamp": ts,
                "type": event_type,
                "source_concept_id": concept,
                "numeric_value": numeric if numeric is not None else np.nan,
                "raw_table": filename,
                "raw_vsn": "",
                "text_value": "",
                "unit": "",
                "drug_tags": "",
            }
        )

    for idx, row in df.iterrows():
        subject_id = normalize_string(row.get("patient_sn"))
        ts = base_ts.iloc[idx] if idx < len(base_ts) else pd.NaT
        if not subject_id or pd.isna(ts):
            continue

        if normalize_string(row.get("是否死亡\n选项:是,否")) == "是":
            death_ts = pd.to_datetime(row.get("死亡时间"), errors="coerce")
            add_row(subject_id, death_ts if pd.notna(death_ts) else ts, "Death", "DEATH")

        if normalize_string(row.get("性别\n选项:男,女")):
            add_row(subject_id, ts, "Observation", f"{OBS_PREFIX}GENDER:{normalize_string(row.get('性别\\n选项:男,女'))}")
        if normalize_string(row.get("是否吸烟史\n选项:是,否")):
            add_row(subject_id, ts, "Observation", f"{OBS_PREFIX}SMOKING_HISTORY:{normalize_string(row.get('是否吸烟史\\n选项:是,否'))}")
        if normalize_string(row.get("是否饮酒史\n选项:是,否")):
            add_row(subject_id, ts, "Observation", f"{OBS_PREFIX}DRINKING_HISTORY:{normalize_string(row.get('是否饮酒史\\n选项:是,否'))}")

        for raw_col, concept in [
            ("首诊年龄(岁)", "FIRST_DIAGNOSIS_AGE"),
            ("身高(cm)", "HEIGHT"),
            ("体重(kg)", "WEIGHT"),
            ("体重指数(BMI)", "BMI"),
            ("体表面积(BSA)", "BSA"),
        ]:
            value = pd.to_numeric(row.get(raw_col), errors="coerce")
            if pd.notna(value):
                add_row(subject_id, ts, "Measurement", f"MEAS:{concept}", float(value))

        for raw_col, concept in [
            ("首次pT分期", "PT_STAGE"),
            ("首次pN分期", "PN_STAGE"),
            ("首次pM分期", "PM_STAGE"),
            ("首次cT分期", "CT_STAGE"),
            ("首次cN分期", "CN_STAGE"),
            ("首次cM分期", "CM_STAGE"),
            ("组织学分型", "HISTOLOGY"),
            ("肺癌组织学分型(归一)", "LUNG_HISTOLOGY"),
            ("非小细胞肺癌组织学分型", "NSCLC_HISTOLOGY"),
            ("小细胞肺癌", "SCLC_HISTOLOGY"),
            ("非小细胞肺癌", "NSCLC_FLAG"),
        ]:
            text = normalize_string(row.get(raw_col))
            if text:
                add_row(subject_id, ts, "Observation", f"{OBS_PREFIX}{concept}:{text}")

        for raw_col, concept in [
            ("是否行靶向治疗\n选项:是,否", "TARGETED_THERAPY"),
            ("是否行免疫治疗\n选项:是,否", "IMMUNOTHERAPY"),
            ("是否行化疗\n选项:是,否", "CHEMOTHERAPY"),
            ("是否行放疗\n选项:是,否", "RADIOTHERAPY"),
        ]:
            if normalize_string(row.get(raw_col)) == "是":
                add_row(subject_id, ts, "Observation", f"{OBS_PREFIX}{concept}:Yes")

        history_names = split_multi_value(row.get("既往疾病名称"))
        if normalize_string(row.get("是否有既往疾病史\n选项:是,否")) == "是":
            for history_name in history_names:
                add_row(subject_id, ts, "Observation", f"{OBS_PREFIX}HAS_PAST_ILLNESS:是:{history_name}")

    return pd.DataFrame(rows, columns=EVENT_EXTENDED_COLUMNS)


def _build_baseline_anchor_map(df: pd.DataFrame) -> dict[str, pd.Timestamp]:
    timestamp = _parse_timestamp(df.get("基线资料收集时间"))
    first_diag_ts = _parse_timestamp(df.get("首次本院诊断时间"))
    anchor = timestamp.combine_first(first_diag_ts)
    result: dict[str, pd.Timestamp] = {}
    for idx, subject_id in enumerate(df.get("patient_sn", pd.Series(dtype="object")).astype(str)):
        sid = normalize_string(subject_id)
        if not sid:
            continue
        ts = anchor.iloc[idx] if idx < len(anchor) else pd.NaT
        if pd.notna(ts):
            result[sid] = ts
    return result


def _build_pathology_events(filename: str, df: pd.DataFrame) -> pd.DataFrame:
    events = _base_event_frame(df, filename)
    events["timestamp"] = _parse_timestamp(df.get("检查日期"))
    events["type"] = "Observation"
    events["source_concept_id"] = OBS_PREFIX + df.get("检查名称", pd.Series(index=df.index)).astype(str)
    events["text_value"] = df.get("病理结论", pd.Series("", index=df.index)).astype(str)
    events["source_concept_id"] = events["source_concept_id"] + ":" + events["text_value"]
    return events


def _build_procedure_events(filename: str, df: pd.DataFrame) -> pd.DataFrame:
    events = _base_event_frame(df, filename)
    events["type"] = "Procedure"
    if filename == "基线数据.基线_放射治疗_gbk.csv":
        events["timestamp"] = _parse_timestamp(df.get("放疗开始日期"))
        events["source_concept_id"] = f"{PROC_PREFIX}RADIOTHERAPY:1"
    else:
        events["timestamp"] = _parse_timestamp(df.get("手术开始时间"))
        events["source_concept_id"] = PROC_PREFIX + df.get("手术名称", pd.Series(index=df.index)).astype(str)
    return events


def _build_followup_events(filename: str, df: pd.DataFrame, baseline_anchor_map: dict[str, pd.Timestamp]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        subject_id = normalize_string(row.get("patient_sn"))
        ts = baseline_anchor_map.get(subject_id, pd.NaT)
        if not subject_id or pd.isna(ts):
            continue
        for col, concept in [
            ("是否肝转移\n选项:是,否", "LIVER_METASTASIS"),
            ("是否骨转移\n选项:是,否", "BONE_METASTASIS"),
        ]:
            text = normalize_string(row.get(col))
            if text:
                rows.append(
                    {
                        "subject_id": subject_id,
                        "timestamp": ts,
                        "type": "Observation",
                        "source_concept_id": f"{OBS_PREFIX}{concept}:{text}",
                        "numeric_value": np.nan,
                        "raw_table": filename,
                        "raw_vsn": normalize_string(row.get("vsn_随访小结")),
                        "text_value": "",
                        "unit": "",
                        "drug_tags": "",
                    }
                )
    return pd.DataFrame(rows, columns=EVENT_EXTENDED_COLUMNS)


def _build_imaging_sidecar(filename: str, df: pd.DataFrame) -> pd.DataFrame:
    events = _base_event_frame(df, filename)
    events["timestamp"] = _parse_timestamp(df.get("报告日期"))
    events["type"] = "Observation"
    source = df.get("检查名称(归一)", df.get("检查名称(原值)", pd.Series(index=df.index))).astype(str)
    text = df.get("检查结论", pd.Series("", index=df.index)).astype(str)
    events["source_concept_id"] = OBS_PREFIX + source + ":" + text
    events["text_value"] = text
    return events


def _build_temperature_events(
    filename: str,
    df: pd.DataFrame,
    baseline_anchor_map: dict[str, pd.Timestamp],
) -> pd.DataFrame:
    events = _base_event_frame(df, filename)
    events["timestamp"] = df.get("patient_sn", pd.Series(index=df.index)).astype(str).map(
        lambda sid: baseline_anchor_map.get(normalize_string(sid), pd.NaT)
    )
    events["type"] = "Measurement"
    events["source_concept_id"] = "MEA:体温"
    events["numeric_value"] = pd.to_numeric(df.get("体温(摄氏度)"), errors="coerce")
    return events


def _build_drug_events(filename: str, df: pd.DataFrame, kb: DrugKnowledgeBase) -> pd.DataFrame:
    events = _base_event_frame(df, filename)
    events["timestamp"] = _parse_timestamp(df.get("开始时间")).combine_first(_parse_timestamp(df.get("开立时间")))
    events["type"] = "Drug"
    events["numeric_value"] = pd.to_numeric(df.get("单次剂量"), errors="coerce")
    events["unit"] = df.get("单次剂量单位", pd.Series("", index=df.index)).astype(str)
    events["text_value"] = df.get("药物商品名", pd.Series("", index=df.index)).astype(str)

    order_status = df.get("医嘱状态\n选项:未开立,已开立,已作废,已停止,已执行,已确认,其他", pd.Series("", index=df.index)).astype(str)
    keep_mask = ~order_status.str.contains("未开立|已作废|撤销", na=False)
    working = df[keep_mask].copy()
    events = events[keep_mask].copy()
    events["frequency"] = working.get("用药频次", pd.Series("", index=working.index)).astype(str)
    annotated = kb.annotate_frame(working)
    events["source_concept_id"] = annotated["source_concept_id"].to_list()
    events["drug_tags"] = annotated["drug_tags"].to_list()

    events = split_drug_events_by_frequency(events)
    if "frequency" in events.columns:
        events = events.drop(columns=["frequency"])
    return events


def build_events(paths: PipelinePaths) -> BuildArtifacts:
    kb = DrugKnowledgeBase.load(paths.resource_dir)
    built_frames: list[pd.DataFrame] = []
    imaging_frames: list[pd.DataFrame] = []
    summaries: list[dict[str, Any]] = []
    baseline_anchor_map: dict[str, pd.Timestamp] = {}

    for csv_path in sorted(paths.input_dir.glob("*.csv")):
        summary = sniff_csv_summary(csv_path)
        summary["included"] = False
        summary["notes"] = ""
        filename = csv_path.name

        if filename in SKIPPED_SOURCE_FILES:
            summary["notes"] = "kept as source only; not included in v1 core events"
            summaries.append(summary)
            continue

        if filename == "基线数据.基线_gbk.csv":
            df, encoding = read_raw_table(csv_path)
            summary["encoding"] = encoding
            baseline_anchor_map = _build_baseline_anchor_map(df)
            baseline_events = _build_baseline_events(filename, df)
            built_frames.append(baseline_events)
            summary["included"] = True
            summary["rows"] = len(baseline_events)
            summaries.append(summary)
            continue

        if filename in LAB_TABLES:
            df, encoding = read_raw_table(csv_path)
            summary["encoding"] = encoding
            if filename == "基线数据.基线_生命体征_(1)_gbk.csv":
                lab_events = _build_temperature_events(filename, df, baseline_anchor_map)
            else:
                lab_events = _build_lab_events(filename, df)
            built_frames.append(lab_events)
            summary["included"] = True
            summary["rows"] = len(lab_events)
            summaries.append(summary)
            continue

        config = TABLE_CONFIGS.get(filename)
        if config is None:
            summary["notes"] = "unconfigured source"
            summaries.append(summary)
            continue

        df, encoding = read_raw_table(csv_path)
        summary["encoding"] = encoding
        if filename == "基线数据.基线_全部诊断_gbk.csv":
            events = _build_diagnosis_events(filename, df)
            built_frames.append(events)
            summary["included"] = True
            summary["rows"] = len(events)
        elif filename == "基线数据.基线_全部病理_gbk.csv":
            events = _build_pathology_events(filename, df)
            built_frames.append(events)
            summary["included"] = True
            summary["rows"] = len(events)
        elif filename in {"基线数据.基线_手术治疗-全部手术_gbk.csv", "基线数据.基线_放射治疗_gbk.csv"}:
            events = _build_procedure_events(filename, df)
            built_frames.append(events)
            summary["included"] = True
            summary["rows"] = len(events)
        elif filename == "基线数据.基线_随访小结_gbk.csv":
            events = _build_followup_events(filename, df, baseline_anchor_map)
            built_frames.append(events)
            summary["included"] = True
            summary["rows"] = len(events)
        elif filename == "基线数据.基线_药品类医嘱_gbk.csv":
            events = _build_drug_events(filename, df, kb)
            built_frames.append(events)
            summary["included"] = True
            summary["rows"] = len(events)
        elif config.imaging_sidecar:
            sidecar = _build_imaging_sidecar(filename, df)
            imaging_frames.append(sidecar)
            summary["included"] = False
            summary["rows"] = len(sidecar)
            summary["notes"] = "exported to excluded_imaging_observations.csv"
        summaries.append(summary)

    events = pd.concat(built_frames, ignore_index=True) if built_frames else make_empty_events()
    imaging = pd.concat(imaging_frames, ignore_index=True) if imaging_frames else make_empty_events()
    events = finalize_events(events)
    imaging = finalize_events(imaging)
    return BuildArtifacts(events=events, imaging_sidecar=imaging, table_summaries=summaries)


def finalize_events(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return make_empty_events()
    result = df.copy()
    result["subject_id"] = result["subject_id"].astype(str).str.strip()
    result["timestamp"] = pd.to_datetime(result["timestamp"], errors="coerce")
    result["numeric_value"] = pd.to_numeric(result["numeric_value"], errors="coerce")
    result = result.dropna(subset=["subject_id", "timestamp", "source_concept_id"])
    result = result[result["subject_id"].str.lower() != "nan"]
    result = result[result["source_concept_id"].astype(str).str.strip() != ""]
    result = result.sort_values(["subject_id", "timestamp", "source_concept_id"]).reset_index(drop=True)
    return result


def core_meds_view(df: pd.DataFrame) -> pd.DataFrame:
    result = df[MEDS_CORE_COLUMNS].copy()
    result["timestamp"] = pd.to_datetime(result["timestamp"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
    return result

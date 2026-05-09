from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .constants import DEFAULT_INPUT_DIR, DEFAULT_RESOURCE_DIR, DEFAULT_SEED


@dataclass(slots=True)
class PipelinePaths:
    input_dir: Path = field(default_factory=lambda: Path(DEFAULT_INPUT_DIR))
    resource_dir: Path = field(default_factory=lambda: Path(DEFAULT_RESOURCE_DIR))
    output_dir: Path | None = None
    seed: int = DEFAULT_SEED

    def __post_init__(self) -> None:
        if self.output_dir is None:
            self.output_dir = self.input_dir / "CEHRBERT_MEDS_Output"


@dataclass(frozen=True, slots=True)
class TableConfig:
    filename: str
    table_type: str
    timestamp_column: str | None
    source_column: str | None = None
    numeric_column: str | None = None
    text_column: str | None = None
    unit_column: str | None = None
    include_in_events: bool = True
    imaging_sidecar: bool = False


TABLE_CONFIGS: dict[str, TableConfig] = {
    "基线数据.基线_全部诊断_gbk.csv": TableConfig(
        filename="基线数据.基线_全部诊断_gbk.csv",
        table_type="Condition",
        timestamp_column="诊断日期",
        source_column="诊断ICD10编码",
        text_column="诊断ICD10名称",
    ),
    "基线数据.基线_全部病理_gbk.csv": TableConfig(
        filename="基线数据.基线_全部病理_gbk.csv",
        table_type="Observation",
        timestamp_column="检查日期",
        source_column="检查名称",
        text_column="病理结论",
    ),
    "基线数据.基线_手术治疗-全部手术_gbk.csv": TableConfig(
        filename="基线数据.基线_手术治疗-全部手术_gbk.csv",
        table_type="Procedure",
        timestamp_column="手术开始时间",
        source_column="手术名称",
    ),
    "基线数据.基线_放射治疗_gbk.csv": TableConfig(
        filename="基线数据.基线_放射治疗_gbk.csv",
        table_type="Procedure",
        timestamp_column="放疗开始日期",
    ),
    "基线数据.基线_药品类医嘱_gbk.csv": TableConfig(
        filename="基线数据.基线_药品类医嘱_gbk.csv",
        table_type="Drug",
        timestamp_column="开始时间",
        source_column="药物成分名",
        numeric_column="单次剂量",
        unit_column="单次剂量单位",
        text_column="药物商品名",
    ),
    "基线数据.基线_随访小结_gbk.csv": TableConfig(
        filename="基线数据.基线_随访小结_gbk.csv",
        table_type="Observation",
        timestamp_column=None,
        include_in_events=True,
    ),
    "基线数据.基线_CT检查_gbk.csv": TableConfig(
        filename="基线数据.基线_CT检查_gbk.csv",
        table_type="Observation",
        timestamp_column="报告日期",
        source_column="检查名称(归一)",
        text_column="检查结论",
        include_in_events=False,
        imaging_sidecar=True,
    ),
    "基线数据.基线_MRI检查_gbk.csv": TableConfig(
        filename="基线数据.基线_MRI检查_gbk.csv",
        table_type="Observation",
        timestamp_column="报告日期",
        source_column="检查名称(归一)",
        text_column="检查结论",
        include_in_events=False,
        imaging_sidecar=True,
    ),
    "基线数据.基线_超声检查_gbk.csv": TableConfig(
        filename="基线数据.基线_超声检查_gbk.csv",
        table_type="Observation",
        timestamp_column="报告日期",
        source_column="检查名称(归一)",
        text_column="检查结论",
        include_in_events=False,
        imaging_sidecar=True,
    ),
}

LAB_TABLES = {
    "基线数据.基线_血常规_gbk.csv",
    "基线数据.基线_C反应蛋白检测_gbk.csv",
    "基线数据.基线_其他检验_gbk.csv",
    "基线数据.基线_其他检验_(1)_gbk.csv",
    "基线数据.基线_其他检验_(2)_gbk.csv",
    "基线数据.基线_其他检验_(3)_gbk.csv",
    "基线数据.基线_其他检验_(4)_gbk.csv",
    "基线数据.基线_其他检验_(5)_gbk.csv",
    "基线数据.基线_其他检验_(6)_gbk.csv",
    "基线数据.基线_其他检验_(7)_gbk.csv",
    "基线数据.基线_其他检验_(8)_gbk.csv",
    "基线数据.基线_其他检验_(9)_gbk.csv",
    "基线数据.基线_其他检验_(10)_gbk.csv",
    "基线数据.基线_生化检查_gbk.csv",
    "基线数据.基线_凝血检查_gbk.csv",
    "基线数据.基线_病毒相关检查_gbk.csv",
    "基线数据.基线_尿常规_gbk.csv",
    "基线数据.基线_甲状腺功能检查_gbk.csv",
    "基线数据.基线_肿瘤标记物检查_gbk.csv",
    "基线数据.基线_生命体征_(1)_gbk.csv",
}

SKIPPED_SOURCE_FILES = {
    "基线数据.基线_入院记录_gbk.csv",
    "基线数据.基线_全部就诊_gbk.csv",
    "基线数据.基线_治疗及结局_gbk.csv",
    "基线数据.基线_非药品类医嘱_gbk.csv",
    "基线数据.基线_生命体征_gbk.csv",
}

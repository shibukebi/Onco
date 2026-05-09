# MEDS + DILI 研究流程说明

## 1. 目标

本流程将输入目录中的原始临床表转为 MEDS 事件流，并在此基础上完成队列纳排和 DILI 自动识别。

主输出目录默认为：

`<input-dir>/CEHRBERT_MEDS_Output`

## 2. 数据来源与纳入范围

纳入核心事件表的来源：

- `基线数据.基线_gbk.csv`
- `基线数据.基线_全部诊断_gbk.csv`
- `基线数据.基线_全部病理_gbk.csv`
- `基线数据.基线_手术治疗-全部手术_gbk.csv`
- `基线数据.基线_放射治疗_gbk.csv`
- `基线数据.基线_药品类医嘱_gbk.csv`
- `基线数据.基线_随访小结_gbk.csv`
- 各类实验室表：血常规、生化、凝血、病毒、尿常规、甲状腺功能、肿瘤标记物、其他检验、C 反应蛋白、体温

不纳入 v1 核心事件表、但保留为来源的表：

- `基线数据.基线_入院记录_gbk.csv`
- `基线数据.基线_全部就诊_gbk.csv`
- `基线数据.基线_治疗及结局_gbk.csv`
- `基线数据.基线_非药品类医嘱_gbk.csv`

影像侧表：

- `基线数据.基线_CT检查_gbk.csv`
- `基线数据.基线_MRI检查_gbk.csv`
- `基线数据.基线_超声检查_gbk.csv`

以上影像不进入主 `events.parquet`，单独导出为 `excluded_imaging_observations.csv`，但仍参与 DILI 继发病因判断。

## 3. 表到事件的映射

### 3.1 诊断

- 来源：`全部诊断`
- 仅保留 `诊断类型 = 出院诊断`
- `诊断ICD10编码` 按逗号/分号原子化拆分
- 输出类型：`Condition`
- 事件概念格式：`ICD10:<编码>:<名称>`

### 3.2 实验室

- 来源：各类检验表
- 输出类型：`Measurement`
- 事件概念格式：`MEA:<检验项目名称(归一)>`
- 病毒相关检查在定量缺失且存在定性结果时，概念补为 `MEA:<项目>:<定性结果>`

### 3.3 基线表派生事件

- 性别、吸烟史、饮酒史、既往疾病、TNM 分期、组织学、治疗标志输出 `Observation`
- 首诊年龄、身高、体重、BMI、BSA 输出 `Measurement`
- 已死亡患者额外生成 `Death` 事件

### 3.4 药物医嘱

- 来源：`药品类医嘱`
- 剔除状态：`未开立`、`已作废`、`已撤销`
- 保留 `已停止`
- 概念格式：`DRUG:<成分名>:[TAG1|TAG2|...]`
- 主药物知识库：`<resource-dir>/annotated_unique_drugs.xlsx`
- 二次补全来源：
  - `DILI_Risk_Dictionary_Final.xlsx`
  - `chemo_classification_dictionary 2.csv`

药物标签体系：

- 治疗类别：`CHEMO`、`IMMUNE`、`TARGETED`、`ADC`、`BISPECIFIC_IMMUNE`
- 其他类别：`HORMONE`、`SUPPORTIVE`、`SOLVENT`
- DILI 风险：`DILI_RISK:<level>`
- ATC2 属于肝胆类时加 `HEPATOBILIARY`

### 3.5 手术与放疗

- 手术输出：`Procedure`
- 放疗输出固定概念：`PROCEDURE:RADIOTHERAPY:1`

## 4. 队列纳排

按顺序执行：

1. 多原发肿瘤黑名单
2. 肿瘤药暴露筛选
3. 基线肝损伤排除
4. 随访完整性筛选

### 4.1 肿瘤药暴露定义

以下标签视为 index therapy：

- `CHEMO`
- `IMMUNE`
- `TARGETED`
- `ADC`
- `BISPECIFIC_IMMUNE`

以下标签不作为 index therapy：

- `HORMONE`
- `SUPPORTIVE`
- `SOLVENT`

### 4.2 基线肝损伤

取首个肿瘤药前 30 天内最近一次肝功能：

- `ALT >= 200`
- 或 `ALT >= 120 且 TBIL >= 46`
- 或 `ALP >= 250 且 GGT > 45`

若 `TBIL` 缺失，用 `DBIL + IBIL` 补。

### 4.3 随访完整性

硬过滤口径：

- 首个肿瘤药前 14 天内至少 1 次 ALT
- 治疗期间至少 3 个不同监测时间点

同时保留一份 `前后14天` 审计名单用于人工复核。

## 5. DILI 判定

### 5.1 阳性识别

任一时间点满足以下任一分支即判为 DILI 阳性：

- Branch A: `ALT >= 200`
- Branch B: `ALT >= 120 且 TBIL >= 46`
- Branch C: `ALP >= 250 且 GGT > 45`

### 5.2 结果字段

`dili/dili_comprehensive_results.csv` 包含：

- 阳性时间点
- 当前肝功能值
- 基线值
- 首次肿瘤药暴露时间
- `CTCAE` 分级
- `R_value`
- `dili_type`
- `secondary_cause`

### 5.3 继发病因

继续排查：

- 病毒性肝炎
- 胆道梗阻/胆道损伤
- 自身免疫性肝病
- 肝转移
- 酒精性肝病
- 代谢性肝病
- 缺血性肝病
- `NAFLD`

## 6. 输出文件

核心输出：

- `events.parquet`
- `metadata/codes.parquet`
- `metadata/subject_splits.parquet`
- `metadata/dataset.json`

审计输出：

- `audits/*.csv`

DILI 输出：

- `dili/dili_positive_events.csv`
- `dili/dili_comprehensive_results.csv`

运行日志：

- `logs/inspect_summary.json`
- `logs/build_summary.json`
- `logs/run_manifest.json`

## 7. 复跑命令

```bash
python3 -m onology_meds.cli \
  --input-dir "./data/raw_input" \
  --resource-dir "./resources" \
  run-all
```

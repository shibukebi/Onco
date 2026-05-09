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

## 4. 原始数据到标准词组的转化逻辑

本项目将“标准词”定义为分 domain 标准化字典中的 `concept_name` 英文字段。  
因此，转化并不是直接从原始中文表格翻译到英文，而是通过两段式映射完成：

1. 原始表格行先转成 MEDS 事件
2. MEDS 事件再转成标准英文词组

### 4.1 第一步：原始表格到 MEDS 事件

每条原始记录先整理为统一事件结构：

- `subject_id`
- `timestamp`
- `type`
- `source_concept_id`
- `numeric_value`

其中 `source_concept_id` 是标准化前的中间概念键，负责承接原始中文语义。典型规则如下：

- 诊断：`ICD10:<编码>:<中文诊断名>`
- 检验：`MEA:<中文检验名>`
- 药物：`DRUG:<成分名>:[标签列表]`
- 观察项：`OBS:<字段名>:<取值>`
- 操作/手术：`PROCEDURE:<中文手术名>`

也就是说，原始数据不会直接进入英文标准词阶段，而是先被压缩成一个领域统一的 MEDS 概念层。

### 4.2 第二步：MEDS 概念到标准英文词组

标准词映射由 `src/onology_meds/standardize_sample.py` 中的 `ConceptMapper` 完成。

整体顺序如下：

1. 先根据事件类型选择字典文件
2. 再从 `source_concept_id` 中解析出待匹配中文键 `lookup_key_cn`
3. 用 `lookup_key_cn` 去匹配对应字典中的 `concept_name_cn`
4. 匹配成功后，输出该条字典记录的 `concept_name` 作为标准英文词
5. 再根据英文标准词重建 `standardized_source_concept_id`

字典分发关系固定为：

- `Condition` -> `condition.json`
- `Drug` -> `drug.json`
- `Measurement` -> `measurement.json`
- `Observation` -> `obs.json`
- `Procedure` -> `procedure.json`

### 4.3 `lookup_key_cn` 的解析规则

不同事件类型会先从 `source_concept_id` 中剥掉前缀或标签，得到真正用于查词典的中文键：

- `ICD10:C34.905:右肺恶性肿瘤` -> `C34.905:右肺恶性肿瘤`
- `DRUG:帕博利珠单抗:[IMMUNE|DILI_RISK:IMMUNO]` -> `帕博利珠单抗`
- `MEA:丙氨酸氨基转移酶(ALT)-静脉血` -> `丙氨酸氨基转移酶(ALT)-静脉血`
- `OBS:GENDER:男` -> `GENDER:男`
- `PROCEDURE:口腔清创术` -> `口腔清创术`

因此，字典匹配并不是直接拿完整 `source_concept_id` 去查，而是拿清洗后的 `lookup_key_cn` 去对齐字典中的中文概念名。

### 4.4 字典匹配规则

每个 domain 字典内部支持两级匹配：

1. `concept_name_cn` 精确匹配
2. 归一化后的 `concept_name_cn` 匹配

归一化主要处理：

- 空格折叠
- 大小写统一

一旦命中字典，就返回：

- `matched_concept_name_cn`
- `standard_term_en`
- `standardized_source_concept_id`
- `mapping_status`

其中：

- `matched_concept_name_cn` 来自字典中的 `concept_name_cn`
- `standard_term_en` 来自字典中的 `concept_name`

### 4.5 标准化后概念的重建

命中字典后，系统不会只保留英文词，还会重建英文版概念 ID：

- 诊断：`ICD10:<编码>:<英文标准词>`
- 药物：`DRUG:<英文标准词>:[原标签]`
- 检验：`MEA:<英文标准词>`
- 观察：`OBS:<英文标准词>`
- 手术：`PROCEDURE:<英文标准词>`

这样既保留了领域前缀，也把中文概念替换成了英文标准词。

### 4.6 `mapping_status` 的含义

当前标准化结果会输出以下状态：

- `reference_dictionary`
  - 字典命中，且该字典记录本身被标记为参考级标准匹配
- `matched_by_concept_id`
  - 字典命中，且该记录通过概念对齐链路匹配成功
- `unmatched`
  - 字典里有英文词，但该条记录仍被标记为未严格标准化
- `local_dictionary_override`
  - 本地字典中人工修正过的条目，直接以字典内容为准
- `fallback_rule`
  - 字典未命中，系统只能按规则生成兜底英文标签

### 4.7 本地修正规则的位置

本项目当前不再在映射代码里单独维护 `local override` 分支。  
本地修正已经直接写入原始 domain 字典中，因此会以 `local_dictionary_override` 的形式返回。

这意味着：

- 修正优先级已经前移到字典层
- 后续补词典时，不需要改 Python 逻辑
- 只需要维护字典 JSON 即可

### 4.8 Fallback 兜底逻辑

如果字典没有可用结果，则进入 `fallback_rule`：

- `Observation` 中的 `XXX:是/否` 会转为英文 yes/no 形式
- `Measurement` 会做标题化字符串兜底
- 其他类型保留原始清洗后文本

例如：

- `OBS:LIVER_METASTASIS:是` -> `Liver Metastasis: Yes`
- `MEA:白蛋白(ALB)-静脉血` 若未命中字典，则生成 `白蛋白(Alb)-静脉血`

这类结果可以用于审计和人工补词典，但不应默认视为高质量标准词。

### 4.9 补词典工作流

为了持续减少 `fallback_rule`，本项目提供专门导出：

```bash
python3 -m onology_meds.cli export-fallback-candidates
```

该命令会扫描全量 `events.parquet`，导出所有 `fallback_rule` 项，并生成人工补词典表。  
补录时建议优先处理：

1. `total_event_count` 高的条目
2. `total_subject_count` 高的条目
3. 肿瘤诊断、药物、肝功能指标等核心研究变量

## 5. 队列纳排

按顺序执行：

1. 多原发肿瘤黑名单
2. 肿瘤药暴露筛选
3. 基线肝损伤排除
4. 随访完整性筛选

### 5.1 肿瘤药暴露定义

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

### 5.2 基线肝损伤

取首个肿瘤药前 30 天内最近一次肝功能：

- `ALT >= 200`
- 或 `ALT >= 120 且 TBIL >= 46`
- 或 `ALP >= 250 且 GGT > 45`

若 `TBIL` 缺失，用 `DBIL + IBIL` 补。

### 5.3 随访完整性

硬过滤口径：

- 首个肿瘤药前 14 天内至少 1 次 ALT
- 治疗期间至少 3 个不同监测时间点

同时保留一份 `前后14天` 审计名单用于人工复核。

## 6. DILI 判定

### 6.1 阳性识别

任一时间点满足以下任一分支即判为 DILI 阳性：

- Branch A: `ALT >= 200`
- Branch B: `ALT >= 120 且 TBIL >= 46`
- Branch C: `ALP >= 250 且 GGT > 45`

### 6.2 结果字段

`dili/dili_comprehensive_results.csv` 包含：

- 阳性时间点
- 当前肝功能值
- 基线值
- 首次肿瘤药暴露时间
- `CTCAE` 分级
- `R_value`
- `dili_type`
- `secondary_cause`

### 6.3 继发病因

继续排查：

- 病毒性肝炎
- 胆道梗阻/胆道损伤
- 自身免疫性肝病
- 肝转移
- 酒精性肝病
- 代谢性肝病
- 缺血性肝病
- `NAFLD`

## 7. 输出文件

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

## 8. 复跑命令

```bash
python3 -m onology_meds.cli \
  --input-dir "./data/raw_input" \
  --resource-dir "./resources" \
  run-all
```

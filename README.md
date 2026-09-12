# 2026CUMCM

## A题：药材的烘干问题

小组建模与论文工作入口。第一问的有效径向数值基准及灵敏度已完成并合入main；第二问的变物性热湿耦合模型、表3–4、72 h `result2.xlsx`、论文图和验证归档已在 `feat/q2-coupled-drying` 完成。第三问固定尺寸全域干燥事件、表5、`result3.xlsx`、论文图和验证归档已在`feat/q3-fixed-drying`完成。第四问收缩域模型已在`feat/q4-shrinkage-drying`得到经验证的数值结论，`result4.xlsx`已生成并回读通过；PR #8 已打开并按 review 反馈补强交付门禁。整篇论文仍需按清单推进。

第一问基准由[PR #2](https://github.com/Lyxose-Tim/2026CUMCM/pull/2)交付，main合并提交为 `2924983`；依据为[正式模型契约](reports/Q1_MODEL_SPEC.md)，交付见[结果报告](reports/Q1_RESULTS_REPORT.md)、[验证报告](reports/Q1_VERIFY_REPORT.md)、[result1.xlsx](results/result1.xlsx)和[复现说明](REPRODUCE.md)。参考文档仍由[PR #1](https://github.com/Lyxose-Tim/2026CUMCM/pull/1)独立管理，按固定提交只读引用。历史计算报告保留生成时的版本与状态，当前协作进度以本入口、todo和PR记录为准。

评测后续 Issue #3/#4 由[PR #5](https://github.com/Lyxose-Tim/2026CUMCM/pull/5)向main交付，审核人已批准 `8be6535` 的数值证据、追溯、无Git路径和Issue范围，本轮同步修正其提出的文档状态问题。[参数灵敏度结果](reports/Q1_SENSITIVITY_REPORT.md)包含12组扰动、极端工况复核和独立图源；[鲁棒性设计](reports/Q1_ROBUSTNESS_DESIGN.md)明确联合/环境扰动及CV的适用范围。原基准文件保留，联合随机实验和实物验证仍未执行；Issue #4仅对应设计与文档交付。合并进度以PR记录为准，按用户已授权的“审核通过且无问题”条件执行。

第二问从 t=0 统一使用附录3变物性公式，正式网格为 N=20480。0–4 h 使用附件1逐段线性插值，4–72 h 采用最后一小时均值延拓，并另算末值保持及 50 °C、0.05 kg/kg 两个对照。见[模型规范](Q2_MODEL_SPEC.md)、[结果报告](reports/Q2_RESULTS_REPORT.md)、[验证报告](reports/Q2_VERIFY_REPORT.md)、[result2.xlsx](results/result2.xlsx)和[全精度归档](results/q2/archive/manifest.json)。72 h 是第二问固定情景范围，不代表问题三的严格停止时刻。

第三问沿用同一固定半径模型，以全部计算节点的最大含水率定位0.15 kg/kg的首次向下穿越。正式N=40960收紧BDF结果为57.4740097759 h；根后1 s完整状态严格达标，估计数值时间误差量级0.0453 s。见[模型规范](reports/Q3_MODEL_SPEC.md)、[结果报告](reports/Q3_RESULTS_REPORT.md)、[验证报告](reports/Q3_VERIFY_REPORT.md)、[result3.xlsx](results/result3.xlsx)、[复现说明](Q3_REPRODUCE.md)和[依赖记录](reports/Q3_DEPENDENCY_RECORD.md)。该数值预测依赖4 h后的环境延拓，不代表实验准确率。

第四问使用附件2实测半径分段线性插值、附录4物性和材料坐标`xi=r/R(t)`，以全部计算节点最大含水率首次低于0.15 kg/kg定位事件。正式N=20480收紧BDF结果为51.0920106837 h；10240到20480的临界时间差约0.0755 s，附录3固定半径退化回归到第三问同网格结果。见[模型规范](reports/Q4_MODEL_SPEC.md)、[结果报告](reports/Q4_RESULTS_REPORT.md)、[验证报告](reports/Q4_VERIFY_REPORT.md)、[表6](results/q4/table6.md)、[result4.xlsx](results/result4.xlsx)和[图表清单](results/q4/figure_manifest.json)。Excel回读核对3066行、23列、44287个数值单元和23165个域外空白，并逐列核对0–2 cm表头及“药材表面”列。

### 阅读顺序

| 文档 | 用途 | 建议阅读者 |
| --- | --- | --- |
| [详细指导计划](plan.md) | 四问路线、三人分工、72小时参考排程、图表与验收标准 | 全体组员先读 |
| [建模设计报告](reports/ANALYSIS_MODELING_REPORT.md) | 变量、方程、初边值条件、收缩坐标、数值方法与输出接口 | 建模、编程负责人重点读 |
| [第一问完整建模过程](reports/Q1_MODELING_PROCESS.md) | 假设依据、守恒推导、离散、数值验证、答案和论文写作证据 | 第一问论文写作与交叉核查 |
| [第二问模型规范](Q2_MODEL_SPEC.md) | 变物性热湿耦合、长期环境、门禁与来源追踪 | 第二问论文写作与交叉核查 |
| [第二问结果与验证](reports/Q2_RESULTS_REPORT.md) | 表3–4、72 h端点、误差和解释边界 | 建模、编程与论文负责人 |
| [第三问结果与验证](reports/Q3_RESULTS_REPORT.md) | 全域临界时间、表5、误差、敏感性和交付 | 建模、编程与论文负责人 |
| [第四问结果与验证](reports/Q4_RESULTS_REPORT.md) | 收缩域临界时间、表6、2×2对照和验证 | 建模、编程与论文负责人 |
| [执行待办清单](todo.md) | 认领任务、同步进度、检查四问及提交材料是否齐全 | 全体组员持续更新 |

### 四问路线

| 问题 | 核心工作 | 对应产物 |
| --- | --- | --- |
| 1 | 建立圆柱径向传热与非线性水分扩散模型 | 表1–2、result1.xlsx |
| 2 | 用附录3建立全过程变物性热湿耦合模型 | 表3–4、result2.xlsx |
| 3 | 定位全域最大含水率低于0.15 kg/kg的时刻 | 烘干时长、表5、result3.xlsx |
| 4 | 引入实测半径收缩及附录4物性 | 烘干时长、表6、result4.xlsx |

### 小组开始工作的第一步

1. 全组通读指导计划，确认长期环境、传质边界、潜热和材料收缩的基准假设。
2. 认领A（机理与推导）、B（数值与数据）、C（论文与核查）三个角色，并在待办任务后标注负责人。
3. 按下列结构准备小组已有的题面和附件。数据文件名、单位与字段约定见建模设计报告；仓库同时包含指导文档和已验证的第一问实现。
4. 问题一至四的“输入—求解—验证—导出—报告”链路已建立；第四问PR外部交付待完成。

```text
A题/
  A题.pdf
  附件/
    附件1.xlsx
    附件2.xlsx
    附件3/
      result1.xlsx
      result2.xlsx
      result3.xlsx
      result4.xlsx
```

### 协作与验收约定

- 每项任务在 `todo.md` 认领，实际完成并核查后再勾选。方案变更同步写入 `plan.md` 和建模设计报告的对应位置。
- 编程、建模和论文改动尽量分开提交；需要交叉审核的改动使用分支和Pull Request，说明改了什么以及验证结果。
- 参数变更要记录依据、单位和影响范围；同一组结果生成论文表格、图表和Excel，避免多处手填出现不一致。
- 首先检查全域达标条件、开尔文转换、变系数散度和第四问动态表面列，再做网格收敛、通量平衡与敏感性分析。
- 第四问同时改变物性和半径，用2×2对照实验分别解释两者的影响。
- 建模假设、数值验证和实验验证应分别表述；正式排版与提交格式在论文阶段按比赛要求核对。

阶段出口、完整文件清单与详细时间安排见[指导计划](plan.md)。

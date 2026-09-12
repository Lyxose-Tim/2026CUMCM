# 2026CUMCM A题：药材的烘干问题

本仓库包含四问的一维圆柱径向热湿模型、数值验证、题面表1–6、四份 Excel、论文图源和复现入口。当前分支是针对四问独立审议的综合返修，不表示已自动合并或完成正式论文提交。

## 当前结果

| 问题 | 模型与范围 | 正式结论 |
|---|---|---|
| Q1 | 附录2，0–1800 s | 表1–2与 result1.xlsx |
| Q2 | 附录3变物性，0–72 h | 表3–4与 result2.xlsx |
| Q3 | 固定半径，全域 C<0.15 | 57.4740097759 h |
| Q4 | 附录4与收缩半径，全域 C<0.15 | 51.0920106837 h |

Q2 的 72 h 是全过程情景范围，Q3/Q4 才回答全域达标临界时间。四位小数是交付显示格式，不代表模型具备四位真实精度。

## 现行模型口径

- Q1 使用附录2；Q2/Q3 从 t=0 全程使用附录3；Q4 使用附录4。
- 中心为对称边界，表面使用题设尺度下的有效换热和传质 Robin 边界。
- 环境 0–4 h 逐段线性插值，之后主情景保持最后一小时均值。
- Q4 使用材料坐标 xi=r/R(t)、径向仿射收缩和半径分段线性插值；PCHIP 与输入扰动只作结构情景。
- 停止事件读取全部计算节点的最大干基含水率，不以表面值或平均值代替。
- 模型不显式加入潜热，经验密度只用于有效热容量；结果不声称为完整多相守恒或实验验证。

完整推导与解释边界见 [四问建模总报告](reports/ANALYSIS_MODELING_REPORT.md)。

## 关键证据

- [Q1 模型与结果](reports/Q1_MODEL_SPEC.md)
- [Q2 模型规范](reports/Q2_MODEL_SPEC.md)
- [Q2 结果与验证](reports/Q2_RESULTS_REPORT.md)
- [Q3 模型、结果与验证](reports/Q3_RESULTS_REPORT.md)
- [Q4 模型、结果与验证](reports/Q4_RESULTS_REPORT.md)
- [独立审议整改闭环](reports/INDEPENDENT_REVIEW_REMEDIATION.md)
- [总结果索引](reports/RESULTS_REPORT.md)

论文主图位于 figures/paper，单问支撑图位于 figures/q1、figures/q2、figures/q3 和 figures/q4。每张数据图均有对应 CSV 与版本化哈希清单；技术路线另保留 DrawIO 源。

## 复现

使用 Python 3.12 并安装 requirements.lock.txt。原始数据目录需含 A题.pdf、附件1.xlsx、附件2.xlsx 与四份模板，实际路径通过 --data-root 传入。

常用入口：

- python -m pytest -q
- python -m q1.export
- python -m q2.export
- python -m q3.export --data-root 你的A题目录
- python -m q4.export --data-root 你的A题目录
- python -m q2.figures；python -m q3.figures；python -m q4.figures
- python paper_figures.py
- python -m common.portable_audit

Excel 默认由普通 Python/openpyxl 生成，不要求 Codex 私有作者工具。完整重算命令、产物含义和无 Git 归档核查见 [REPRODUCE.md](REPRODUCE.md)。

## 目录

| 路径 | 内容 |
|---|---|
| configs | 四问配置、误差预算和输入摘要 |
| q1–q4 | 模型、求解、验证、导出、报告入口 |
| common | 版本化哈希、工作簿与便携审计工具 |
| results | 数值归档、表格、工作簿和机器证据 |
| figures | 单问支撑图和六张论文主图 |
| reports | 模型规范、结果报告、验证报告与审议闭环 |
| tests | 数学、数值、交付和反例测试 |

## 尚未声称完成

仓库尚不包含内部温湿实测标签，不能报告实验准确率或统计置信区间。正式竞赛论文的模板选择、摘要、参考文献、页数、最终编译与提交规则仍需按当届通知完成。

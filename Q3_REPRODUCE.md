# 问题三复现说明

## 正式口径

configs/q3.json 是唯一配置事实源。正式案例为 N=40960 的收紧 BDF；N=5120、10240、20480 和同网格时间设置用于收敛与回归，不再把 N=20480 写成正式答案。

Q3 从原始初值独立积分，沿用附录3、固定半径和 Q2 的主环境延拓。结果模板只规定格式，不参与数值求解。

## 从头计算

在仓库根目录、Python 3.12 与 requirements.lock.txt 环境中执行：

1. python -m pytest -q
2. python -m q3.run --data-root 你的A题目录 --workers 1
3. python -m q3.refine --data-root 你的A题目录
4. python -m q3.validation
5. python -m q3.export --data-root 你的A题目录
6. python -m q3.figures
7. python -m q3.reports

q3.run 计算基础、时间设置和敏感性算例；q3.refine 顺序执行 N=40960 算例以控制内存峰值。导出使用普通 Python/openpyxl，并立即回读 result3.xlsx。

## 事件证据

每个完成算例保存：

- run.json：配置、输入、源码、求解设置、根区间、诊断与文件摘要。
- fields.npz：60 s 输出场、几何、初始状态、根包围状态和根前/根/根后完整状态。
- accepted_steps.csv：接受步上的全域最大值、位置、中心、平均、表面与累计平衡。
- verification.json：空间阶、时间设置、Q2 回归、事件斜率和敏感性。
- table5.csv、result3.xlsx、figure_data 与 PDF：由同一正式运行派生。

事件函数读取全部 N+1 个计算节点。21 个 Excel 半径只用于交付，不能作为全域事件状态。根处通常为等号，严格低于由根后 1 s 的完整状态复核。

## 强制新积分

要避免正式缓存，给 q3.run 与 q3.refine 指定同一个全新输出目录，再对该目录运行 q3.validation。经济型独立复算可以只计算 base_N5120，并用 q3.reproduce 的 --fresh 与正式同网格归档比较。

不同平台重新积分的浮点结果按已公布的场和事件预算比较，不要求压缩文件字节相同。已有正式归档的只读核验仍要求版本化文件摘要完全匹配。

## 便携核验

q3.validation、q3.export、q3.figures、q3.reports 和 common.portable_audit 均不依赖私有作者工具。源码 ZIP 中没有 .git 时，code_commit 可以为空，但配置、源码和交付文件摘要仍必须通过。

当前没有内部温湿实测标签。空间、时间、根误差和四位小数舍入都不得表述为实验准确率或统计置信区间。

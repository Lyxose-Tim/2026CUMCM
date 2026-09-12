# 四问复现与验收

## 1. 环境

推荐 Python 3.12。仓库根目录依次运行：

1. python -m venv .venv
2. Windows：.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
3. Linux/macOS：.venv/bin/python -m pip install -r requirements.lock.txt
4. python -m pytest -q

原始数据不入库。data-root 指向同时包含 A题.pdf 和附件目录的 A题根目录。配置会核对题面、附件和模板摘要；不应通过修改摘要绕过来源不一致。

建议在高密网格计算前设置 OPENBLAS_NUM_THREADS=1、OMP_NUM_THREADS=1，并预留足够内存和运行时间。Q1 的正式内部时空场原始规模约 590 MB；Q2 的工作簿需写入并回读 10886400 个结果单元格。

## 2. 从头重算

### Q1

1. python -m q1.run --data-root 你的A题目录
2. python -m q1.export
3. python -m q1.figures
4. python -m q1.reports

Q1 灵敏度另见 reports/Q1_SENSITIVITY_SPEC.md。

### Q2

统一入口：

python -m q2.reproduce --data-root 你的A题目录

它按顺序运行数值求解、普通 Python 工作簿导出、图表和报告。正式归档含 t=0，result2.xlsx 含 1–259200 s。

### Q3

1. python -m q3.run --data-root 你的A题目录 --workers 1
2. python -m q3.refine --data-root 你的A题目录
3. python -m q3.validation
4. python -m q3.export --data-root 你的A题目录
5. python -m q3.figures
6. python -m q3.reports

正式案例由 configs/q3.json 唯一指定为 N=40960。详细算例、事件状态和缓存规则见 Q3_REPRODUCE.md。

### Q4

统一入口：

python -m q4.reproduce --data-root 你的A题目录 --workers 1

该入口计算 A–D 机制组、空间/时间/方法组、五个结构敏感性情景、验证、工作簿、图和报告。C 案例会延长到实际事件；正式主案例为附录4、收缩半径、N=20480 的收紧 BDF。

### 论文主图

python paper_figures.py

输出六张主图、对应 CSV 和 results/paper_figure_manifest.json。图1同时保留 figures/paper/fig01_model_roadmap.drawio。

## 3. 只核验已有交付

已有正式数值归档时，无需重新积分即可执行：

1. python -m pytest -q
2. python -m q3.validation
3. python -m q4.validation
4. python -m q1.export
5. python -m q2.export
6. python -m q3.export --data-root 你的A题目录
7. python -m q4.export --data-root 你的A题目录
8. python -m q2.figures
9. python -m q3.figures
10. python -m q4.figures
11. python paper_figures.py
12. python -m q2.reports
13. python -m q3.reports
14. python -m q4.reports
15. python -m common.portable_audit

导出入口会生成工作簿并立即独立回读，不需要 Codex 捆绑的 Node 或 Artifact Tool。Node 脚本仍保留为兼容与格式预览路径，不是完整复现的必需依赖。

## 4. 证据结构

- 数值 run.json 或 archive/manifest.json：配置、输入、依赖、源码记录、运行设置和数据文件摘要。
- verification.json：数学、物理、空间、时间、方法与事件门禁。
- export_verification.json：工作簿尺寸、数值类型、四位显示、空白掩码和逐格回读。
- figure_manifest.json：生成器、验证文件、CSV 与 PDF 的版本化摘要。
- report_manifest.json：报告生成器和引用证据摘要。
- results/paper_figure_manifest.json：六张论文主图及图源。

文本使用 sha256-text-lf-v2：严格按 UTF-8 解码，将 CRLF 和单独 CR 统一为 LF 后计算 SHA-256。二进制使用 sha256-raw-v1。换行变化可以跨平台复现，真实文本或数值变化仍会被拒绝。

## 5. 无 Git 与干净检出

common.portable_audit 只依赖文件内容摘要，不要求 .git。它可在 GitHub 源码 ZIP 解压目录中核对 Q2–Q4 数值、工作簿、图和报告。存在 .git 时，数值记录中的 code_commit 用于说明生成背景；无 .git 时不会跳过文件级核验。

提交前应分别在以下环境执行只读审计：

1. 使用 LF 的干净检出目录。
2. git archive 生成并解压的无 .git ZIP。

跨平台浮点重新积分允许在已公布预算内变化，不要求 NPZ 压缩字节逐位相同；已有归档和交付文件的摘要核验则要求内容与记录严格一致。

## 6. 解释限制

数值收敛、Excel 零差回读和文件摘要只能证明实现与交付一致，不能证明模型具有实验准确率。长期环境、半径延拓、有效 Ce、潜热、密度和端面属于模型层不确定性，应与空间、时间和根误差分开报告。

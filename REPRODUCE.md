# 第一、二问复现

范围为0–1800 s的有效径向基准。先读[模型契约](reports/Q1_MODEL_SPEC.md)。原始题面/附件由成员自行放在本地，不入库、不覆盖。所有参数在 `configs/q1.json`；入口遇到题面、环境或模板哈希变化会报错，需先核查来源，不可直接改哈希绕过。

## 环境

数值环境为Python 3.12，实际依赖版本锁定在 `requirements.lock.txt`。PowerShell示例，在仓库根目录运行：

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m q1.run --data-root 'E:/Code_from_class/2026A/A题'
```

`--data-root` 是含 `A题.pdf` 和 `附件/` 的目录，按本机实际位置修改。只读取附件1的前31点作为环境驱动。Linux/macOS对应解释器为 `.venv/bin/python`。图中文字需系统存在 Microsoft YaHei、SimHei、Noto Sans CJK SC或WenQuanYi Zen Hei之一；脚本检查并记录实际字体，不静默输出缺字图。

求解先运行独立测试，随后执行全部网格、时间与Radau复核、完整级数和独立通量积分。失败退出非零且归档状态为 `diagnostic_only`，禁止正式导出；软件异常保留 `failure.json`。用户已批准网格上限从10240扩为20480，误差预算未放宽。运行所需内存随N增长，最终全精度矩阵原始大小约590 MB；分块无损归档避免单个GitHub文件过大。

## 统一导出

```powershell
./.venv/Scripts/python.exe -m q1.export
./.venv/Scripts/python.exe -m q1.figures
```

Excel作者端使用Codex捆绑Node与 `@oai/artifact-tool`，不依赖数值虚拟环境。通过客户端 `load_workspace_dependencies` 找到Node和node_modules，在仓库中创建被忽略的node_modules目录联接（Windows `New-Item -ItemType Junction`，其他系统用符号链接）。使用返回的Node路径执行：

```powershell
& '<bundled-node-path>' scripts/build_result1.mjs
./.venv/Scripts/python.exe -m q1.check_export
./.venv/Scripts/python.exe -m q1.reproduce --data-root 'E:/Code_from_class/2026A/A题'
./.venv/Scripts/python.exe -m q1.reports
```

本机作者端运行时版本、命令和视觉检查记录见 `results/q1/authoring.json`。`.scratch/`只存中间JSON与预览；正式Excel固定为 `results/result1.xlsx`。表格为数值而非字符串，四位显示采用 `Decimal(str(float))` 的ROUND_HALF_UP。本文表格、Excel和图源数据都来自同一归档，不手填结果。

## 归档与核查

- `results/q1/archive/manifest.json`：参数、输入哈希、基础代码提交、源文件哈希、依赖版本和运行命令。
- `field_*.npz`：每秒完整内部场，包括t=0；float64，[时间,半径]，通过哈希核验后拼接。
- `geometry.npz`：节点m、控制体m³、面m²及21个报表节点索引。
- `convergence.json` / `grid_outputs.npz`：每组网格完整1801×21输出、最大差位置、早期表面和实际阶。
- `accepted_steps.csv`：所有接受步的时刻、步长、极值、表面值及体积平均；非法试探值另记录，未修改物性。
- `balance.csv`：所有每秒时刻的热/水分余额及独立求积复核差。
- `bessel_T.csv` / `bessel_C.csv`：常系数解与完整级数逐点对照。
- `verification.json`：数值门槛；`export_verification.json`：独立Excel/正文表/图源回读门槛；`reproduction.json`：复现复核。三者与人工交叉审核分开。

若只检查已有归档，运行导出和回读命令即可核对表图。数值复现需重新运行求解；不同平台浮点值不必逐位相同，按时间/空间预算比较全输出，不能仅比较Excel四位值。第二问已完成；第三、四问及实物实验验证仍未进行。

## 第一问评测后续：灵敏度与鲁棒性设计

本扩展叠加于PR #2的基准，设计见 `reports/Q1_SENSITIVITY_SPEC.md`，参数情景固定在 `configs/q1_sensitivity.json`。复用同一Python 3.12及锁定依赖，无新增依赖。实际运行使用已存在的基准工作区虚拟环境；其他机器按上文创建环境即可。PowerShell中先限制每个进程的BLAS线程，以避免两个独立算例争用大量线程：

```powershell
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
New-Item -ItemType Directory -Force -Path .scratch | Out-Null
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m q1.sensitivity --data-root 'E:/Code_from_class/2026A/A题' --workers 2
./.venv/Scripts/python.exe -m q1.sensitivity_report
```

`--workers 1`可降低并发内存需求。两个工作进程只运行相互独立的情景，不改变单次积分算法。总计33次积分：13组生产场，六组极端情景各补两组较粗网格及一次更严BDF，共18次，另有两次Radau。

所有结果进入 `results/q1_sensitivity/`，原 `results/q1/`、`results/result1.xlsx`、`figures/q1/` 和原始输入逐文件哈希保护。每个 `runs/<case>_N<...>_<method>_<level>/` 保存：

- `series.npz`：1801×21每秒正式径向场（含内部t=0）、完整网格体积平均，以及1800 s完整内部剖面/体积权重。灵敏度归档不重复保存每组590 MB的全部内部时空场；若需其他内部时空点，应按记录的配置重新运行。
- `run.json`：该组实际参数、输入/代码哈希、求解设置、运行诊断、试探失败、守恒/表面检查与各数据文件哈希。
- `accepted_steps.csv`：所有接受步的极值、表面与体积平均响应；`balance.csv`：每秒独立通量余额和求积差。
- 总目录的 `verification.json`：全输出差、早期表面、最大差位置、体积平均差、实际收敛阶、端点响应和弹性；`manifest.json`：版本、输入、命令、运行列表和总体状态。
- `figure_data/`及`figures/q1_sensitivity/`：可回读的数值CSV和由它们生成的矢量PDF；`export_verification.json`记录图源/报告/图文件哈希及独立端点回读差。

每次开始都重查输入和基准哈希。缓存只在数值源文件、依赖锁定文件、配置、该组参数和产物哈希一致时复用；改变数值代码后需指定新的 `--directory`，不能把新旧计算混在一起。新运行开始会将总体状态置为running；未完成或未通过的记录禁止正式报告导出。

若需**重新积分复现**而非仅校验缓存，使用新目录：

```powershell
./.venv/Scripts/python.exe -m q1.sensitivity --data-root 'E:/Code_from_class/2026A/A题' --directory .scratch/q1-sensitivity-reproduction --workers 2
```

比较各 `series.npz` 的每秒21半径场和体积平均，采用原时间预算而非压缩文件逐字节一致性。浮点矩阵不一定跨平台逐位相同。当前使用明确的 `sha256-text-lf-v1` 方案：Python/JSON/CSV/Markdown/锁定依赖等文本只统一CRLF→LF；其他字节变化仍会被拒绝。NPZ、PDF、Excel及原输入维持原始字节SHA256。源码同时保留原始字节哈希，便于诊断换行差异。

另提供单组新进程复现入口，默认重算D前因子−20%的N=20480生产情景；输出目录必须不存在，保证不能被缓存命中。实际比较覆盖每秒21个半径和体积平均，结果记录在 `reproduction.json`：

```powershell
./.venv/Scripts/python.exe -m q1.sensitivity_reproduce --data-root 'E:/Code_from_class/2026A/A题' --output .scratch/fresh-sensitivity-reproduction
```

已归档的33次情景及复核之外，本轮额外执行了这一次新进程积分。此复现不是33组全部重跑的记录；全组重跑使用上文新目录命令。

最后运行入库的审计入口，重跑测试并记录测试源码、当前数值源码与全部产物的一致性。当前完整测试集为37项：

```powershell
./.venv/Scripts/python.exe -m q1.sensitivity_audit --run-tests --write
```

仅检查已有证据而不修改文件，运行 `python -m q1.sensitivity_audit`。该命令会检查当前计算源码、报告生成器、测试源码、各组run文件与实际数据、单组重新积分的记录；不能仅由旧的 `numerically_verified` 字段绕过当前源码核验。源文件改变后必须重新计算；报告生成器改变后须重新导出、测试和审计。旧版无便携指纹的归档不会被静默认定为当前代码已验证。

manifest中的 `code_commit` 表示启动调用时的源码提交；各组run保存其实际生成时的提交；审计保存检查时的提交。打包结果的提交发生在计算之后，三者不必相等，当前head的适用性由13个明确计算依赖文件的 `source_digest` 逐文件校验。文件清单包含共享归档模块；新增/遗漏依赖会导致范围检查失败。测试与报告生成代码另有摘要检查。

所有灵敏度入口均可在GitHub源码ZIP解压目录运行，不要求 `.git` 或Git可执行程序；此时 `code_commit` 为null，完整源码摘要仍必需。目录仅位于其他仓库内部时也不借用父仓库的提交。无Git不允许跳过源码或数值检查。审核根因与整改说明见[PR #5审核回应](reports/Q1_PR5_REVIEW_RESPONSE.md)。

本轮已用实际 `git archive --format=zip <结果提交>` 解压到仓库外验证这些入口，并在其中独立重算一个情景；详见 `results/q1_sensitivity/zip_portability.json`。从ZIP运行主入口时，匹配的33组归档可作为缓存接受审计；这与“33组全部重新积分”明确区分。要执行全部重新积分，仍需使用上文的新输出目录命令。

`reports/Q1_ROBUSTNESS_DESIGN.md`只交付第一问联合/环境扰动设计与CV适用范围，没有暗中执行随机50次或增强潜热模型；第二问的长期环境对照由独立Q2结果记录，不应倒填为第一问实验。

## 第二问：72 h 变物性热湿耦合

第二问配置位于 `configs/q2.json`，模型契约见 `Q2_MODEL_SPEC.md`。原始输入目录必须同时包含 `A题.pdf`、`附件/附件1.xlsx` 和 `附件/附件3/result2.xlsx`；三者哈希与配置不符时入口会拒绝运行。统一复现命令为：

```powershell
./.venv/Scripts/python.exe -m q2.run --data-root 'E:/Code_from_class/2026A/A题'
./.venv/Scripts/python.exe -m q2.export --node '<bundled-node-path>'
./.venv/Scripts/python.exe -m q2.figures
./.venv/Scripts/python.exe -m q2.reports
```

也可用 `python -m q2.reproduce --data-root <A题目录> --node <bundled-node-path>` 顺序执行全部步骤。正式数值先按 N=40 至 20480 倍增加密，连续两级满足空间预算后，计算收紧 BDF、Radau、Q1 常物性退化对照以及两个长期环境情景。完整计算在当前机器耗时较长；只核验已有归档和 Excel 时可直接运行后三个入口。

`results/q2/archive/` 保存 0–259200 s、21 个正式半径的 float64 分块及 N=20480 的最终全网格状态。`result2.xlsx` 保存 1–259200 s；`q2.check_export` 流式回读两张 259201×22 工作表的全部 10886400 个结果单元格。

Artifact Tool 已用于写入、检查和渲染 12 行格式蓝图。完整 10886400 格工作簿在 16 GB V8 堆上限仍内存不足，因此最终文件由 `scripts/build_result2_stream.py` 以 openpyxl write-only 模式生成；该降级、工作簿 SHA-256、尺寸和逐格零差结果记录在 `results/q2/export_verification.json`。数值源码与导出源码分别保留摘要，改动数值核心必须重算，改动导出器必须重新导出和回读。

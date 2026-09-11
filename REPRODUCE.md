# 第一问复现

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

若只检查已有归档，运行导出和回读命令即可核对表图。数值复现需重新运行求解；不同平台浮点值不必逐位相同，按时间/空间预算比较全输出，不能仅比较Excel四位值。未进行第二至第四问求解，亦未进行实验验证。

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

比较各 `series.npz` 的每秒21半径场和体积平均，采用原时间预算而非压缩文件逐字节一致性。浮点矩阵不一定跨平台逐位相同；源文件原始字节哈希会记录不同换行格式，缓存拒绝混用属预期行为。31项测试的最新实际运行记录与新增图的视觉检查另存灵敏度目录，不能由求解器success代替。

另提供单组新进程复现入口，默认重算D前因子−20%的N=20480生产情景；输出目录必须不存在，保证不能被缓存命中。实际比较覆盖每秒21个半径和体积平均，结果记录在 `reproduction.json`：

```powershell
./.venv/Scripts/python.exe -m q1.sensitivity_reproduce --data-root 'E:/Code_from_class/2026A/A题' --output .scratch/fresh-sensitivity-reproduction
```

已归档的33次情景及复核之外，本轮额外执行了这一次新进程积分。此复现不是33组全部重跑的记录；全组重跑使用上文新目录命令。

`reports/Q1_ROBUSTNESS_DESIGN.md`只交付联合/环境扰动设计与CV适用范围，没有暗中执行随机50次、增强潜热模型或第二至第四问。

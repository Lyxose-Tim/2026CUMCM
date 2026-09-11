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

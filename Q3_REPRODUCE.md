# 问题三复现说明

需要Python 3.12及仓库`requirements.lock.txt`；在本工作区新建虚拟环境。不要把其他任务工作区作为输出目录。

```powershell
py -3.12 -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
$env:PYTHONUTF8='1'
$env:OPENBLAS_NUM_THREADS='1'
$env:OMP_NUM_THREADS='1'
./.venv/Scripts/python.exe -m q3.run --data-root 'E:/Code_from_class/2026A/A题' --workers 2
./.venv/Scripts/python.exe -m q3.refine --data-root 'E:/Code_from_class/2026A/A题'
./.venv/Scripts/python.exe -m q3.validation
./.venv/Scripts/python.exe -m q3.export --data-root 'E:/Code_from_class/2026A/A题'
```

`configs/q3.json`是正式选择和算例集合的事实源：`formal_case=tight_N40960`，`grids`列出全部四档网格，`temporal_cases`和`temporal_comparisons`列出时间收敛设置，`refinement_cases`列出追加的N=40960基准和收紧解。历史初选单独保存在`initial_formal_case`。`q3.run`默认执行前三档基准、两组时间检查和六个敏感性情景；`q3.refine`读取配置并顺序执行两组加密算例，以限制内存峰值。也可以用`q3.run --cases tight_N40960`单独执行配置中的正式算例。验证、导出和报告均检查并沿用当前配置的正式选择，共13个算例。

原始输入目录须包含题面PDF、附件1、结果模板result2及result3；result2模板只由继承的Q2输入核验函数读取，不作为第三问数值来源。均不读取附件2。修改物性/边界须作为新模型情景记录，不得调节参数迎合时长。

Excel作者端使用Codex `load_workspace_dependencies`返回的捆绑Node及`@oai/artifact-tool`。按该工具返回的包路径创建被Git忽略的node_modules目录联接，执行：

```powershell
& '<bundled-node-path>' scripts/build_result3.mjs
./.venv/Scripts/python.exe -m q3.check_export
./.venv/Scripts/python.exe -m q3.figures
./.venv/Scripts/python.exe -m q3.reports
./.venv/Scripts/python.exe -m q3.audit
```

Linux/macOS使用`.venv/bin/python`和符号链接。图表需要Microsoft YaHei、SimHei或Noto Sans CJK SC。命令在仓库根目录运行。数字单元格为数值类型，以Decimal ROUND_HALF_UP统一四位小数；底层临界时间保留全精度。

## 输出含义

- `results/q3/runs/<case>/run.json`：实际参数、输入与模板哈希、环境延拓、求解器、数值源码指纹、文件哈希、根区间和诊断。
- `fields.npz`：每60 s的21半径场及全网格加权平均/极值；t=0、几何、均匀初始全状态；包围区间的左/根/右完整状态，以及根前1 s/根/根后1 s完整状态。
- `accepted_steps.csv`：全部接受步时间、全域极值与位置、中心/表面/平均、温度包络、径向增加量及累计水分余额。中点也在积分中检查，诊断极值覆盖两者；未归档每个中点的完整状态。
- `verification.json`：每个run的状态核查、空间阶和时间误差、Q2对照、阈值时间敏感性及记录绑定。
- `table5.csv`、`table5.md`：同源全精度与四位正文表；`results/result3.xlsx`为提交模板输出。
- `figure_data/*.csv`、`figures/q3/*.pdf`与`figure_manifest.json`：独立图源及其摘要。
- `export_verification.json`：真实Excel全量回读；`visual_qa.json`：人工视觉检查记录。

数组均为float64，温度与含水率在完整状态向量中前后拼接，各有N+1项。半径为m，Excel半径为cm；内部时间为s，正文为h。完整时空内部场并未全部保存，重新求其他半径/时刻须按同配置积分；不得将21半径采样当作全域状态。

## 缓存、重新积分与现有交付核查

已有完整run仅在当前源码、实际参数、配置、输入和产物哈希匹配时复用。要强制新积分，给两个数值命令相同的新`--directory`目录，再用`q3.validation --directory <新目录>`核查；这样不能命中正式缓存。更经济的独立新进程复算可以仅运行：

```powershell
./.venv/Scripts/python.exe -m q3.run --data-root 'E:/Code_from_class/2026A/A题' --directory .scratch/q3-fresh --cases base_N5120 --workers 1
./.venv/Scripts/python.exe -m q3.reproduce --fresh .scratch/q3-fresh
```

用全精度NPZ在相同时刻比较原N=5120结果，不能只检查Excel舍入。跨平台浮点结果允许在已公布数值误差预算内变化，不要求压缩文件字节相同。仅审查现有交付时可调用`q3.validation`（重跑测试与归档核对，复用既有积分证据）、`q3.check_export`与`q3.reports`。

已有运行若只有`status=running`而进程已结束，视作中断，不当成可用缓存。先将该不完整目录移到自己的诊断区，再重跑对应算例；已经完成且摘要匹配的其他算例可以复用。正式数值计算、缓存复用与单组新进程复现分别记录。

数值误差估计与长期环境假设不确定性分别报告。当前没有内部场实验标签，不存在本任务的实验准确率或统计置信区间。

`q3.audit`是已有交付的只读最终审计：绑定当前源码、测试、归档、Excel、图、报告、独立复算及视觉检查。重新生成交付后，实际渲染并检查Excel首尾与全部PDF，更新`visual_qa.json`（绑定真实文件）；不要将未查看的图标记为已检查。

Git checkout中的最后步骤必须按以下顺序执行：

1. 提交全部源码与交付文件（此时旧audit.json尚未刷新）。
2. 运行`python -m q3.audit --write`，绑定当前HEAD的完整已提交内容，唯一排除路径为`results/q3/audit.json`。
3. 单独提交新audit.json，再运行`python -m q3.audit`；干净新克隆也应通过。后续任何其他已提交内容变化均须重新审计；未提交或未跟踪且未忽略的文件也会阻断Git审计。

不能将HEAD字面量写进受跟踪的audit.json后再提交，并要求它等于新HEAD：审计文件自身改变了提交哈希，会产生自引用循环。schema v2因此将旧`code_commit`字段拆为`audited_content_commit`与`git_tree`。前者是生成审计时包含全部交付内容的提交；后者对该提交的`git ls-tree -r -z --full-tree`除审计自身外的全部条目计算SHA-256，包含路径、文件模式及Git对象摘要。审计同时验证来源提交、当前HEAD的树与记录三者一致，并实时输出当前HEAD；不是接受任意旧提交。旧schema、陈旧树、工作区改动及Git读取失败均拒绝通过。一次仅修改审计文件或提交元数据、未修改被审计内容的提交可通过。

源码ZIP无`.git`时，明确输出Git核查已跳过，仍核对全部便携源码与交付文件摘要；存在`.git`但因safe.directory等原因读取失败时不能冒充ZIP。数值run.json的`source.code_commit`保留实际积分启动时提交，配合精确数值源码摘要解释，不表示最终交付HEAD。

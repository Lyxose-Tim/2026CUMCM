# 问题三依赖与协作记录

## 固定起点

- 仓库：Lyxose-Tim/2026CUMCM。
- 最新核对main：`8fdcb81a5ac5c695531aa3e2e86839912e55962a`。
- 上游PR：[问题二 #6](https://github.com/Lyxose-Tim/2026CUMCM/pull/6)，分支`feat/q2-coupled-drying`。
- 固定依赖提交：`aa1d1b65ec7349c112fc2da0eef8110858a8a00a`。
- 2026-09-12启动及实施中再次核对：PR为OPEN、reviewDecision为CHANGES_REQUESTED；当前head作者声明修复已上传，最新独立审查尚未批准。完整快照在`results/q3/dependency_snapshot.json`。
- 本任务独立检出：`.worktrees/q3-fixed-drying`；分支`feat/q3-fixed-drying`。发布检出`.publish/2026CUMCM`仅作为clone对象来源，没有切换、修改或提交该检出。
- 启动时开放PR只有#1和#6，todo内问题三尚未认领；任务由Codex执行，没有伪造小组成员认领。

## 审查与实际复核

已读README、plan、todo、分析报告、Q2模型/结果/验证报告及q2全部相关模块，查阅问题二审核任务必要结论和GitHub review。项目根、父目录及仓库中未发现适用AGENTS.md或CONTRIBUTING文件。

Q2此前审核未发现变物性与耦合核心的阻塞错误，但曾发现空单元格放行、报告状态/实际工作簿绑定、Windows换行指纹三类缺陷。本次在固定最新提交上实际执行现有回归测试，并调用Q2正式报告的`validated_export('results/q2')`：当前实际工作簿哈希、通过状态、源码及文本换行绑定可通过。Q3完整测试集也包含其修复反例。此本地复核不能替代独立审核人的批准；没有代替小组批准或合并PR #6。

同网格N=20480、同收紧设置的Q3与Q2归档在3449个共同输出时刻、21半径逐点比较，温度最大差4.9738e−14 °C，含水率最大差2.3753e−13 kg/kg。Q2归档仅有21半径时间序列与72 h完整末态，因此Q3从均匀原始初值重算完整网格事件，没有由Excel舍入数据倒推。

## 文件保护与提交

q1/、q2/、两问配置、既有结果工作簿与归档、原图均不修改。代码新增在q3/，输出在results/q3/、results/result3.xlsx及figures/q3/。共享文档只更新问题三进度和指向，不重写他人参考分支。提交分为模型/计划、求解代码、验证与导出、实际结果及协作入口。

问题三草稿PR以`feat/q2-coupled-drying`为base，仅展示Q3差异，明确叠加依赖。上游尚未合并，不直接推main，不合并任何PR。后续上游若更新/合并，应先检查变化再同步依赖和PR base，不能仅依据“文件已上传”推断批准。

## 原始输入与环境

题面PDF SHA-256：`052d8014bff5727c019b72e44fdffaf5c145ce04050dd938baaf3527db331736`。

附件1 SHA-256：`7ef32870abeef420b89560b2530ff60dfe4255917805151d89988d0311af9dd7`。结果3模板的实际哈希保存在所有run.json的`identity.inputs.q3_template`中；输入内容未修改。

在独立工作区新建Python 3.12虚拟环境并按requirements.lock.txt安装依赖。Excel使用Codex捆绑Artifact Tool和Node作者端。q3数值与现有q2使用相同SciPy/Numpy接口，实际版本随各次run保存。文本指纹统一CRLF→LF，二进制NPZ/XLSX/PDF保持字节哈希。

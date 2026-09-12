"""Generate reviewable reports only from currently bound passing evidence."""
import json
from pathlib import Path

import numpy as np

from q2.inputs import sha256
from q2.provenance import portable_artifact_sha256
from q3.validation import verified
from q3.export import delivery_sources,rounded


def require_export(directory="results/q3",workbook="results/result3.xlsx"):
    directory=Path(directory)
    e=json.loads((directory/"export_verification.json").read_text(encoding="utf-8"))
    if e.get("passed") is not True:
        raise ValueError("Excel verification failed or absent")
    if e["workbook_sha256"] != sha256(workbook):
        raise ValueError("Excel verification belongs to a different workbook")
    if (e["delivery_sources"] != delivery_sources()
        or e["verification_sha256"] != portable_artifact_sha256(directory/"verification.json")
        or e["table5_sha256"] != portable_artifact_sha256(directory/"table5.csv")):
        raise ValueError("Excel evidence is stale")
    return e


def make(directory="results/q3"):
    directory=Path(directory)
    v,r,f=verified(directory)
    e=require_export(directory)
    fig=json.loads((directory/"figure_manifest.json").read_text(encoding="utf-8"))
    if (fig["source_code_sha256"] != portable_artifact_sha256("q3/figures.py")
        or fig["verification_sha256"] != portable_artifact_sha256(directory/"verification.json")):
        raise ValueError("Stale figure source")
    for name,digest in fig["csv"].items():
        if portable_artifact_sha256(directory/"figure_data"/name) != digest:
            raise ValueError("Changed figure CSV")
    for name,digest in fig["pdf"].items():
        if sha256(Path("figures/q3")/name) != digest:
            raise ValueError("Changed figure PDF")
    root=r["root"];diag=r["diagnostics"]
    near=np.asarray(root["near_summary"])
    table=np.loadtxt(directory/"table5.csv",delimiter=",",skiprows=1)
    t5="| 时间 / h | 0 cm | 0.5 cm | 1 cm | 1.5 cm | 2 cm |\n|---:|---:|---:|---:|---:|---:|\n"
    t5+="\n".join("| "+" | ".join(f"{x:.4f}" for x in row)+" |" for row in rounded(table))
    sensitivity="| 情景 | 时间 / h | 相对同网格基准变化 / h | 变化 / % |\n|---|---:|---:|---:|\n"
    sensitivity+="\n".join(f"| {s['case']} | {s['time_h']:.6f} | {s['change_h']:+.6f} | {100*s['relative_change']:+.4f} |" for s in v["sensitivity"])
    title="# 问题三计算结果报告\n\n"
    text=title+f"""## 结论与适用范围

固定半径2 cm、附录3物性和问题二相同环境闭合下，全域含水率阈值的临界时间为

**t* = {root['time_h']:.10f} h = {root['time_s']:.12f} s**，按题目四位小数显示为 **{root['time_h']:.4f} h**（约{root['time_h']/24:.4f}天）。

正式结果采用N=40960、收紧BDF积分。当前估计数值时间误差量级为{v['estimated_numerical_time_change_s']:.6f} s；这不是严格误差界，也不包含环境、闭合及实物误差。初始72 h覆盖内已发生事件，没有为满足2–3天量级而调参。

数学上t*是严格达标集合的下确界；连续临界点通常为等号。根处全域最大值为{near[1,1]:.16f} kg/kg，最大值位置r={near[1,2]*100:.8f} cm。另保存的t*+1 s完整场已严格低于阈值，属于后验核查时刻，不替代最短时间定义。Excel及表5末行均列临界时间t*，四舍五入显示的0.1500不用于判断严格不等号。

## 表5 药材烘干过程水分浓度

{t5}

最后一行为临界结束状态。前面各行为6 h整数倍且不超过t*；时间由秒转换为小时，21个Excel半径中抽取0、0.5、1、1.5、2 cm。全精度表见`results/q3/table5.csv`。

## 准确末状态与阈值证据

| 状态 | 时间 / s | Cmax / (kg/kg) | 最大值半径 / cm | 体积平均 | 表面 |
|---|---:|---:|---:|---:|---:|
"""
    for label,row in zip(["根前1 s，未达标","临界根，等号","根后1 s，严格达标"],near):
        text+=f"| {label} | {row[0]:.12f} | {row[1]:.16f} | {row[2]*100:.8f} | {row[4]:.12f} | {row[5]:.12f} |\n"
    text+=f"""
最终二分包围区间为[{root['bracket_s'][0]:.12f}, {root['bracket_s'][1]:.12f}] s，g值分别为{root['bracket_g'][0]:.6e}、{root['bracket_g'][1]:.6e} kg/kg；原接受步包围区间为[{root['accepted_bracket_s'][0]:.9f}, {root['accepted_bracket_s'][1]:.9f}] s。每次根评价均读取全部40961个含水率节点，中心和表面为已有端点；无超调的空间重建最大值等于全部节点最大值。

阈值附近dCmax/dt≈{v['slope_C_per_s']:.12e} kg/(kg·s)。含水率误差1e−6 kg/kg对应约{v['C_error_1e_6_time_s']:.4f} s；四位小数舍入半宽5e−5对应约{v['rounding_5e_5_time_s']:.2f} s。因此不能由Excel中0.1500倒推严格停止时间。

## 长期环境与参数敏感性

0–4 h由附件1逐段线性插值；4 h后使用最后一小时61个观测的均值49.99893442622951 °C、0.04998754098360656 kg/kg。以下仅改变所列项，使用N=5120；变化量相对于同网格均值环境基准，避免混入正式网格差。

{sensitivity}

`terminal_hold`、`nominal`分别表示4 h后末值保持、50 °C与0.05 kg/kg保持；hm和D_prefactor分别乘0.9、1.1。情景网格的结束时间误差为数秒量级，主要参数/末值情景影响远大于该量级；名义环境与均值环境十分接近，其小差异按数值情景差解释，不声称实物可分辨。未对敏感性情景逐一重跑完整网格序列，也未将这些确定性情景当作统计置信区间。

## 图表与交付

| 论文图 | 对应CSV | 支持的结论 |
|---|---|---|
| `figures/q3/q3_moisture_curves.pdf` | `figure_data/response.csv` | 全域最大值与中心在后期重合；体积平均和表面提前降低，不能作停机依据 |
| `figures/q3/q3_threshold_zoom.pdf` | `figure_data/response.csv`及完整根状态 | 根前后符号、缓慢下降与数值误差量级 |
| `figures/q3/q3_radial_profiles.pdf` | `profiles.csv`、`endpoint_profile.csv` | 代表时刻径向梯度及低扩散率表层细节 |
| `figures/q3/q3_convergence.pdf` | `convergence.csv` | 网格时间差与实测收敛阶 |

`results/result3.xlsx`保留原模板Sheet1与表头语义，含{e['rows']}条时间记录、21个半径列。首行实际半径为0–2 cm每0.1 cm，首列时间s；从60 s开始，每60 s一行，末尾添加全精度临界时间并去重。数值单元格保留四位小数，末时刻单元格底层为全精度数值。内部NPZ另存t=0。

## 模型局限

忽略端面、采用有效Ce同尺度Robin闭合、h及hm沿用附录2且不显式计入潜热，均继承Q2并公开记录。恒定半径是问题三条件；未调用附件2或附录4。现有附件没有内部含水率实测标签，本结果是所选模型下的数值预测，不能声称实验准确率。长期环境观测只有4 h，后续约{root['time_h']-4:.2f} h属于明示延拓。

依赖与复现见`reports/Q3_DEPENDENCY_RECORD.md`及`Q3_REPRODUCE.md`。问题二PR尚待其独立审核；本任务不自行批准或合并上游。
"""
    Path("reports/Q3_RESULTS_REPORT.md").write_text(text,encoding="utf-8")
    spatial="| 粗N → 细N | 临界时间绝对差 / s | 共同60 s场最大含水率差 |\n|---|---:|---:|\n"
    spatial+="\n".join(f"| {s['coarse_N']} → {s['fine_N']} | {s['time_difference_s']:.9f} | {s['C']:.8e} |" for s in v["spatial"])
    temporal="| 设置对照 | 临界时间绝对差 / s | 共同场最大含水率差 |\n|---|---:|---:|\n"
    temporal+="\n".join(f"| {s['a']} / {s['b']} | {s['time_difference_s']:.9f} | {s['C']:.8e} |" for s in v["temporal"])
    verify=f"""# 问题三数值与交付验证报告

## 当前结论

当前源码绑定的数值门禁与Excel全量回读通过。正式网格N=40960；原始初值、正值、有限数、温度历史包络、全域根及前后状态、局部/全局水分平衡均通过。该结论属于数值与交付验证；小组独立交叉审核及实物验证不在此处宣称完成。

## 空间与时间误差

{spatial}

两段实测收敛阶为{', '.join(f'{p:.6f}' for p in v['observed_orders'])}。初始“相邻差<0.1 s”的直接目标未通过，记录字段`initial_adjacent_difference_goal_passed=false`保留事实。增加40960网格后，依据已观察的近二阶收敛，用最后相邻差除以(2^p−1)，p取实测阶与2的较小值，得到剩余空间误差估计{v['estimated_space_time_error_s']:.9f} s。该估计满足0.1 s的误差量级目标，依赖渐近收敛假设，不是严格证明。

{temporal}

估计空间误差、最大时间设置变化及最终根包围宽度相加为{v['estimated_numerical_time_change_s']:.9f} s。没有用根算法容差替代PDE离散误差；不能从表格四位小数推断同量级真实精度。

## 全域、初边值与水分平衡

- 全时程接受步和中点均检查全部计算节点。中心/表面本身为端点；首单元用偶二次重建，其余线性重建无内部超调，故重建全域最大值等于全部节点最大值。
- 接受步最大值位置范围为{v['argmax_radius_range_m']} m；6 h后为{v['argmax_after_6h_range_m']} m；根前、根、根后位置为{v['near_argmax_radius_m']} m。早期近均匀平台上的argmax可能受浮点平局影响，不强行宣称唯一中心极值。
- 四档网格根前/根/根后最大值位置（m）为`{v['mesh_near_argmax_radius_m']}`；用于核查最大值位置随网格的稳定性。
- 最大Cmax数值增加量{diag['max_Cmax_increase']:.3e} kg/kg；径向相邻增加最大值{v['max_radial_increase']:.3e} kg/kg。比较原理和实测单调性共同支持首次穿越判断。
- 全程最小含水率{diag['minimum_moisture']:.12f} kg/kg，未裁剪负值；温度历史包络超出量{diag['temperature_envelope_violation']:.3e} °C（舍入量级）。
- 总体水分余额最大相对残差{diag['max_relative_balance']:.8e}；8点和4点Gauss表面流量求积累计差{diag['flux_quadrature_difference']:.8e}；逐控制体水分残差最大绝对值{diag['max_local_water_balance_absolute']:.8e}。
- 表面节点保留储存，Robin通量作为控制体外边界精确施加；中心面积与通量为零。独立三点后向梯度最大相对残差{diag['max_surface_gradient_relative_residual']:.8e}，各网格值见convergence.csv。它与状态误差不同，低D薄表层放大梯度误差；未拿边界公式与自身比较冒充独立梯度核验。
- 为避开BDF的非物理解探测步，从均匀原始初值显式用1e−4 s初始步；这与Q2异常重试采用的尺度一致，未修改初始场或材料系数。

## 同设置问题二回归

Q3的N=20480收紧设置与Q2的N=20480收紧归档，在{v['q2_regression']['common_times']}个共同时间、21个输出半径比较：温度最大差{v['q2_regression']['T']:.9e} °C，含水率最大差{v['q2_regression']['C']:.9e} kg/kg，符合预设预算。Q2归档仅用于共同输出对照；全域事件由完整计算状态重算。

q1/q2物理源码没有改动。上游53项既有测试和本次新增事件/交付反例均由当前完整测试集执行，实际数量及输出见`results/q3/unit_tests.txt`。GitHub无CI结论时不把本地测试称作CI通过。

## Excel、图源与追溯

- 全量回读{e['cells_checked']}个含水率单元格，全部存在、为有限数、格式0.0000，与源舍入值逐格最大差{e['moisture_max_abs_difference']}；末时间底层值误差{e['terminal_time_difference_s']:.3e} s。
- Excel SHA-256：`{e['workbook_sha256']}`。正文表5、Excel、曲线及末态由同一个正式run归档生成。
- 数值源码提交`{r['source']['code_commit']}`，规范化源摘要`{r['source']['source_digest']}`；文件及输入绑定见每个run.json，运行环境Python {r['source']['python']}、SciPy {r['source']['packages']['scipy']}、NumPy {r['source']['packages']['numpy']}。
- 规范化文本哈希允许Windows CRLF/LF差异；实际代码、输入、数值归档、工作簿变化会使当前验证失效。每个新输出目录从原始初值积分，已有缓存必须核验源码、输入、配置和文件摘要。
- 四张矢量PDF由保存的CSV重新读入生成，字体{fig['font']}；渲染核对证据见`results/q3/visual_qa.json`（仅在实际视觉检查后写入）。
"""
    Path("reports/Q3_VERIFY_REPORT.md").write_text(verify,encoding="utf-8")


if __name__ == "__main__":
    make()

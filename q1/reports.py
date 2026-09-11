"""Build concise Q1 result and verification reports from recorded evidence."""
import json
from pathlib import Path

import numpy as np

from .archive import write_json
from .export import verified_source


def table_md(rows):
    return "| 时间 / s | 0 cm | 0.5 cm | 1 cm | 1.5 cm | 2 cm |\n|---:|---:|---:|---:|---:|---:|\n" + "\n".join("| " + " | ".join(map(str,row)) + " |" for row in rows)


def main():
    out = Path("results/q1")
    data,g,m,v = verified_source(out)
    export = json.loads((out/"export_verification.json").read_text(encoding="utf-8"))
    reproduction = json.loads((out/"reproduction.json").read_text(encoding="utf-8"))
    if not export["passed"] or not reproduction["passed"]:
        raise ValueError("Reports require successful export and reproduction checks")
    tables = json.loads((out/"tables.json").read_text(encoding="utf-8"))
    conv = json.loads((out/"convergence.json").read_text(encoding="utf-8"))
    endT,endC = data["temperature_C"][-1],data["moisture"][-1]
    avgT,avgC = (float(u@g["volume_m3"]/g["volume_m3"].sum()) for u in [endT,endC])
    result = f"""# 第一问数值结果报告

题给附录2参数下的中截面径向有效基准已达到本项目的数值交付条件，小组交叉审核待完成。模型及闭合见[正式契约](Q1_MODEL_SPEC.md)，误差证据见[验证报告](Q1_VERIFY_REPORT.md)，复现见[运行说明](../REPRODUCE.md)。仅求解0–1800 s；未实现第二至第四问，未作实验验证。

## 表1：温度 / °C

{table_md(tables['temperature'])}

## 表2：干基含水率 / (kg水/kg干药材)

{table_md(tables['moisture'])}

## 结果解释

1800 s时，中心/表面温度为{endT[0]:.6f}/{endT[-1]:.6f} °C，径向差为{endT[-1]-endT[0]:.6f} °C，体积平均为{avgT:.6f} °C。中心/表面含水率为{endC[0]:.6f}/{endC[-1]:.6f} kg/kg，体积平均为{avgC:.6f} kg/kg。这些数值是当前闭合假设下的计算预测。

热、湿径向Biot数大于1，图中保留了径向差异。水分扩散时间尺度远长于预热时段，主要失水区靠近表面；温度从外向内传播，中心响应滞后。相应结论由实际场值和下列图源数据支持，不通过改变题给参数迎合预期。

| 图 | 表达内容 | 数据源 |
|---|---|---|
| [环境输入](../figures/q1/environment.pdf) | 31个观测点及分段线性驱动 | results/q1/figure_data/environment.csv |
| [径向曲线](../figures/q1/radial_profiles.pdf) | 指定7时刻的温度、含水率分布 | results/q1/figure_data/profiles.csv |
| [中心、表面与平均响应](../figures/q1/center_surface_response.pdf) | 中心滞后及表面失水 | results/q1/figure_data/response.csv |
| [收敛证据](../figures/q1/convergence.pdf) | 全输出及前60 s表面细化差 | results/q1/figure_data/convergence.csv |

## 交付和限制

[result1.xlsx](../results/result1.xlsx)两表均为A1:V1801，时间1–1800 s、21个半径0–2 cm。温度与含水率共{export['numeric_result_cells_checked']}个结果单元格已逐格独立回读。表1–2、Excel、图均来自同一份全精度归档。t=0只存内部；四位采用ROUND_HALF_UP，显示舍入误差最多5e-5，不能据此声称四位物理准确。

环境水分列被解释为等效干基边界驱动，未经材料气固平衡实验标定。基准不显式计潜热，条件性审查不能证明其可忽略；题给820 kg/m³仅用于热容量。端面热上界只适用于契约中的线性各向同性无潜热模型。现有资料支持这个有效基准的计算与复核，不能识别真实蒸发通量或给出实验置信区间。
"""
    Path("reports/Q1_RESULTS_REPORT.md").write_text(result,encoding="utf-8")
    conv_rows = []
    for row in conv:
        if "difference" not in row:
            continue
        d = row["difference"]
        order = row.get("observed_order",{})
        order_text = f"{order['C']:.3f}" if 'C' in order else "—"
        conv_rows.append(f"| {row['N']} | {d['T']['max_abs']:.5e} | {d['C']['max_abs']:.5e} | {d['C']['time_s']:g} | {d['C']['radius_cm']:g} | {order_text} |")
    trials = {"BDF":m["solver"]["trial_failures"],"Radau":v["radau_diagnostics"]["trial_failures"]}
    last = conv[-1]
    pC = last["observed_order"]["C"]
    rich = last["difference"]["C"]["max_abs"]/(2**pC-1)
    metrics = []
    for name,label in [("T","温度"),("C","含水率")]:
        a,b,r = v["analytic"][name],v["balance"][name],v["boundary"][name]
        metrics += [f"| {label}完整级数最大绝对差 | {a['max_abs']:.6e} | {a['budget']:.1e} |",f"| {label}时间设置差 | {v['tolerance_difference'][name]['max_abs']:.6e} | {m['configuration']['budgets']['time_'+name]:.1e} |",f"| {label}Radau差 | {v['radau_difference'][name]['max_abs']:.6e} | {m['configuration']['budgets']['time_'+name]:.1e} |",f"| {label}全程归一化余额 | {b['max_balance']:.6e} | 1e-8 |",f"| {label}独立求积复核差 | {b['max_quadrature_difference']:.6e} | 1e-10 |",f"| {label}1–60 s边界归一化残差 | {r['early']:.6e} | 1e-2 |",f"| {label}100–1800 s边界归一化残差 | {r['late']:.6e} | 1e-3 |"]
    verify = f"""# 第一问数值验证报告

数值、导出及复现门槛已通过；小组交叉审核仍为pending。自动检查是实现和数值证据，不代替材料实验或独立组员审核。

## 基础关系与独立基准

第一条代码验收是sum bVi dotui=−AR qR；多网格随机正状态检查归一化余额≤1e-12、总体积相对差≤1e-13。u=(r/R)²配解析边界通量验证所有节点算子4a/(bR²)，尺度误差≤1e-10。平衡场、hm=0非均匀正初值的质量/方差、中心系数、两个稀疏Jacobian块及独立方向差分均通过测试。测试代码和运行日志入库，未用事后裁剪满足检查。

常系数恒环境对照热参数和D(2.55)，覆盖1、2、5、10、30、60、100、300、600、1800 s及21个半径。完整级数的特征根由J0零点括区间，投影系数另经数值积分核对；热用{v['analytic']['T']['modes']}项，水分用{v['analytic']['C']['modes']}项，两次截断差均小于1e-10。不是短时单项近似。

制造场1+(r/R)²的内部及体积加权残差约二阶、表面局部残差约一阶，记录在verification.json。不能把表面局部截断阶当成全局场误差阶。

## 全输出空间收敛

| 细网格N | 最大温度差 / °C | 最大含水率差 / kg/kg | 水分最差时刻 / s | 半径 / cm | 水分观测阶 |
|---:|---:|---:|---:|---:|---:|
{chr(10).join(conv_rows)}

比较全部1–1800 s×21半径，t=0也保存且差为零。所有细网格的水分最大差集中在早期表面，详见convergence.json的独立1–60 s表面字段。初轮上限10240只能提供一次达标细化，用户明确授权扩到20480；空间预算T8e-4、C8e-6未放宽。温度细化差接近初轮时间误差后，正式空间组收紧至rtol=1e-11、atol=(1e-12,1e-14)、max_step=2.5 s。初轮记录保留在initial_convergence.json和initial_verification.json。

最终N={m['N']}，dr={g['radius_m'][1]*1000:.8f} mm，连续两次细化进入预算并下降。水分最末观测阶{pC:.5f}，在可见的渐近区按Richardson估计最细网格水分误差约{rich:.6e} kg/kg；此估计不是严格上界。温度最末细化差仍与更严时间差同量级，温度的二阶空间趋势以较粗且时间误差更小的网格组佐证，不把极小细化差的阶外推为严格误差保证。

## 时间、边界与余额

| 检查 | 实测最大误差 | 阈值 |
|---|---:|---:|
{chr(10).join(metrics)}

正式归档采用更严BDF：rtol={m['solver']['settings']['rtol']:.1e}，atolT={m['solver']['settings']['atol_T']:.1e}、atolC={m['solver']['settings']['atol_C']:.1e}，max_step={m['solver']['settings']['max_step']:g} s。Radau使用同一空间算子，仅对时间推进形成交叉复核，空间正确性另由完整级数和制造场支持。

全程余额用连续解独立4/8点Gauss求积并以差值触发细分，在所有接受步、环境折点和每秒输出点切分；表面Robin通量独立于ODE右端求积。BDF连续多项式至多五次，Robin通量对表面场线性，Gauss4对每段多项式已足够；Gauss8给出独立求积复核。每秒余额全量保存在balance.csv。未同时积分辅助质量状态来自证。

## 非负性、试探态和复现

所有接受步及完整每秒场均为正并在契约包络内，温度/C包络宽限分别1e-7/1e-9。以下是自动步长估计或非线性试探阶段触发的记录，未被接受为解：

```json
{json.dumps(trials,ensure_ascii=False,indent=2)}
```

初始步长估计尚未建立积分器对象时current_step为null，同时记录trial_offset_from_segment_start。触发后从该段原始初值缩小first_step和max_step，未更改D、未裁剪C；接受解及BDF/Radau差的检查仍通过。

独立新进程重新读取原输入和配置，重算最终网格并比较全部{reproduction['times_compared']}个时刻×{reproduction['radii_compared']}个内部节点：温度最大差{reproduction['full_internal_grid_max_abs']['temperature_C']:.6e} °C、含水率最大差{reproduction['full_internal_grid_max_abs']['moisture']:.6e} kg/kg。记录在reproduction.json。

## 导出与追溯

独立openpyxl回读{export['numeric_result_cells_checked']}个Excel数值，核对两表A1:V1801、时间/半径、数值类型、0.0000格式、B2冻结窗口及与正文表一致性；图曲线直接读取保存的CSV，图源逐项回对全精度归档。作者端及视觉检查另见authoring.json。原模板哈希不变。

数值阶段源代码基础提交：{m['code_commit']}。manifest.json记录实际源文件哈希、输入哈希、参数、依赖版本和运行命令，后续报告/导出提交可从Git历史追踪。模型结构不确定性与纯数值误差分列，四位显示不是准确率。第二至第四问及整篇论文未执行。
"""
    Path("reports/Q1_VERIFY_REPORT.md").write_text(verify,encoding="utf-8")
    Path("reports/RESULTS_REPORT.md").write_text("# 计算结果索引\n\n目前仅第一问数值基准交付就绪，小组交叉审核待完成。第二至第四问和整篇论文尚未实现。\n\n- [第一问结果与表1–2](Q1_RESULTS_REPORT.md)\n- [第一问数值验证](Q1_VERIFY_REPORT.md)\n- [第一问模型契约](Q1_MODEL_SPEC.md)\n- [result1.xlsx](../results/result1.xlsx)\n- [复现说明](../REPRODUCE.md)\n- [全精度归档清单](../results/q1/archive/manifest.json)\n",encoding="utf-8")


if __name__ == "__main__":
    main()

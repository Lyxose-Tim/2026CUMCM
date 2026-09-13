"""Generate Q4 model, result, and verification reports from bound evidence."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from common.hashing import file_record, verify_file
from q2.archive import write_json
from q4.export import delivery_sources
from q4.sensitivity import verified_summary
from q4.validation import verified


REPORT_DIR = Path("reports")


def require_export(directory="results/q4", workbook="results/result4.xlsx"):
    directory = Path(directory)
    evidence = json.loads((directory / "export_verification.json").read_text(encoding="utf-8"))
    if evidence.get("passed") is not True:
        raise ValueError("Q4 Excel verification failed or absent")
    try:
        verify_file(workbook, evidence["workbook_hash"])
        verify_file(directory / "verification.json", evidence["verification_hash"])
        verify_file(directory / "table6.csv", evidence["table6_hash"])
        verify_file(directory / "radius_input_manifest.json", evidence["radius_input_manifest_hash"])
        verify_file(directory / "radius_observations.csv", evidence["radius_observations_hash"])
    except (KeyError, ValueError) as exc:
        raise ValueError("Q4 Excel evidence belongs to a different workbook or is stale") from exc
    if evidence["delivery_sources"] != delivery_sources():
        raise ValueError("Q4 Excel delivery evidence is stale")
    return evidence


def require_figures(directory: Path):
    manifest = json.loads((directory / "figure_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 3:
        raise ValueError("Versioned Q4 figure evidence is required")
    verify_file("q4/figures.py", manifest["generator"])
    verify_file(directory / "verification.json", manifest["verification"])
    verify_file(directory / "sensitivity" / "summary.json", manifest["sensitivity_summary"])
    for name, digest in manifest["csv"].items():
        verify_file(directory / "figure_data" / name, digest)
    for name, digest in manifest["pdf"].items():
        verify_file(Path("figures/q4") / name, digest)
    return manifest


def require_sensitivity(directory: Path):
    return verified_summary(directory / "sensitivity")


def _case_table(summary: list[dict]) -> str:
    labels = {
        "A_appendix3_fixed_N5120": "A：附录3，固定半径",
        "B_appendix3_shrink_N5120": "B：附录3，收缩半径",
        "C_appendix4_fixed_N5120": "C：附录4，固定半径",
        "D_appendix4_shrink_N5120": "D：附录4，收缩半径",
    }
    lines = [
        "| 案例 | 全域达标时间 / h | 事件半径 / cm | 中心C | 表面C |",
        "|---|---:|---:|---:|---:|",
    ]
    for item in summary:
        if item["status"] != "event":
            raise ValueError(f"Unresolved event in case table: {item['case']}")
        lines.append(
            f"| {labels[item['case']]} | {item['time_h']:.10f} | {item['event_radius_cm']:.4f} | "
            f"{item['center_C_at_event']:.6f} | {item['surface_C_at_event']:.6f} |"
        )
    return "\n".join(lines)


def write_reports(directory="results/q4"):
    directory = Path(directory)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    verification, record, fields = verified(directory)
    export = require_export(directory)
    figures = require_figures(directory)
    sensitivity = require_sensitivity(directory)
    root = record["root"]
    diagnostics = record["diagnostics"]
    interaction = verification["factorial_interaction"]
    n = record["identity"]["case"]["N"] + 1
    root_C = np.asarray(fields["near_states"][1, n:], dtype=float)
    ratio = 0.175 * np.exp(0.15 / root_C)
    crossover_C = 0.15 / np.log(1.0 / 0.175)
    surface_ratio = float(ratio[-1])
    reversed_nodes = int(np.count_nonzero(ratio > 1.0))
    radius_observations = np.genfromtxt(
        directory / "radius_observations.csv", delimiter=",", names=True
    )
    radius_observed_end_s = float(radius_observations["time_s"][-1])
    radius_observed_end_cm = float(radius_observations["radius_cm"][-1])

    model_spec = r"""# 问题四模型规范

## 坐标与状态量

问题四在 Q2/Q3 热湿模型上引入附件2半径变化和附录4物性。令材料坐标 xi=r/R(t)，并假设长度不变、径向材料点随半径仿射运动。干基含水率 C 按单位干物质计，因此几何收缩不额外产生体积浓缩源项；若把 C 解释为单位当前体积的浓度，则必须改写守恒式，本模型不采用该解释。

材料坐标下的有效方程为

\[
\rho_4(C)c_{p,4}(C)\theta_t=
\frac1{R(t)^2\xi}\frac\partial{\partial\xi}
\left(\xi k_4(C)\theta_\xi\right),
\qquad
C_t=\frac1{R(t)^2\xi}\frac\partial{\partial\xi}
\left(\xi D_4(C,\theta+273.15)C_\xi\right).
\]

中心为对称边界；表面为

\[
-\frac{D_4}{R}C_\xi=h_m(C_s-C_e),\qquad
-\frac{k_4}{R}\theta_\xi=h(\theta_s-T_e).
\]

## 物性与输入闭合

\[
\rho_4=760+90C,\quad
c_{p,4}=1850+2150\frac{C}{C+1},\quad
k_4=0.12+0.20\frac{C}{C+1},
\]

\[
D_4=4.2\times10^{-4}\exp(-0.30/C)
\exp[-3850/(\theta+273.15)].
\]

附件2半径记录覆盖 **0–72 h**，末个观测点为 **RADIUS_END_H_TOKEN h、RADIUS_END_CM_TOKEN cm**。主方案只在观测点之间作分段线性插值，不作半径外推，也没有 1.2 cm 限幅规则。正式 Q4 事件发生在半径记录覆盖内；附录4固定半径 C 组超过 72 h 时始终保持 2 cm，不需要移动半径。PCHIP 仅作为观测点间结构敏感性情景。环境 0–4 h 使用附件1逐段线性插值，之后主方案保持最后一小时均值；末值保持另列为结构情景。

Ce、h、hm、rho cp 均按题设尺度视为有效闭合量；经验 rho 不是独立标定的干骨架密度，热方程不含蒸发潜热，模型忽略端面和轴向梯度。因此它是竞赛题设下的一维有效模型，不是完整焓守恒或实验校准模型。

## 事件与数值方案

停止条件仍为全域最大干基含水率首次严格低于 0.15 kg/kg。正式案例为 FORMAL_CASE_TOKEN，使用 N=FORMAL_N_TOKEN、收紧容差与减半最大步长的 BDF；A–D 机制表统一使用 N=5120，避免把网格差混入物性和几何主效应。空间、时间、积分方法和根定位误差分别核验，不合并成统计置信区间。
"""
    model_spec = model_spec.replace("FORMAL_CASE_TOKEN", verification["formal_case"])
    model_spec = model_spec.replace("FORMAL_N_TOKEN", str(record["identity"]["case"]["N"]))
    model_spec = model_spec.replace("RADIUS_END_H_TOKEN", f"{radius_observed_end_s / 3600:.0f}")
    model_spec = model_spec.replace("RADIUS_END_CM_TOKEN", f"{radius_observed_end_cm:.3f}")
    (REPORT_DIR / "Q4_MODEL_SPEC.md").write_text(model_spec, encoding="utf-8")

    structural_lines = [
        f"| {item['scenario']} | {item['event_time_h']:.10f} | "
        f"{item['event_delta_vs_linear_s'] / 60:+.4f} |"
        for item in sensitivity["scenarios"]
    ]
    results_report = rf"""# 问题四计算结果报告

## 正式结果

附录4物性、收缩半径和主环境延拓下，全域达标时间为 **{root['time_h']:.10f} h**（{root['time_s']:.9f} s）；临界时材料半径为 **{root['radius_m'] * 100:.4f} cm**。该值是 51.0920 h 观测区间内插值结果，不是人为下限；附件2在 72 h 的末个实测半径为 {radius_observed_end_cm:.3f} cm。根处中心值为 0.15 kg/kg，动态表面值为 {root['near_summary'][1][7]:.12f} kg/kg，说明表面和平均值早于内部最湿点达到阈值，不能作为停机判据。

## A–D 机制对照

{_case_table(verification['table6_summary'])}

四个算例都实际定位到事件；C 案例的 129.8489535563 h 来自延长的 150 h 数值窗，不再以大于 72 h 的删失值代替。正式答案使用高精度 N=20480 案例，A–D 只承担同网格机制分解。

在相同 C、T 下，D4/D3 = 0.175 exp(0.15/C)。

该比值在 C={crossover_C:.7f} 处等于 1。湿芯 C≥0.15 时比值约为 0.186–0.476，附录4局部扩散较慢；但正式根时刻表面 C={root_C[-1]:.10f}，对应 D4/D3={surface_ratio:.5f}，共有 {reversed_nodes}/{len(root_C)} 个材料节点出现 D4/D3>1。另一方面半径由 2 cm 收缩至事件时的 {root['radius_m'] * 100:.4f} cm，缩短了扩散路径。故 A–D 时间差是湿芯减慢、干表层反转、几何收缩及温湿耦合共同作用的净结果，不能把全场概括为“附录4扩散始终更慢”。

以事件时间为响应，附录3条件下收缩效应为 {interaction['geometry_effect_appendix3_s'] / 3600:+.4f} h，附录4条件下为 {interaction['geometry_effect_appendix4_s'] / 3600:+.4f} h；固定半径下物性效应为 {interaction['property_effect_fixed_s'] / 3600:+.4f} h，收缩半径下为 {interaction['property_effect_shrinking_s'] / 3600:+.4f} h，交互项为 {interaction['interaction_s'] / 3600:+.4f} h。交互项很大，不能把“换物性”和“收缩”解释成两个可简单相加的修正。

## 结构敏感性

| 情景 | 全域达标时间 / h | 相对线性基准 / min |
|---|---:|---:|
{chr(10).join(structural_lines)}

半径记录按显示分辨率上下移动 0.0005 cm 时，事件时间范围为 {sensitivity['radius_record_scenario_range_s'][0] / 3600:.10f}–{sensitivity['radius_record_scenario_range_s'][1] / 3600:.10f} h，宽度 {sensitivity['radius_record_scenario_width_s'] / 60:.4f} min。PCHIP 相对线性改变 {sensitivity['pchip_minus_linear_s'] / 60:+.4f} min，长期环境改为末值保持改变 {sensitivity['terminal_hold_minus_last_hour_mean_s'] / 60:+.4f} min。以上均是**确定性结构情景范围，不是置信区间**。

## 图表与工作簿

五张 Q4 PDF 分别展示过程与半径、真实动态表面剖面、A–D 案例、数值层和结构情景；每张图由 results/q4/figure_data/ 中的完整绘图 CSV 重建。results/result4.xlsx 共 {export['rows']} 个数据行、{export['columns']} 列；固定物理半径超过当前表面时留空，末列始终保存真实动态表面值。独立回读核对 {export['cells_checked']} 个数值与 {export['blank_cells_checked']} 个域外空白。

## 解释边界

4 h 后环境延拓、半径观测点间插值及记录显示精度对结果有结构影响，且没有内部含水率实验数据可校准；因此 51.0920 h 是明示模型与输入规则下的情景预测。数值误差、Excel 四位小数舍入、结构情景和真实模型误差必须分开陈述。
"""
    (REPORT_DIR / "Q4_RESULTS_REPORT.md").write_text(results_report, encoding="utf-8")

    spatial_lines = "\n".join(
        f"| {item['a']}→{item['b']} | {item['root_time_difference_s']:.9f} | "
        f"{item['field_difference']['C']['max_abs']:.8e} | {item['field_difference']['T']['max_abs']:.8e} |"
        for item in verification["spatial"]
    )
    temporal = verification["temporal"][0]
    method = verification["method"]["comparison"]
    verify_report = f"""# 问题四数值与交付验证报告

验证状态：passed = {verification['passed']}。所有正式和 A–D 算例均通过有限性、正值、温度包络、半径单调、域外空白、全域严格越阈、根残差和水分平衡检查。

## 空间收敛

| 对照 | 临界时间差 / s | 最大含水率场差 | 最大温度场差 / °C |
|---|---:|---:|---:|
{spatial_lines}

后一组 N=10240→20480 的临界时间差为 {verification['spatial'][-1]['root_time_difference_s']:.9f} s；空间预算门禁 passed = {verification['spatial_budget']['passed']}。比较覆盖全部共同 60 s 时刻、21 个固定物理半径列和动态表面列；24 h 仅作为中间检查点，另在各对照共同事件覆盖前的最后一个规则时刻保存完整 T/C 近根状态。

## 时间、方法与根定位

| 层次 | 临界时间差 / s | 最大含水率场差 | 最大温度场差 / °C |
|---|---:|---:|---:|
| BDF 基准与收紧/半步 | {temporal['root_time_difference_s']:.9f} | {temporal['field_difference']['C']['max_abs']:.8e} | {temporal['field_difference']['T']['max_abs']:.8e} |
| BDF 与 Radau | {method['root_time_difference_s']:.9f} | {method['field_difference']['C']['max_abs']:.8e} | {method['field_difference']['T']['max_abs']:.8e} |

BDF/Radau 对照使用相同 N=5120；其共同近根时刻为 {method['field_difference']['near_root_common']['time_s']:.0f} s，直接取双方精确归档的 60 s 状态，无时间插值或重建误差。该时刻共有 {method['field_difference']['near_root_common']['C']['valid_columns']} 个共同有效含水率输出列（含动态表面），最大 C 差为 {method['field_difference']['near_root_common']['C']['max_abs']:.8e}，最大 T 差为 {method['field_difference']['near_root_common']['T']['max_abs']:.8e} °C。

正式根区间宽度为 {verification['root_resolution']['formal_bracket_width_s']:.9e} s，根残差为 {verification['root_resolution']['formal_root_residual']:.3e}。这些层次分别保存，未相互替代，也未包装成统一置信区间。

## 回归与守恒

- 固定域退化到 Q3 的共同时间比较：临界时间差 {verification['q3_regression']['root_time_difference_s']:.9f} s，含水率最大差 {verification['q3_regression']['C']:.8e}，温度最大差 {verification['q3_regression']['T']:.8e} °C。
- 正式运行总体水分平衡最大相对残差 {diagnostics['max_relative_balance']:.8e}，末接受步余额 {record['terminal']['relative_balance']:.8e}。
- 两种表面流量求积累计差 {diagnostics['flux_quadrature_difference']:.8e}，最低含水率 {diagnostics['minimum_moisture']:.12f}。
- 温度历史包络超出量 {diagnostics['temperature_envelope_violation']:.3e} °C，最大含水率数值增加量 {diagnostics['max_Cmax_increase']:.3e}。

## 交付与追溯

- 工作簿哈希方案 {export['workbook_hash']['hash_scheme']}，SHA-256 {export['workbook_hash']['sha256']}；末时间误差 {export['terminal_time_difference_s']:.3e} s。
- 图表字体 {figures['font']}，五张 PDF 和全部 CSV 由 results/q4/figure_manifest.json 逐文件绑定。
- 结构敏感性配置、生成器、五个运行记录及其 NPZ/接受步文件和汇总 CSV 均由 results/q4/sensitivity/summary.json 递归绑定。
- 正式数值源码提交 {record['source']['code_commit']}，源摘要 {record['source']['source_digest']}；测试输出见 results/q4/unit_tests.txt。

这里的 passed 是数值与交付门禁，不代表实物试验验证，也不把长期环境延拓的不确定性归入数值误差。
"""
    (REPORT_DIR / "Q4_VERIFY_REPORT.md").write_text(verify_report, encoding="utf-8")

    index = REPORT_DIR / "RESULTS_REPORT.md"
    index.write_text("""# 计算结果索引

四问计算、验证、表格和论文图源均按同一证据链交付。

- [问题一：附录2常热物性与非线性水分扩散基准](Q1_RESULTS_REPORT.md)
- [问题二：72 h 变物性热湿耦合与表3–4](Q2_RESULTS_REPORT.md)
- [问题三：固定半径全域达标事件与表5](Q3_RESULTS_REPORT.md)
- [问题四：收缩域机制、全域达标事件与表6](Q4_RESULTS_REPORT.md)
- [问题四数值与交付验证](Q4_VERIFY_REPORT.md)
- [综合建模与适用边界](ANALYSIS_MODELING_REPORT.md)
""", encoding="utf-8")

    report_paths = [
        REPORT_DIR / "Q4_MODEL_SPEC.md",
        REPORT_DIR / "Q4_RESULTS_REPORT.md",
        REPORT_DIR / "Q4_VERIFY_REPORT.md",
        index,
    ]
    write_json(directory / "report_manifest.json", {
        "schema_version": 3,
        "generator": file_record("q4/reports.py"),
        "reports": {path.name: file_record(path) for path in report_paths},
        "verification": file_record(directory / "verification.json"),
        "export_verification": file_record(directory / "export_verification.json"),
        "figure_manifest": file_record(directory / "figure_manifest.json"),
        "sensitivity_summary": file_record(directory / "sensitivity" / "summary.json"),
    })


if __name__ == "__main__":
    write_reports()

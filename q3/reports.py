"""Generate Q3 model, result, and verification reports from bound evidence."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from common.hashing import file_record, verify_file
from q2.archive import write_json
from q3.export import delivery_sources, rounded
from q3.validation import verified


REPORT_DIR = Path("reports")


def require_export(directory="results/q3", workbook="results/result3.xlsx"):
    directory = Path(directory)
    evidence = json.loads((directory / "export_verification.json").read_text(encoding="utf-8"))
    if evidence.get("passed") is not True:
        raise ValueError("Q3 Excel verification failed or absent")
    try:
        verify_file(workbook, evidence["workbook_hash"])
        verify_file(directory / "verification.json", evidence["verification_hash"])
        verify_file(directory / "table5.csv", evidence["table5_hash"])
    except (KeyError, ValueError) as exc:
        raise ValueError("Q3 Excel evidence belongs to a different workbook or is stale") from exc
    if evidence["delivery_sources"] != delivery_sources():
        raise ValueError("Q3 Excel delivery evidence is stale")
    return evidence


def require_figures(directory: Path):
    manifest = json.loads((directory / "figure_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 2:
        raise ValueError("Versioned Q3 figure evidence is required")
    verification = json.loads((directory / "verification.json").read_text(encoding="utf-8"))
    formal_case = verification["formal_case"]
    verify_file("q3/figures.py", manifest["generator"])
    verify_file(directory / "verification.json", manifest["verification"])
    verify_file(directory / "runs" / formal_case / "run.json", manifest["formal_run"])
    for name, digest in manifest["csv"].items():
        verify_file(directory / "figure_data" / name, digest)
    for name, digest in manifest["pdf"].items():
        verify_file(Path("figures/q3") / name, digest)
    return manifest


def _table5(directory: Path) -> str:
    values = rounded(np.loadtxt(directory / "table5.csv", delimiter=",", skiprows=1))
    lines = [
        "| 时间 / h | 0 cm | 0.5 cm | 1 cm | 1.5 cm | 2 cm |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    lines.extend("| " + " | ".join(f"{value:.4f}" for value in row) + " |" for row in values)
    return "\n".join(lines)


def make(directory="results/q3"):
    directory = Path(directory)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    verification, record, _ = verified(directory)
    export = require_export(directory)
    figures = require_figures(directory)
    root = record["root"]
    diagnostics = record["diagnostics"]
    near = np.asarray(root["near_summary"], dtype=float)

    model_spec = rf"""# 问题三模型规范

## 任务定义

问题三沿用问题二的附录3变物性热湿耦合模型，从原始初值重新积分，并保持圆柱半径 R=2 cm 不变。停止事件定义为

\[
t^*=\inf\{{t>0:\max_{{0\le r\le R}} C(r,t)<0.15\}}.
\]

数值根处连续场通常满足等号；“严格低于”由根后 1 s 的完整场另行核查。表面值、体积平均值和全域最大值是三个不同统计量，只有全域最大值用于停止判据。

## 控制方程与闭合

\[
\rho(C)c_p(C)\theta_t=\frac1r\frac\partial{{}}{{\partial r}}\left(rk(C)\theta_r\right),\qquad
C_t=\frac1r\frac\partial{{}}{{\partial r}}\left(rD(C,\theta+273.15)C_r\right).
\]

中心采用对称边界；表面采用与问题一、二一致的换热和传质 Robin 边界。环境在 0–4 h 使用附件1逐段线性插值，4 h 后主情景保持最后一小时均值。模型把 Ce、h、hm 与 rho cp 视为题设尺度下的有效闭合量；经验密度不是经独立质量守恒标定的干骨架密度，热方程也未加入蒸发潜热。因此结果是题设有效模型下的预测，不等同于完整焓守恒或实验精度声明。

## 数值事件定位

径向有限体积离散保留中心和表面控制体，面系数用调和平均；时间积分使用分段 BDF。正式案例由 configs/q3.json 固定为 {verification['formal_case']}，网格区间数唯一为 **N={record['identity']['case']['N']}**。每次事件评价读取全部 N+1 个含水率节点，并用无超调重建核查全域最大值；最终根区间宽度、网格、时间设置和 Q2 退化回归分别报告。
"""
    (REPORT_DIR / "Q3_MODEL_SPEC.md").write_text(model_spec, encoding="utf-8")

    near_lines = []
    for label, row in zip(["根前 1 s", "临界根", "根后 1 s"], near):
        near_lines.append(
            f"| {label} | {row[0]:.12f} | {row[1]:.16f} | {row[2] * 100:.8f} | "
            f"{row[4]:.12f} | {row[5]:.12f} |"
        )
    sensitivity_lines = [
        f"| {item['case']} | {item['time_h']:.6f} | {item['change_h']:+.6f} | "
        f"{100 * item['relative_change']:+.4f}% |"
        for item in verification["sensitivity"]
    ]
    results_report = f"""# 问题三计算结果报告

## 核心结论

固定半径、附录3物性和主环境延拓下，全域含水率首次达到临界等号的时间为

**t*={root['time_h']:.10f} h={root['time_s']:.12f} s**，题目表格按四位小数显示为 **{root['time_h']:.4f} h**（约 {root['time_h'] / 24:.4f} d）。事件位于 72 h 计算窗内，没有为贴合“2–3 天”而反向调参。

根处全域最大值为 {near[1, 1]:.16f} kg/kg，位置为 {near[1, 2] * 100:.8f} cm。根后 1 s 的完整场严格低于阈值；Excel 显示的 0.1500 仅是四位小数格式，不能替代全精度事件判断。

## 表5

{_table5(directory)}

最后一行为临界状态，前面各行为不超过 t* 的 6 h 整数倍。全精度来源为 results/q3/table5.csv。

## 阈值证据

| 状态 | 时间 / s | 全域最大C | 最大值半径 / cm | 体积平均C | 表面C |
|---|---:|---:|---:|---:|---:|
{chr(10).join(near_lines)}

最终根包围区间为 [{root['bracket_s'][0]:.12f}, {root['bracket_s'][1]:.12f}] s；区间端点函数值分别为 {root['bracket_g'][0]:.6e} 和 {root['bracket_g'][1]:.6e}。阈值附近斜率约为 {verification['slope_C_per_s']:.12e} kg/(kg·s)。当前数值时间变化量估计为 {verification['estimated_numerical_time_change_s']:.6f} s；四位小数舍入半宽对应约 {verification['rounding_5e_5_time_s']:.2f} s。两者都不是实物误差界。

## 确定性敏感性情景

| 情景 | 临界时间 / h | 相对同网格基准 / h | 相对变化 |
|---|---:|---:|---:|
{chr(10).join(sensitivity_lines)}

这些情景分别改变长期环境、传质系数或扩散系数前因子，使用 N=5120 与同网格基准比较。它们用于显示结构和参数影响方向，**不是统计置信区间**，也未替代正式网格答案。

## 图表与交付

四张 Q3 矢量图及逐图 CSV 位于 figures/q3/ 与 results/q3/figure_data/，清单采用版本化哈希。results/result3.xlsx 保留模板工作表与 21 个固定半径列，共 {export['rows']} 个数据行；时间从 60 s 开始并包含全精度临界末行。工作簿独立回读了 {export['cells_checked']} 个数值单元格，最大逐格差为 {export['moisture_max_abs_difference']}。

## 解释边界

模型忽略端面和潜热，长期环境只有前 4 h 观测，后续约 {root['time_h'] - 4:.2f} h 依赖明示延拓。没有内部含水率实验标签，故不报告实验准确率。中心在后期控制全域最大值，但早期近均匀平台上的最大值位置可能受浮点平局影响，不把它解读为唯一物理热点。
"""
    (REPORT_DIR / "Q3_RESULTS_REPORT.md").write_text(results_report, encoding="utf-8")

    spatial = "\n".join(
        f"| {item['coarse_N']}→{item['fine_N']} | {item['time_difference_s']:.9f} | "
        f"{item['C']:.8e} | {item['T']:.8e} |"
        for item in verification["spatial"]
    )
    temporal = "\n".join(
        f"| {item['a']} / {item['b']} | {item['time_difference_s']:.9f} | "
        f"{item['C']:.8e} | {item['T']:.8e} |"
        for item in verification["temporal"]
    )
    verify_report = f"""# 问题三数值与交付验证报告

验证状态：passed = {verification['passed']}。该状态只表示当前源码、输入、数值归档和交付文件通过设定门禁。

## 空间收敛

| 粗N→细N | 临界时间差 / s | 最大含水率场差 | 最大温度场差 / °C |
|---|---:|---:|---:|
{spatial}

三段观测阶为 {', '.join(f'{value:.6f}' for value in verification['observed_orders'])}。直接相邻网格差小于 0.1 s 的初始目标未满足，因此配置继续推进到 N=40960；按已观测近二阶规律估计的剩余空间时间误差为 {verification['estimated_space_time_error_s']:.9f} s。该估计依赖渐近区假设，不是严格 PDE 误差界。

## 时间设置

| 设置对照 | 临界时间差 / s | 最大含水率场差 | 最大温度场差 / °C |
|---|---:|---:|---:|
{temporal}

空间估计、最大时间设置变化与根区间宽度分开保存后，给出的总数值变化量估计为 {verification['estimated_numerical_time_change_s']:.9f} s；没有把根算法容差冒充 PDE 离散误差。

## 物理与守恒门禁

- 最小含水率 {diagnostics['minimum_moisture']:.12f} kg/kg，温度历史包络超出量 {diagnostics['temperature_envelope_violation']:.3e} °C。
- 总体水分平衡最大相对残差 {diagnostics['max_relative_balance']:.8e}，表面流量两种求积累计差 {diagnostics['flux_quadrature_difference']:.8e}。
- 逐控制体水分残差最大绝对值 {diagnostics['max_local_water_balance_absolute']:.8e}；独立表面梯度最大相对残差 {diagnostics['max_surface_gradient_relative_residual']:.8e}。
- 全时程最大含水率数值增加量 {diagnostics['max_Cmax_increase']:.3e}，径向相邻增加最大值 {verification['max_radial_increase']:.3e}。
- N=20480 同设置 Q2 回归比较 {verification['q2_regression']['common_times']} 个共同时间，温度最大差 {verification['q2_regression']['T']:.9e} °C，含水率最大差 {verification['q2_regression']['C']:.9e}。

## 交付与追溯

- 工作簿 {export['rows']} 行、{export['columns']} 列，哈希方案 {export['workbook_hash']['hash_scheme']}，SHA-256 {export['workbook_hash']['sha256']}。
- 正式数值提交记录 {record['source']['code_commit']}，源摘要 {record['source']['source_digest']}。
- 图表字体 {figures['font']}，四张 PDF 和对应 CSV 均由 results/q3/figure_manifest.json 逐文件绑定。
- 本地测试输出绑定在 results/q3/unit_tests.txt；未把本地测试称作远端 CI，也未声称完成实验验证。
"""
    (REPORT_DIR / "Q3_VERIFY_REPORT.md").write_text(verify_report, encoding="utf-8")

    report_paths = [
        REPORT_DIR / "Q3_MODEL_SPEC.md",
        REPORT_DIR / "Q3_RESULTS_REPORT.md",
        REPORT_DIR / "Q3_VERIFY_REPORT.md",
    ]
    write_json(directory / "report_manifest.json", {
        "schema_version": 2,
        "generator": file_record("q3/reports.py"),
        "reports": {path.name: file_record(path) for path in report_paths},
        "verification": file_record(directory / "verification.json"),
        "export_verification": file_record(directory / "export_verification.json"),
        "figure_manifest": file_record(directory / "figure_manifest.json"),
    })


if __name__ == "__main__":
    make()

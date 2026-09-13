"""Build Q2 result and verification reports from verified machine outputs."""
import argparse
import json
import math
from pathlib import Path

from common.hashing import file_record, verify_file
from .archive import write_json
from .export import TABLE_TIMES, TABLE_RADIUS_INDICES, rounded_array, verified_source
from .provenance import delivery_snapshot


def markdown_table(times, values):
    header = "| 时间 / h | 0 cm | 0.5 cm | 1.0 cm | 1.5 cm | 2.0 cm |\n|---:|---:|---:|---:|---:|---:|\n"
    rows = []
    for t, row in zip(times, rounded_array(values)):
        rows.append("| " + " | ".join([f"{float(t):.1f}", *[f"{value:.4f}" for value in row]]) + " |")
    return header + "\n".join(rows)


def validated_export(directory, workbook=None):
    directory = Path(directory)
    workbook = Path(workbook) if workbook is not None else directory.parent / "result2.xlsx"
    record = json.loads((directory / "export_verification.json").read_text(encoding="utf-8"))
    if record.get("passed") is not True:
        raise ValueError("Q2 Excel verification did not pass")
    if record.get("numeric_result_cells_checked") != 10886400:
        raise ValueError("Q2 Excel verification has an incomplete cell count")
    difference = record.get("max_absolute_readback_difference")
    if not isinstance(difference, (int, float)) or not math.isfinite(difference) or difference != 0.0:
        raise ValueError("Q2 Excel verification has a nonzero or invalid difference")
    if not workbook.is_file():
        raise ValueError("Current result2.xlsx is missing")
    try:
        verify_file(workbook, record["workbook_hash"])
    except (KeyError, ValueError) as exc:
        raise ValueError("Q2 Excel verification is stale for the current workbook") from exc
    if record.get("workbook_bytes") != workbook.stat().st_size:
        raise ValueError("Q2 Excel size does not match its verification")
    bindings = {
        "numerical_verification_hash": directory / "verification.json",
        "archive_manifest_hash": directory / "archive" / "manifest.json",
    }
    for key, path in bindings.items():
        try:
            verify_file(path, record[key])
        except (KeyError, ValueError) as exc:
            raise ValueError(f"Q2 Excel verification is stale for {path.name}") from exc
    current_delivery = delivery_snapshot()
    recorded_delivery = record.get("delivery_source", {})
    if (
        recorded_delivery.get("source_digest") != current_delivery["source_digest"]
        or recorded_delivery.get("source_hashes") != current_delivery["source_hashes"]
    ):
        raise ValueError("Q2 Excel verification is stale for the current export sources")
    return record


def validated_figures(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "figure_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 2:
        raise ValueError("Versioned Q2 figure evidence is required")
    verify_file("q2/figures.py", manifest["generator"])
    verify_file(directory / "verification.json", manifest["verification"])
    verify_file(directory / "archive" / "manifest.json", manifest["archive_manifest"])
    verify_file(directory / "convergence.json", manifest["convergence"])
    for name, digest in manifest["csv"].items():
        verify_file(directory / "figure_data" / name, digest)
    for name, digest in manifest["pdf"].items():
        verify_file(Path("figures/q2") / name, digest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default="results/q2")
    parser.add_argument("--reports", default="reports")
    args = parser.parse_args()
    directory, reports = Path(args.directory), Path(args.reports)
    report_paths = [
        reports / "Q2_MODEL_SPEC.md",
        reports / "Q2_RESULTS_REPORT.md",
        reports / "Q2_VERIFY_REPORT.md",
    ]
    try:
        export_verification = validated_export(directory)
        figure_manifest = validated_figures(directory)
        data, _, manifest, verification = verified_source(directory)
        scenarios = json.loads((directory / "environment_scenarios.json").read_text(encoding="utf-8"))
    except Exception:
        for path in report_paths:
            path.unlink(missing_ok=True)
        raise
    reports.mkdir(parents=True, exist_ok=True)
    table_T = data["temperature_C"][TABLE_TIMES][:, TABLE_RADIUS_INDICES]
    table_C = data["moisture"][TABLE_TIMES][:, TABLE_RADIUS_INDICES]
    extension = manifest["inputs"]["environment_extension"]
    endpoint_T, endpoint_C = data["temperature_C"][-1], data["moisture"][-1]
    scenario_lines = "\n".join(
        f"- `{item['mode']}`：中心温度 {item['endpoint']['center_temperature_C']:.6f} °C，"
        f"中心水分 {item['endpoint']['center_moisture']:.6f} kg/kg。"
        for item in scenarios
    )
    model_text = r"""# 第二问模型规范

## 控制方程

第二问从 t=0、theta=28 °C、C=2.55 kg/kg 重新积分，在固定半径 2 cm 的一维圆柱径向域内求解

\[
\rho(C)c_p(C)\theta_t=\frac1r\frac\partial{\partial r}
\left(rk(C)\theta_r\right),\qquad
C_t=\frac1r\frac\partial{\partial r}
\left(rD(C,\theta+273.15)C_r\right).
\]

附录3的 rho、cp、k、D 在每个节点随 C、theta 更新，面系数采用调和平均。中心采用对称边界；表面沿用问题一的换热与传质 Robin 边界。

## 有效闭合与适用边界

Ce、h、hm 与 rho cp 均按题设量纲作为有效闭合量使用。经验 rho 不解释成经过独立质量守恒标定的干骨架密度；热方程没有潜热项，因此不能称为完整焓守恒。模型忽略端面和轴向梯度，只描述竞赛题设下的一维径向有效过程。

环境 0–4 h 由附件1逐段线性插值，4–72 h 的主情景保持最后一小时均值；末值保持和 50 °C、0.05 kg/kg 只作为确定性结构情景。72 h 输出回答第二问的全过程，不宣称给出严格停止时间。

## 数值方案

圆柱有限体积离散显式处理中心控制体和表面储存，解析 Jacobian 包含物性导数与交叉导数。时间积分在环境折点处分段使用 BDF，并与收紧 BDF、减半最大步长和 Radau 对照。正式网格只有在连续两次空间加密满足全部时间与 21 个输出半径的误差预算后才能选定。
"""
    report_paths[0].write_text(model_text, encoding="utf-8")
    result_text = f"""# 第二问结果报告

## 计算口径

模型从初始时刻重新积分至 72 h。0--4 h 环境由附件 1 逐段线性插值；4--72 h 的正式情景固定为附件 1 最后一小时均值，即 {extension['temperature_C']:.6f} °C 和 {extension['moisture']:.6f} kg/kg。该延拓属于情景假设，不等同于题目给定观测。

正式径向网格为 N={manifest['N']}，归档保留 t=0，提交工作簿从 t=1 s 开始。

## 表 3 温度分布

{markdown_table(TABLE_TIMES / 3600, table_T)}

## 表 4 水分浓度分布

{markdown_table(TABLE_TIMES / 3600, table_C)}

## 72 h 端点

- 中心温度：{endpoint_T[0]:.6f} °C；表面温度：{endpoint_T[-1]:.6f} °C。
- 中心水分浓度：{endpoint_C[0]:.6f} kg/kg；表面水分浓度：{endpoint_C[-1]:.6f} kg/kg。
- 本结果描述第二问给定时域内的热湿演化，不声称已经求得严格烘干终止时刻，也不替代第三问。

## 结果解释边界

温度方程采用题面给定的有效热容形式，未加入潜热项，因此不能解释为完整焓守恒。4 h 后结果依赖环境延拓；两个72 h对照端点为：

{scenario_lines}

三种情景的相对偏差见 `../figures/q2/q2_environment_scenarios.pdf` 及绑定 CSV。当前附件没有内部场实测，数值收敛不能替代实验精度验证。
"""
    tol = verification["tolerance_difference"]
    rad = verification["radau_difference"]
    q1 = verification["q1_compatible_difference"]
    verify_text = f"""# 第二问数值验证报告

## 结论

数值门禁与Excel独立回读均通过。正式结果可用于表 3、表 4、`result2.xlsx` 和论文图表。

## 空间与时间误差

- 空间网格按倍增序列检验，并连续 {verification['consecutive_within_budget']} 次满足误差预算；正式网格 N={verification['N']}。
- 收紧 BDF 对照最大差：温度 {tol['T']['max_abs']:.3e} °C，水分 {tol['C']['max_abs']:.3e} kg/kg。
- Radau 对照最大差：温度 {rad['T']['max_abs']:.3e} °C，水分 {rad['C']['max_abs']:.3e} kg/kg。

## 物理与实现检查

- 总体水分平衡相对残差：{manifest['solver']['relative_moisture_balance']:.3e}。
- 含水率全程严格为正，全部正式输出为有限数，秒级时间轴无缺漏或重复。
- 接受步上的温度保持在初值与历史环境包络内；表面热、水分通量方向检查通过。
- 冻结附录 2 常物性后与 Q1 退化对照：温度最大差 {q1['T']['max_abs']:.3e} °C，水分最大差 {q1['C']['max_abs']:.3e} kg/kg。
- 单元测试覆盖物性及解析导数、完整耦合 Jacobian 的方向差分、平衡场、中心处理、共享面通量、逐控制体热湿方程残差和选点稠密输出。

## 可追溯性

- 源码提交：`{manifest['code_commit']}`。
- 源码摘要：`{manifest['source_digest']}`。
- 输入、配置、依赖、运行命令及每个归档分块的 SHA-256 均记录在 `results/q2/archive/manifest.json`。

## Excel 与图表验收

- `result2.xlsx` 为 {export_verification['workbook_bytes'] / 1024**2:.2f} MiB，包含两张259201行、22列工作表。
- 已独立流式回读 {export_verification['numeric_result_cells_checked']} 个数值单元格，最大绝对差为 {export_verification['max_absolute_readback_difference']:.1f}，工作簿 SHA-256 为 `{export_verification['workbook_hash']['sha256']}`。
- 正式工作簿由普通 Python 环境中的 openpyxl write-only 流式生成，不依赖私有作者端工具。
- 六张PDF图均从绑定CSV生成并经PNG渲染检查，无缺字、裁切或重叠。
- Excel交付源码摘要：`{export_verification['delivery_source']['source_digest']}`；对应提交：`{export_verification['delivery_source']['code_commit']}`。
"""
    report_paths[1].write_text(result_text, encoding="utf-8")
    report_paths[2].write_text(verify_text, encoding="utf-8")
    write_json(directory / "report_manifest.json", {
        "schema_version": 2,
        "generator": file_record("q2/reports.py"),
        "reports": {path.name: file_record(path) for path in report_paths},
        "verification": file_record(directory / "verification.json"),
        "export_verification": file_record(directory / "export_verification.json"),
        "figure_manifest": file_record(directory / "figure_manifest.json"),
        "figure_count": len(figure_manifest["pdf"]),
    })


if __name__ == "__main__":
    main()

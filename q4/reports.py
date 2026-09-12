"""Generate Q4 model, result, and verification reports."""
import json
from pathlib import Path

from q2.archive import write_json
from q2.inputs import sha256
from q2.provenance import portable_artifact_sha256
from q4.export import delivery_sources
from q4.validation import verified


def require_export(directory="results/q4", workbook="results/result4.xlsx"):
    directory = Path(directory)
    evidence = json.loads((directory / "export_verification.json").read_text(encoding="utf-8"))
    if evidence.get("passed") is not True:
        raise ValueError("Q4 Excel verification failed or absent")
    if evidence["workbook_sha256"] != sha256(workbook):
        raise ValueError("Q4 Excel verification belongs to a different workbook")
    if (evidence["delivery_sources"] != delivery_sources()
            or evidence["verification_sha256"] != portable_artifact_sha256(directory / "verification.json")
            or evidence["table6_sha256"] != portable_artifact_sha256(directory / "table6.csv")):
        raise ValueError("Q4 Excel delivery evidence is stale")
    return evidence


def write_reports(directory="results/q4"):
    directory = Path(directory)
    verification, record, _ = verified(directory)
    export_evidence = require_export(directory)
    root = record["root"]
    summary = verification["table6_summary"]
    lines = []
    for item in summary:
        if item["status"] == "event":
            lines.append(
                f"| {item['case']} | {item['time_h']:.10f} | {item['event_radius_cm']:.4f} | "
                f"{item['center_C_at_event']:.6f} | {item['surface_C_at_event']:.6f} |"
            )
        else:
            lines.append(f"| {item['case']} | >{item['horizon_h']:.0f} |  |  |  |")
    table = "\n".join(lines)
    Path("reports/Q4_MODEL_SPEC.md").write_text(f"""# Q4 模型规范

第四问在第二、三问热湿耦合方程基础上引入附件2半径收缩和附录4物性。材料坐标取 `xi=r/R(t)`，假设长度不变、径向材料点仿射收缩、干基含水率不因几何收缩产生额外体积浓缩项。

材料坐标方程为

```text
U_t = R(t)^(-2) * 1/xi * d/dxi [xi D4(U,Theta) U_xi]
rho4(U) cp4(U) Theta_t = R(t)^(-2) * 1/xi * d/dxi [xi k4(U) Theta_xi]
```

中心为对称边界；表面为 `-D4/R * U_xi = hm(U_s-Ce)` 与 `-k4/R * Theta_xi = h(Theta_s-Te)`。附件2半径采用单调分段线性插值，长期环境沿用第二、三问的最后一小时均值延拓。

附录4物性：

```text
rho4 = 760 + 90 C
cp4 = 1850 + 2150 C/(C+1)
k4 = 0.12 + 0.20 C/(C+1)
D4 = 4.2e-4 exp(-0.30/C) exp[-3850/(theta+273.15)]
```

停止条件与第三问一致：全部计算节点的最大干基含水率首次严格低于 0.15 kg/kg。正式案例为 `{verification['formal_case']}`。
""", encoding="utf-8")
    Path("reports/Q4_RESULTS_REPORT.md").write_text(f"""# Q4 结果报告

正式第四问结果采用附录4物性和附件2实测半径收缩，临界时间为 **{root['time_h']:.10f} h**，临界时表面半径为 **{root['radius_m'] * 100:.4f} cm**。根后 1 s 的全域最大含水率严格低于 0.15 kg/kg。

| 案例 | 临界时间 / h | 临界半径 / cm | 中心C | 表面C |
| --- | ---: | ---: | ---: | ---: |
{table}

表6见 `results/q4/table6.csv` 与 `results/q4/table6.md`，Excel交付表为 `results/result4.xlsx`，独立回读证据见 `results/q4/export_verification.json`。固定物理半径超过当前药材表面的单元格留空，末列始终为动态药材表面。

图源与论文图位于 `results/q4/figure_data/` 和 `figures/q4/`。A/B/C/D 对照用于分离物性与几何影响；正式高精度行使用 `{verification['formal_case']}`，不把 5120 网格对照当作最终答案。
""", encoding="utf-8")
    Path("reports/Q4_VERIFY_REPORT.md").write_text(f"""# Q4 验证报告

验证状态：`passed = {verification['passed']}`。

- Q3固定域退化回归：C最大差 `{verification['q3_regression']['C']:.3e}`，T最大差 `{verification['q3_regression']['T']:.3e}`。
- 主方案空间加密差：`{verification['spatial'][-1]['time_difference_s']:.6g}` s，C最大差 `{verification['spatial'][-1]['C']:.3e}`。
- 估计数值时间改变量：`{verification['estimated_numerical_time_change_s']:.6g}` s。
- 空间加密预算门禁：`passed = {verification['spatial_budget']['passed']}`。
- 水分总体平衡、温度历史包络、半径单调、域外空白掩码、严格越阈均已通过程序检查。
- Excel交付回读：{export_evidence['rows']} 行、{export_evidence['columns']} 列，工作簿 SHA-256 `{export_evidence['workbook_sha256']}`。
- 单元测试证据：`results/q4/unit_tests.txt`。

该估计不是严格 PDE 误差界；它只绑定当前离散、事件括号和同源求解器对照。
""", encoding="utf-8")
    index = Path("reports/RESULTS_REPORT.md")
    index.write_text("""# 计算结果索引

第一问数值基准与灵敏度、第二问72 h变物性热湿耦合结果、第三问固定尺寸全域干燥事件，以及第四问收缩域全域干燥事件已交付。

- [第一问结果与表1-2](Q1_RESULTS_REPORT.md)
- [第二问结果与表3-4](Q2_RESULTS_REPORT.md)
- [第三问结果与表5](Q3_RESULTS_REPORT.md)
- [第四问结果与表6](Q4_RESULTS_REPORT.md)
- [第四问验证](Q4_VERIFY_REPORT.md)
""", encoding="utf-8")
    write_json(directory / "report_manifest.json", {
        "reports": {str(path): sha256(path) for path in [
            Path("reports/Q4_MODEL_SPEC.md"),
            Path("reports/Q4_RESULTS_REPORT.md"),
            Path("reports/Q4_VERIFY_REPORT.md"),
            index,
        ]},
        "verification_sha256": portable_artifact_sha256(directory / "verification.json"),
        "export_verification_sha256": portable_artifact_sha256(directory / "export_verification.json"),
    })


if __name__ == "__main__":
    write_reports()

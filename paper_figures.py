"""Generate the six main paper figures from verified question-level evidence."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch
import numpy as np

from common.hashing import file_record, verify_file
from q2.archive import write_json
from q3.validation import verified as q3_verified
from q4.validation import verified as q4_verified


COLORS = {
    "blue": "#176B8B",
    "blue_dark": "#183A59",
    "green": "#407F46",
    "gold": "#B47B23",
    "red": "#A64949",
    "gray": "#666666",
}


def _font() -> str:
    available = {font.name for font in font_manager.fontManager.ttflist}
    selected = next(
        (name for name in ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC"] if name in available),
        None,
    )
    if selected is None:
        raise RuntimeError("A Chinese font is required")
    return selected


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _save(fig, path: Path) -> None:
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def _verify_q2_figure_source() -> Path:
    manifest_path = Path("results/q2/figure_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 2:
        raise ValueError("Versioned Q2 figure evidence is required")
    source = Path("results/q2/figure_data/q1_q2_first_1800s.csv")
    verify_file("q2/figures.py", manifest["generator"])
    verify_file("results/q2/verification.json", manifest["verification"])
    verify_file(source, manifest["csv"][source.name])
    return source


def _roadmap(source_dir: Path, figure_dir: Path) -> None:
    nodes = [
        {"id": "input", "x": 0.01, "y": 0.62, "w": 0.13, "h": 0.20, "label": "题面与附件\n环境、半径、物性"},
        {"id": "q1", "x": 0.18, "y": 0.62, "w": 0.13, "h": 0.20, "label": "问题一\n常物性传递"},
        {"id": "q2", "x": 0.35, "y": 0.62, "w": 0.13, "h": 0.20, "label": "问题二\n变物性耦合"},
        {"id": "q3", "x": 0.52, "y": 0.62, "w": 0.13, "h": 0.20, "label": "问题三\n全域达标事件"},
        {"id": "q4", "x": 0.69, "y": 0.62, "w": 0.13, "h": 0.20, "label": "问题四\n收缩与物性机制"},
        {"id": "verify", "x": 0.18, "y": 0.18, "w": 0.65, "h": 0.20, "label": "统一验证\n守恒、Jacobian、网格、时间、方法、根定位"},
        {"id": "delivery", "x": 0.86, "y": 0.62, "w": 0.12, "h": 0.20, "label": "表格\n图源\n报告"},
    ]
    edges = [
        ("input", "q1", "边界与初值"),
        ("q1", "q2", "求解器退化核验"),
        ("q2", "q3", "同一场变量"),
        ("q3", "q4", "事件判据"),
        ("q4", "delivery", "A–D 对照"),
        ("q1", "verify", ""),
        ("q2", "verify", ""),
        ("q3", "verify", ""),
        ("q4", "verify", ""),
        ("verify", "delivery", "证据门禁"),
    ]
    _write_rows(source_dir / "fig01_model_roadmap_nodes.csv", list(nodes[0]), nodes)
    _write_rows(
        source_dir / "fig01_model_roadmap_edges.csv",
        ["source", "target", "label"],
        [{"source": source, "target": target, "label": label} for source, target, label in edges],
    )
    by_id = {node["id"]: node for node in nodes}
    fig, ax = plt.subplots(figsize=(10.2, 4.2), layout="constrained")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fills = ["#E8F1F5", "#E8F1F5", "#EDF3E9", "#F8F0DF", "#F8E9E9", "#F0F0F0", "#E7EDF2"]
    for node, fill in zip(nodes, fills):
        patch = FancyBboxPatch(
            (node["x"], node["y"]), node["w"], node["h"],
            boxstyle="round,pad=0.008,rounding_size=0.015",
            facecolor=fill, edgecolor="#52616B", linewidth=1.1,
        )
        ax.add_patch(patch)
        ax.text(node["x"] + node["w"] / 2, node["y"] + node["h"] / 2, node["label"], ha="center", va="center")
    for source, target, label in edges:
        a, b = by_id[source], by_id[target]
        start = (a["x"] + a["w"], a["y"] + a["h"] / 2)
        end = (b["x"], b["y"] + b["h"] / 2)
        if source in {"q1", "q2", "q3", "q4"} and target == "verify":
            start = (a["x"] + a["w"] / 2, a["y"])
            end = (b["x"] + min(max(start[0] - b["x"], 0.03), b["w"] - 0.03), b["y"] + b["h"])
        ax.annotate("", xy=end, xytext=start, arrowprops={"arrowstyle": "->", "color": "#52616B", "lw": 1.0})
        if label:
            ax.text((start[0] + end[0]) / 2, (start[1] + end[1]) / 2 + 0.025, label, ha="center", fontsize=7, color=COLORS["gray"])
    _save(fig, figure_dir / "fig01_model_roadmap.pdf")


def _environment_and_radius(source_dir: Path, figure_dir: Path, q4_fields: dict) -> None:
    environment = np.genfromtxt("results/q2/environment.csv", delimiter=",", names=True)
    observed_end_s = 14400.0
    mean_mask = environment["time_s"] >= 10800.0
    mean_T = float(np.mean(environment["temperature_C"][mean_mask]))
    mean_C = float(np.mean(environment["equivalent_moisture"][mean_mask]))
    extension_time = np.arange(observed_end_s, 259200.0 + 1, 900.0)
    rows = []
    for row in environment:
        rows.append({"variable": "environment_temperature_C", "time_h": f"{row['time_s'] / 3600:.17g}", "value": f"{row['temperature_C']:.17g}", "segment": "observed"})
        rows.append({"variable": "environment_moisture", "time_h": f"{row['time_s'] / 3600:.17g}", "value": f"{row['equivalent_moisture']:.17g}", "segment": "observed"})
    for time_s in extension_time[1:]:
        rows.append({"variable": "environment_temperature_C", "time_h": f"{time_s / 3600:.17g}", "value": f"{mean_T:.17g}", "segment": "last_hour_mean_extension"})
        rows.append({"variable": "environment_moisture", "time_h": f"{time_s / 3600:.17g}", "value": f"{mean_C:.17g}", "segment": "last_hour_mean_extension"})
    for time_s, radius_m in zip(q4_fields["time_s"], q4_fields["surface_radius_m"]):
        rows.append({
            "variable": "surface_radius_cm",
            "time_h": f"{time_s / 3600:.17g}",
            "value": f"{radius_m * 100:.17g}",
            "segment": "observed_or_interpolated" if time_s <= observed_end_s else "linear_extension_with_floor",
        })
    _write_rows(source_dir / "fig02_environment_radius.csv", ["variable", "time_h", "value", "segment"], rows)

    fig, axes = plt.subplots(1, 3, figsize=(10.2, 3.2), layout="constrained")
    obs_h = environment["time_s"] / 3600.0
    ext_h = extension_time / 3600.0
    axes[0].plot(obs_h, environment["temperature_C"], color=COLORS["blue"], label="附件观测")
    axes[0].plot(ext_h, np.full_like(ext_h, mean_T), "--", color=COLORS["gold"], label="末小时均值延拓")
    axes[0].axvline(4, color=COLORS["gray"], ls=":", linewidth=0.8)
    axes[0].text(4.15, mean_T - 1.0, "4–72 h 均值保持", fontsize=7, color=COLORS["gray"])
    axes[0].set(xlabel="时间 / h", ylabel="环境温度 / °C", xlim=(0, 8))
    axes[0].legend(frameon=False, fontsize=7)
    axes[1].plot(obs_h, environment["equivalent_moisture"], color=COLORS["green"])
    axes[1].plot(ext_h, np.full_like(ext_h, mean_C), "--", color=COLORS["gold"])
    axes[1].axvline(4, color=COLORS["gray"], ls=":", linewidth=0.8)
    axes[1].text(4.15, mean_C - 0.002, "4–72 h 均值保持", fontsize=7, color=COLORS["gray"])
    axes[1].set(xlabel="时间 / h", ylabel="环境平衡含水率 / (kg/kg)", xlim=(0, 8))
    radius_h = q4_fields["time_s"] / 3600.0
    observed = radius_h <= 4
    axes[2].plot(radius_h[observed], q4_fields["surface_radius_m"][observed] * 100, color=COLORS["red"], label="附件记录")
    axes[2].plot(radius_h[~observed], q4_fields["surface_radius_m"][~observed] * 100, "--", color=COLORS["red"], label="线性延拓并限幅")
    axes[2].set(xlabel="时间 / h", ylabel="材料表面半径 / cm")
    axes[2].legend(frameon=False, fontsize=7)
    _save(fig, figure_dir / "fig02_environment_radius.pdf")


def _q1_q2_early(source_dir: Path, figure_dir: Path) -> None:
    source = _verify_q2_figure_source()
    data = np.genfromtxt(source, delimiter=",", names=True)
    rows = []
    for row in data:
        rows.append({name: f"{float(row[name]):.17g}" for name in data.dtype.names})
    _write_rows(source_dir / "fig03_q1_q2_early.csv", list(data.dtype.names), rows)
    time_min = data["time_s"] / 60.0
    fig, axes = plt.subplots(2, 2, figsize=(8.6, 5.8), sharex=True, layout="constrained")
    series = [
        (axes[0, 0], "q1_center_T", "q2_center_T", "中心温度", "温度 / °C", False),
        (axes[0, 1], "q1_surface_T", "q2_surface_T", "表面温度", "温度 / °C", False),
        (axes[1, 0], "q1_center_C", "q2_center_C", "中心含水率变化", r"$(C-2.55)\times10^5$", True),
        (axes[1, 1], "q1_surface_C", "q2_surface_C", "表面含水率", "干基含水率 / (kg/kg)", False),
    ]
    for axis, q1_name, q2_name, title, ylabel, centered in series:
        q1_values = (data[q1_name] - 2.55) * 1e5 if centered else data[q1_name]
        q2_values = (data[q2_name] - 2.55) * 1e5 if centered else data[q2_name]
        axis.plot(time_min, q1_values, "--", color=COLORS["gray"], label="Q1 常物性")
        axis.plot(time_min, q2_values, color=COLORS["blue"], label="Q2 变物性")
        axis.set(title=title, ylabel=ylabel)
    axes[1, 0].set_xlabel("时间 / min")
    axes[1, 1].set_xlabel("时间 / min")
    axes[0, 0].legend(frameon=False, fontsize=8)
    _save(fig, figure_dir / "fig03_q1_q2_early.pdf")


def _physical_radius(
    source_dir: Path,
    figure_dir: Path,
    q3_record: dict,
    q3_fields: dict,
    q4_record: dict,
    q4_fields: dict,
) -> None:
    profile_rows = []
    targets = [("24 h", 86400.0), ("event", None)]
    for question, record, fields in (("Q3", q3_record, q3_fields), ("Q4", q4_record, q4_fields)):
        for time_label, target in targets:
            target_s = float(record["root"]["time_s"] if target is None else target)
            index = int(np.argmin(abs(fields["time_s"] - target_s)))
            if question == "Q3":
                radii = np.arange(21, dtype=float) / 10.0
                values = fields["moisture"][index]
                surface_radius = 2.0
                surface_C = float(values[-1])
            else:
                radii = fields["fixed_radius_m"] * 100.0
                values = fields["moisture"][index, :21]
                surface_radius = float(fields["surface_radius_m"][index] * 100.0)
                surface_C = float(fields["moisture"][index, 21])
            for radius_cm, value in zip(radii, values):
                if np.isfinite(value) and radius_cm <= surface_radius + 1e-10:
                    profile_rows.append({
                        "question": question,
                        "time_label": time_label,
                        "time_h": f"{fields['time_s'][index] / 3600:.17g}",
                        "radius_cm": f"{radius_cm:.17g}",
                        "C": f"{value:.17g}",
                        "point_type": "fixed_radius",
                    })
            profile_rows.append({
                "question": question,
                "time_label": time_label,
                "time_h": f"{fields['time_s'][index] / 3600:.17g}",
                "radius_cm": f"{surface_radius:.17g}",
                "C": f"{surface_C:.17g}",
                "point_type": "surface",
            })
    _write_rows(
        source_dir / "fig04_physical_profiles.csv",
        ["question", "time_label", "time_h", "radius_cm", "C", "point_type"],
        profile_rows,
    )
    radius_rows = []
    for time_s in q3_fields["time_s"][::20]:
        radius_rows.append({"question": "Q3", "time_h": f"{time_s / 3600:.17g}", "surface_radius_cm": "2"})
    for time_s, radius_m in zip(q4_fields["time_s"][::20], q4_fields["surface_radius_m"][::20]):
        radius_rows.append({"question": "Q4", "time_h": f"{time_s / 3600:.17g}", "surface_radius_cm": f"{radius_m * 100:.17g}"})
    _write_rows(source_dir / "fig04_surface_radius.csv", ["question", "time_h", "surface_radius_cm"], radius_rows)

    fig, axes = plt.subplots(1, 3, figsize=(10.2, 3.2), layout="constrained")
    for axis, time_label, title in zip(axes[:2], ["24 h", "event"], ["24 h 径向剖面", "各自达标时径向剖面"]):
        for question, color in (("Q3", COLORS["blue"]), ("Q4", COLORS["red"])):
            fixed = [row for row in profile_rows if row["question"] == question and row["time_label"] == time_label and row["point_type"] == "fixed_radius"]
            surface = [row for row in profile_rows if row["question"] == question and row["time_label"] == time_label and row["point_type"] == "surface"][0]
            axis.plot([float(row["radius_cm"]) for row in fixed], [float(row["C"]) for row in fixed], color=color, label=question)
            axis.scatter(float(surface["radius_cm"]), float(surface["C"]), marker="D", s=24, color=color, edgecolor="white", linewidth=0.4, zorder=3)
        axis.axhline(0.15, color=COLORS["gray"], ls=":", linewidth=0.8)
        axis.set(xlabel="物理半径 / cm", ylabel="干基含水率 / (kg/kg)", title=title)
    axes[0].legend(frameon=False, fontsize=8)
    axes[2].plot(q3_fields["time_s"] / 3600.0, np.full_like(q3_fields["time_s"], 2.0), color=COLORS["blue"], label="Q3 固定半径")
    axes[2].plot(q4_fields["time_s"] / 3600.0, q4_fields["surface_radius_m"] * 100.0, color=COLORS["red"], label="Q4 收缩半径")
    axes[2].set(xlabel="时间 / h", ylabel="材料表面半径 / cm", title="物理域边界")
    axes[2].legend(frameon=False, fontsize=8)
    _save(fig, figure_dir / "fig04_physical_radius_drying.pdf")


def _criteria_and_numerics(source_dir: Path, figure_dir: Path, verification: dict, record: dict, fields: dict) -> None:
    rows = []
    for summary in fields["summary"][::5]:
        rows.append({
            "time_h": f"{summary[0] / 3600:.17g}",
            "surface_C": f"{summary[7]:.17g}",
            "mean_C": f"{summary[6]:.17g}",
            "global_max_C": f"{summary[2]:.17g}",
        })
    _write_rows(source_dir / "fig05_criteria.csv", ["time_h", "surface_C", "mean_C", "global_max_C"], rows)
    numerical = [
        {"layer": "空间 N=10240→20480", "time_scale_s": verification["spatial"][-1]["root_time_difference_s"]},
        {"layer": "时间步与容差", "time_scale_s": verification["temporal"][0]["root_time_difference_s"]},
        {"layer": "BDF 与 Radau", "time_scale_s": verification["method"]["comparison"]["root_time_difference_s"]},
        {"layer": "根区间宽度", "time_scale_s": verification["root_resolution"]["formal_bracket_width_s"]},
    ]
    _write_rows(
        source_dir / "fig05_numerical_layers.csv",
        ["layer", "time_scale_s"],
        [{"layer": item["layer"], "time_scale_s": f"{item['time_scale_s']:.17g}"} for item in numerical],
    )
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.4), layout="constrained")
    time_h = fields["summary"][:, 0] / 3600.0
    axes[0].plot(time_h, fields["summary"][:, 7], color=COLORS["red"], label="表面")
    axes[0].plot(time_h, fields["summary"][:, 6], "--", color=COLORS["gold"], label="体积平均")
    axes[0].plot(time_h, fields["summary"][:, 2], color=COLORS["blue"], label="全域最大")
    axes[0].axhline(0.15, color=COLORS["gray"], ls=":", label="全域判据")
    axes[0].axvline(record["root"]["time_h"], color=COLORS["gray"], ls=":", linewidth=0.8)
    axes[0].set(xlabel="时间 / h", ylabel="干基含水率 / (kg/kg)")
    axes[0].legend(frameon=False, fontsize=8, ncols=2)
    values = [item["time_scale_s"] for item in numerical]
    axes[1].bar(np.arange(4), values, color=[COLORS["blue"], COLORS["gold"], COLORS["red"], COLORS["gray"]])
    axes[1].set_yscale("log")
    axes[1].set_xticks(np.arange(4), [item["layer"] for item in numerical], rotation=25, ha="right", fontsize=8)
    axes[1].set(ylabel="临界时间数值差异尺度 / s", title="数值层分开报告")
    _save(fig, figure_dir / "fig05_criteria_numerical_layers.pdf")


def _mechanism_and_structure(source_dir: Path, figure_dir: Path, verification: dict) -> None:
    sensitivity_path = Path("results/q4/sensitivity/summary.json")
    sensitivity = json.loads(sensitivity_path.read_text(encoding="utf-8"))
    if sensitivity.get("passed") is not True:
        raise ValueError("Verified Q4 sensitivity evidence is required")
    case_rows = []
    for item in verification["table6_summary"]:
        case_rows.append({"case": item["case"][0], "time_h": f"{item['time_h']:.17g}", "radius_cm": f"{item['event_radius_cm']:.17g}"})
    _write_rows(source_dir / "fig06_cases.csv", ["case", "time_h", "radius_cm"], case_rows)
    sensitivity_rows = [
        {
            "scenario": item["scenario"],
            "event_time_h": f"{item['event_time_h']:.17g}",
            "delta_vs_linear_min": f"{item['event_delta_vs_linear_s'] / 60:.17g}",
        }
        for item in sensitivity["scenarios"]
    ]
    _write_rows(source_dir / "fig06_structural_scenarios.csv", ["scenario", "event_time_h", "delta_vs_linear_min"], sensitivity_rows)

    fig, axes = plt.subplots(1, 2, figsize=(9.3, 3.4), layout="constrained")
    case_times = [float(row["time_h"]) for row in case_rows]
    bars = axes[0].bar(np.arange(4), case_times, color=["#6B8EAD", COLORS["green"], "#C08A34", COLORS["red"]])
    axes[0].bar_label(bars, labels=[f"{value:.2f}" for value in case_times], padding=3, fontsize=8)
    axes[0].set_xticks(np.arange(4), ["A\n附3 固定", "B\n附3 收缩", "C\n附4 固定", "D\n附4 收缩"])
    axes[0].set(ylabel="全域达标时间 / h", title="物性 × 几何的 2×2 对照")
    scenario_plot = [row for row in sensitivity_rows if row["scenario"] != "linear"]
    values = [float(row["delta_vs_linear_min"]) for row in scenario_plot]
    labels = ["PCHIP", "半径下移", "半径上移", "末值环境"]
    bars = axes[1].bar(np.arange(4), values, color=[COLORS["blue"] if value < 0 else COLORS["red"] for value in values])
    axes[1].axhline(0, color="#444444", linewidth=0.8)
    axes[1].bar_label(bars, labels=[f"{value:+.2f}" for value in values], padding=3, fontsize=8)
    axes[1].set_xticks(np.arange(4), labels, rotation=18, ha="right")
    axes[1].set(ylabel="相对线性基准 / min", title="确定性结构情景（非置信区间）")
    _save(fig, figure_dir / "fig06_mechanism_structural_sensitivity.pdf")


def make(output="figures/paper", source="results/paper_figure_data") -> None:
    figure_dir, source_dir = Path(output), Path(source)
    figure_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)
    font = _font()
    plt.rcParams.update({
        "font.family": font,
        "font.size": 9,
        "axes.unicode_minus": False,
        "pdf.fonttype": 42,
        "axes.spines.top": False,
        "axes.spines.right": False,
    })

    q3_verification, q3_record, q3_fields = q3_verified("results/q3")
    q4_verification, q4_record, q4_fields = q4_verified("results/q4")
    _roadmap(source_dir, figure_dir)
    _environment_and_radius(source_dir, figure_dir, q4_fields)
    _q1_q2_early(source_dir, figure_dir)
    _physical_radius(source_dir, figure_dir, q3_record, q3_fields, q4_record, q4_fields)
    _criteria_and_numerics(source_dir, figure_dir, q4_verification, q4_record, q4_fields)
    _mechanism_and_structure(source_dir, figure_dir, q4_verification)

    pdf_paths = sorted(figure_dir.glob("fig*.pdf"))
    if len(pdf_paths) != 6:
        raise RuntimeError(f"Expected six main paper figures, found {len(pdf_paths)}")
    drawio_path = figure_dir / "fig01_model_roadmap.drawio"
    if not drawio_path.exists():
        raise FileNotFoundError(drawio_path)
    write_json("results/paper_figure_manifest.json", {
        "schema_version": 2,
        "font": font,
        "generator": file_record("paper_figures.py"),
        "drawio_source": file_record(drawio_path),
        "evidence": {
            "q2_figure_manifest": file_record("results/q2/figure_manifest.json"),
            "q3_verification": file_record("results/q3/verification.json"),
            "q4_verification": file_record("results/q4/verification.json"),
            "q4_sensitivity": file_record("results/q4/sensitivity/summary.json"),
        },
        "csv": {path.name: file_record(path) for path in sorted(source_dir.glob("*.csv"))},
        "pdf": {path.name: file_record(path) for path in pdf_paths},
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="figures/paper")
    parser.add_argument("--source", default="results/paper_figure_data")
    args = parser.parse_args()
    make(args.output, args.source)

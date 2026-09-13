"""Paper-ready Q4 figures from verified numeric sources."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

from common.hashing import file_record, verify_file
from q2.archive import write_json
from q4.sensitivity import verified_summary
from q4.validation import verified


CASE_LABELS = {
    "A_appendix3_fixed_N5120": "A: 附录3，固定半径",
    "B_appendix3_shrink_N5120": "B: 附录3，收缩半径",
    "C_appendix4_fixed_N5120": "C: 附录4，固定半径",
    "D_appendix4_shrink_N5120": "D: 附录4，收缩半径",
}


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _font() -> str:
    available = {font.name for font in font_manager.fontManager.ttflist}
    selected = next(
        (name for name in ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC"] if name in available),
        None,
    )
    if selected is None:
        raise RuntimeError("A Chinese font is required")
    return selected


def _load_sensitivity(directory: Path) -> dict:
    return verified_summary(directory / "sensitivity")


def make(directory="results/q4", figure_dir="figures/q4"):
    directory, figure_dir = Path(directory), Path(figure_dir)
    source = directory / "figure_data"
    source.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    verification, record, fields = verified(directory)
    sensitivity = _load_sensitivity(directory)

    font = _font()
    plt.rcParams.update({
        "font.family": font,
        "font.size": 9,
        "axes.unicode_minus": False,
        "pdf.fonttype": 42,
        "axes.spines.top": False,
        "axes.spines.right": False,
    })

    trace = np.loadtxt(
        directory / "runs" / verification["formal_case"] / "accepted_steps.csv",
        delimiter=",",
        skiprows=1,
    )
    response = np.vstack([
        fields["summary"][:1],
        np.atleast_2d(trace)[:, :12],
        np.asarray(record["root"]["near_summary"], dtype=float),
    ])
    response = response[np.argsort(response[:, 0], kind="stable")]
    _, unique_indices = np.unique(response[:, 0], return_index=True)
    response = response[np.sort(unique_indices)]
    np.savetxt(
        source / "response.csv",
        response,
        delimiter=",",
        fmt="%.17g",
        comments="",
        header=(
            "time_s,radius_m,Cmax,argmax_xi,argmax_radius_m,center_C,mean_C,"
            "surface_C,Cmin,Tmin_C,Tmax_C,radial_increase"
        ),
    )
    np.savetxt(
        source / "radius.csv",
        np.c_[fields["time_s"], fields["surface_radius_m"]],
        delimiter=",",
        fmt="%.17g",
        comments="",
        header="time_s,surface_radius_m",
    )

    profile_times = [21600.0, 43200.0, 86400.0, 129600.0, float(record["root"]["time_s"])]
    profile_rows = []
    selected_times = []
    for target_time in profile_times:
        index = int(np.argmin(abs(fields["time_s"] - target_time)))
        time_s = float(fields["time_s"][index])
        selected_times.append(time_s)
        surface_radius_m = float(fields["surface_radius_m"][index])
        for radius_m, moisture in zip(fields["fixed_radius_m"], fields["moisture"][index, :21]):
            if (np.isfinite(moisture) and radius_m < surface_radius_m - 1e-12):
                profile_rows.append({
                    "time_s": f"{time_s:.17g}",
                    "radius_cm": f"{radius_m * 100:.17g}",
                    "C": f"{moisture:.17g}",
                    "point_type": "fixed_radius",
                })
        profile_rows.append({
            "time_s": f"{time_s:.17g}",
            "radius_cm": f"{surface_radius_m * 100:.17g}",
            "C": f"{fields['moisture'][index, 21]:.17g}",
            "point_type": "dynamic_surface",
        })
    _write_rows(
        source / "fixed_radius_profiles.csv",
        ["time_s", "radius_cm", "C", "point_type"],
        profile_rows,
    )

    case_rows = []
    for item in verification["table6_summary"]:
        if item["case"] not in CASE_LABELS or item["status"] != "event":
            raise ValueError(f"Q4 case {item['case']} does not contain a resolved event")
        case_rows.append({
            "case": item["case"],
            "label": CASE_LABELS[item["case"]],
            "time_h": f"{item['time_h']:.17g}",
            "event_radius_cm": f"{item['event_radius_cm']:.17g}",
            "surface_C_at_event": f"{item['surface_C_at_event']:.17g}",
            "center_C_at_event": f"{item['center_C_at_event']:.17g}",
        })
    _write_rows(
        source / "case_summary.csv",
        ["case", "label", "time_h", "event_radius_cm", "surface_C_at_event", "center_C_at_event"],
        case_rows,
    )

    numerical_rows = []
    comparisons = [
        ("空间", "N=5120→10240", verification["spatial"][0]),
        ("空间", "N=10240→20480", verification["spatial"][1]),
        ("时间", "BDF 基准→收紧", verification["temporal"][0]),
        ("方法", "N=5120 BDF→Radau", verification["method"]["comparison"]),
    ]
    for layer, label, item in comparisons:
        numerical_rows.append({
            "layer": layer,
            "comparison": label,
            "root_difference_s": f"{item['root_time_difference_s']:.17g}",
            "max_abs_C": f"{item['field_difference']['C']['max_abs']:.17g}",
            "max_abs_T_C": f"{item['field_difference']['T']['max_abs']:.17g}",
            "dynamic_surface_included": str(item["field_difference"]["dynamic_surface_included"]).lower(),
        })
    _write_rows(
        source / "numerical_comparisons.csv",
        ["layer", "comparison", "root_difference_s", "max_abs_C", "max_abs_T_C", "dynamic_surface_included"],
        numerical_rows,
    )

    structural_rows = []
    for item in sensitivity["scenarios"]:
        structural_rows.append({
            "scenario": item["scenario"],
            "event_time_h": f"{item['event_time_h']:.17g}",
            "event_delta_vs_linear_s": f"{item['event_delta_vs_linear_s']:.17g}",
            "radius_offset_cm": f"{item['radius_offset_cm']:.17g}",
            "radius_interpolation": item["radius_interpolation"],
            "environment_mode": item["environment_mode"],
        })
    _write_rows(
        source / "structural_sensitivity.csv",
        [
            "scenario", "event_time_h", "event_delta_vs_linear_s", "radius_offset_cm",
            "radius_interpolation", "environment_mode",
        ],
        structural_rows,
    )

    pdf_paths = []

    def save(fig, name):
        path = figure_dir / f"{name}.pdf"
        fig.savefig(path, bbox_inches="tight")
        plt.close(fig)
        pdf_paths.append(path)

    response_data = np.loadtxt(source / "response.csv", delimiter=",", skiprows=1)
    radius_data = np.loadtxt(source / "radius.csv", delimiter=",", skiprows=1)
    time_h = response_data[:, 0] / 3600.0

    fig, axes = plt.subplots(2, 1, figsize=(6.5, 5.0), sharex=True, layout="constrained")
    axes[0].plot(time_h, response_data[:, 2], color="#176B8B", label="全域最大值", linewidth=1.7)
    axes[0].plot(time_h, response_data[:, 6], "--", color="#B47B23", label="体积平均值")
    axes[0].plot(time_h, response_data[:, 7], color="#A64949", label="动态表面值")
    axes[0].axhline(0.15, color="#555555", ls=":", label="判据 0.15")
    axes[0].set(ylabel="干基含水率 / (kg/kg)", xlim=(0, record["root"]["time_h"]))
    axes[0].legend(frameon=False, ncols=2, fontsize=8)
    axes[1].plot(radius_data[:, 0] / 3600.0, radius_data[:, 1] * 100, color="#407F46", linewidth=1.6)
    axes[1].set(xlabel="时间 / h", ylabel="材料表面半径 / cm")
    save(fig, "q4_moisture_radius")

    with (source / "fixed_radius_profiles.csv").open("r", encoding="utf-8", newline="") as stream:
        plotted_profiles = list(csv.DictReader(stream))
    fig, ax = plt.subplots(figsize=(6.5, 3.4), layout="constrained")
    colors = plt.colormaps["viridis"](np.linspace(0.05, 0.85, len(selected_times)))
    for selected_time, color in zip(selected_times, colors):
        points = sorted(
            [row for row in plotted_profiles if float(row["time_s"]) == selected_time],
            key=lambda row: float(row["radius_cm"]),
        )
        surface = [row for row in points if row["point_type"] == "dynamic_surface"][0]
        label = f"{selected_time / 3600:.0f} h"
        if np.isclose(selected_time, record["root"]["time_s"]):
            label = f"结束 {record['root']['time_h']:.4f} h"
        ax.plot(
            [float(row["radius_cm"]) for row in points],
            [float(row["C"]) for row in points],
            color=color,
            label=label,
        )
        ax.scatter(
            float(surface["radius_cm"]),
            float(surface["C"]),
            marker="D",
            s=22,
            color=color,
            edgecolor="white",
            linewidth=0.45,
            zorder=3,
        )
    ax.axhline(0.15, color="#555555", ls=":", linewidth=1)
    ax.set(xlabel="物理半径 / cm", ylabel="干基含水率 / (kg/kg)")
    ax.legend(frameon=False, fontsize=7, ncols=2)
    ax.text(0.01, 0.03, "菱形为各时刻真实动态表面", transform=ax.transAxes, fontsize=8, color="#555555")
    save(fig, "q4_fixed_radius_profiles")

    fig, ax = plt.subplots(figsize=(6.4, 3.4), layout="constrained")
    labels = [row["label"] for row in case_rows]
    times_h = [float(row["time_h"]) for row in case_rows]
    bars = ax.bar(np.arange(4), times_h, color=["#6B8EAD", "#407F46", "#C08A34", "#A64949"])
    ax.bar_label(bars, labels=[f"{value:.2f} h" for value in times_h], padding=3, fontsize=8)
    ax.set_xticks(np.arange(4), labels, rotation=18, ha="right")
    ax.set(ylabel="达到全域判据的时间 / h")
    ax.set_ylim(0, max(times_h) * 1.13)
    save(fig, "q4_case_comparison")

    fig, axes = plt.subplots(1, 3, figsize=(9.2, 3.2), layout="constrained")
    comparison_labels = [row["comparison"] for row in numerical_rows]
    numerical_values = [
        ("临界时间差 / s", [float(row["root_difference_s"]) for row in numerical_rows]),
        ("最大含水率差", [float(row["max_abs_C"]) for row in numerical_rows]),
        ("最大温度差 / °C", [float(row["max_abs_T_C"]) for row in numerical_rows]),
    ]
    for axis, (ylabel, values) in zip(axes, numerical_values):
        axis.bar(np.arange(4), values, color=["#6B8EAD", "#3F6F8F", "#B47B23", "#A64949"])
        axis.set_yscale("log")
        axis.set_xticks(np.arange(4), comparison_labels, rotation=32, ha="right", fontsize=7)
        axis.set_ylabel(ylabel)
        axis.grid(axis="y", which="both", color="#DDDDDD", linewidth=0.5)
    save(fig, "q4_numerical_comparisons")

    structural_plot = [row for row in structural_rows if row["scenario"] != "linear"]
    structural_labels = ["PCHIP", "半径记录下移", "半径记录上移", "末值环境保持"]
    structural_minutes = [float(row["event_delta_vs_linear_s"]) / 60.0 for row in structural_plot]
    fig, ax = plt.subplots(figsize=(6.4, 3.3), layout="constrained")
    colors = ["#6B8EAD" if value < 0 else "#A64949" for value in structural_minutes]
    bars = ax.bar(np.arange(len(structural_minutes)), structural_minutes, color=colors)
    ax.axhline(0, color="#444444", linewidth=0.8)
    ax.bar_label(bars, labels=[f"{value:+.2f} min" for value in structural_minutes], padding=3, fontsize=8)
    ax.set_xticks(np.arange(len(structural_labels)), structural_labels, rotation=18, ha="right")
    ax.set(ylabel="相对线性基准的临界时间变化 / min")
    ax.text(0.01, 0.97, "确定性结构情景，不是置信区间", transform=ax.transAxes, va="top", fontsize=8, color="#555555")
    save(fig, "q4_structural_sensitivity")

    csv_paths = sorted(source.glob("*.csv"))
    write_json(directory / "figure_manifest.json", {
        "schema_version": 3,
        "font": font,
        "generator": file_record("q4/figures.py"),
        "verification": file_record(directory / "verification.json"),
        "sensitivity_summary": file_record(directory / "sensitivity" / "summary.json"),
        "csv": {path.name: file_record(path) for path in csv_paths},
        "pdf": {path.name: file_record(path) for path in pdf_paths},
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", default="results/q4")
    parser.add_argument("--figure-dir", default="figures/q4")
    args = parser.parse_args()
    make(args.directory, args.figure_dir)

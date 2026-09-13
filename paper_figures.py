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
from matplotlib.patches import Circle, FancyBboxPatch
import numpy as np

from common.hashing import TEXT_HASH_SCHEME, file_record, verify_file
from q2.archive import write_json
from q3.validation import verified as q3_verified
from q4.provenance import load_run as load_q4_run
from q4.sensitivity import verified_summary
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


def _read_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _panel_label(axis, label: str) -> None:
    axis.text(
        0.01, 0.98, label, transform=axis.transAxes, ha="left", va="top",
        fontsize=9, fontweight="bold",
    )


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
        {"id": "input", "x": 0.31, "y": 0.73, "w": 0.16, "h": 0.15, "label": "题面与附件\n边界、半径、物性"},
        {"id": "q1", "x": 0.54, "y": 0.73, "w": 0.18, "h": 0.15, "label": "问题一：附录2\n常热物性、D(C)"},
        {"id": "q2", "x": 0.31, "y": 0.42, "w": 0.18, "h": 0.15, "label": "问题二：附录3\n从原初值独立积分"},
        {"id": "q3", "x": 0.56, "y": 0.42, "w": 0.16, "h": 0.15, "label": "问题三\n全域达标事件"},
        {"id": "q4", "x": 0.79, "y": 0.42, "w": 0.18, "h": 0.15, "label": "问题四：附录4\nR(t) 收缩域"},
        {"id": "verify", "x": 0.31, "y": 0.10, "w": 0.49, "h": 0.15, "label": "分层验证：守恒、Jacobian、网格、时间、Radau、近根状态"},
        {"id": "delivery", "x": 0.84, "y": 0.10, "w": 0.13, "h": 0.15, "label": "表格、图源\n报告与审计"},
    ]
    edges = [
        ("input", "q1", "题设参数", "solid"),
        ("input", "q2", "原始初值 + 附录3", "solid"),
        ("q1", "q2", "冻结物性退化核验", "dashed"),
        ("q2", "q3", "同一场变量", "solid"),
        ("q3", "q4", "继承全域判据", "solid"),
        ("q4", "delivery", "A–D 与正式结果", "solid"),
        ("q2", "verify", "", "solid"),
        ("q3", "verify", "", "solid"),
        ("q4", "verify", "", "solid"),
        ("verify", "delivery", "证据门禁", "solid"),
    ]
    _write_rows(source_dir / "fig01_model_roadmap_nodes.csv", list(nodes[0]), nodes)
    _write_rows(
        source_dir / "fig01_model_roadmap_edges.csv",
        ["source", "target", "label", "style"],
        [
            {"source": source, "target": target, "label": label, "style": style}
            for source, target, label, style in edges
        ],
    )
    _write_rows(
        source_dir / "fig01_model_geometry.csv",
        ["item", "label"],
        [
            {"item": "center", "label": "r=0, xi=0"},
            {"item": "surface", "label": "r=R(t), xi=1"},
            {"item": "heat_flux", "label": "-k theta_r = h(theta_s-T_e)"},
            {"item": "mass_flux", "label": "-D C_r = h_m(C_s-C_e)"},
        ],
    )
    by_id = {node["id"]: node for node in nodes}
    fig, ax = plt.subplots(figsize=(10.6, 5.0), layout="constrained")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    center = (0.145, 0.55)
    radius = 0.105
    ax.add_patch(Circle(center, radius, facecolor="#F6F6F3", edgecolor="#52616B", linewidth=1.2))
    ax.plot(center[0], center[1], "o", color=COLORS["blue_dark"], ms=3)
    ax.annotate(
        "", xy=(center[0] + radius, center[1]), xytext=center,
        arrowprops={"arrowstyle": "->", "color": COLORS["blue_dark"], "lw": 1.2},
    )
    ax.text(center[0] + radius * 0.48, center[1] + 0.025, r"$r=\xi R(t)$", ha="center", fontsize=8)
    ax.text(center[0], center[1] - 0.025, r"$r=0,\ \xi=0$", ha="center", va="top", fontsize=7)
    ax.text(center[0] + radius, center[1] - 0.035, r"$r=R(t),\ \xi=1$", ha="center", va="top", fontsize=7)
    for dy, color, label in ((0.055, COLORS["red"], r"$q_h$"), (-0.055, COLORS["green"], r"$q_m$")):
        ax.annotate(
            "", xy=(center[0] + radius + 0.075, center[1] + dy),
            xytext=(center[0] + radius, center[1] + dy),
            arrowprops={"arrowstyle": "->", "color": color, "lw": 1.2},
        )
        ax.text(center[0] + radius + 0.045, center[1] + dy + 0.018, label, color=color, ha="center")
    ax.text(0.02, 0.90, "(a) 圆柱径向域与表面通量", fontweight="bold")
    ax.text(0.31, 0.95, "(b) 四问继承、退化核验与交付门禁", fontweight="bold")
    fills = ["#E8F1F5", "#E8F1F5", "#EDF3E9", "#F8F0DF", "#F8E9E9", "#F0F0F0", "#E7EDF2"]
    for node, fill in zip(nodes, fills):
        patch = FancyBboxPatch(
            (node["x"], node["y"]), node["w"], node["h"],
            boxstyle="round,pad=0.008,rounding_size=0.015",
            facecolor=fill, edgecolor="#52616B", linewidth=1.1,
        )
        ax.add_patch(patch)
        ax.text(node["x"] + node["w"] / 2, node["y"] + node["h"] / 2, node["label"], ha="center", va="center")
    for source, target, label, style in edges:
        a, b = by_id[source], by_id[target]
        start = (a["x"] + a["w"], a["y"] + a["h"] / 2)
        end = (b["x"], b["y"] + b["h"] / 2)
        connectionstyle = "arc3,rad=0"
        label_xy = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2 + 0.025)
        label_ha = "center"
        if (source, target) == ("input", "q2"):
            start = (a["x"] + a["w"] / 2, a["y"])
            end = (b["x"] + b["w"] / 2, b["y"] + b["h"])
            label_xy = (start[0] - 0.018, (start[1] + end[1]) / 2)
            label_ha = "right"
        elif (source, target) == ("q1", "q2"):
            start = (a["x"] + 0.04, a["y"])
            end = (b["x"] + b["w"], b["y"] + b["h"] * 0.62)
            connectionstyle = "arc3,rad=0.18"
            label_xy = (0.555, 0.625)
        elif source in {"q2", "q3", "q4"} and target == "verify":
            start = (a["x"] + a["w"] / 2, a["y"])
            ports = {"q2": 0.43, "q3": 0.61, "q4": 0.75}
            end = (ports[source], b["y"] + b["h"])
        elif (source, target) == ("q4", "delivery"):
            start = (a["x"] + a["w"] / 2, a["y"])
            end = (b["x"] + b["w"] / 2, b["y"] + b["h"])
            label_xy = (0.94, 0.31)
            label_ha = "right"
        elif (source, target) == ("verify", "delivery"):
            label_xy = ((start[0] + end[0]) / 2, start[1] + 0.025)
        ax.annotate(
            "", xy=end, xytext=start,
            arrowprops={
                "arrowstyle": "->", "color": "#52616B", "lw": 1.0,
                "linestyle": "--" if style == "dashed" else "-",
                "connectionstyle": connectionstyle,
            },
        )
        if label:
            ax.text(
                *label_xy, label, ha=label_ha, va="center", fontsize=7,
                color=COLORS["gray"],
                bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.8, "alpha": 0.88},
            )
    _save(fig, figure_dir / "fig01_model_roadmap.pdf")


def _verified_radius_observations(q4_record: dict) -> np.ndarray:
    root = Path("results/q4")
    manifest = json.loads((root / "radius_input_manifest.json").read_text(encoding="utf-8"))
    identity = q4_record["identity"]["inputs"]["q4_radius"]
    if (manifest.get("schema_version") != 1
            or manifest.get("attachment_sha256") != identity["sha256"]
            or manifest.get("observed_end_s") != identity["observed_end_s"]):
        raise ValueError("Radius observation snapshot differs from the verified Q4 input")
    verify_file("q4/export.py", manifest["generator"])
    verify_file(root / "verification.json", manifest["verification"])
    verify_file(root / "radius_observations.csv", manifest["csv"])
    data = np.genfromtxt(root / "radius_observations.csv", delimiter=",", names=True)
    if len(data) != manifest["rows"] or data["time_s"][-1] != manifest["observed_end_s"]:
        raise ValueError("Incomplete radius observation snapshot")
    return data


def _environment_and_radius(
    source_dir: Path, figure_dir: Path, q4_record: dict, _q4_fields: dict
) -> None:
    environment = np.genfromtxt("results/q2/environment.csv", delimiter=",", names=True)
    radius = _verified_radius_observations(q4_record)
    environment_end_s = float(q4_record["identity"]["inputs"]["environment_extension"]["observed_end_s"])
    radius_end_s = float(q4_record["identity"]["inputs"]["q4_radius"]["observed_end_s"])
    mean_mask = environment["time_s"] >= 10800.0
    mean_T = float(np.mean(environment["temperature_C"][mean_mask]))
    mean_C = float(np.mean(environment["equivalent_moisture"][mean_mask]))
    radius_line_time = np.unique(np.r_[np.arange(0.0, radius_end_s + 1.0, 300.0), radius["time_s"]])
    radius_line = np.interp(radius_line_time, radius["time_s"], radius["radius_cm"])
    rows = []
    for row in environment:
        rows.append({"variable": "environment_temperature_C", "time_h": f"{row['time_s'] / 3600:.17g}", "value": f"{row['temperature_C']:.17g}", "segment": "attachment_observation"})
        rows.append({"variable": "environment_Ce", "time_h": f"{row['time_s'] / 3600:.17g}", "value": f"{row['equivalent_moisture']:.17g}", "segment": "attachment_observation"})
    for time_s, value in ((environment_end_s, mean_T), (radius_end_s, mean_T)):
        rows.append({"variable": "environment_temperature_C", "time_h": f"{time_s / 3600:.17g}", "value": f"{value:.17g}", "segment": "last_hour_mean_extension"})
    for time_s, value in ((environment_end_s, mean_C), (radius_end_s, mean_C)):
        rows.append({"variable": "environment_Ce", "time_h": f"{time_s / 3600:.17g}", "value": f"{value:.17g}", "segment": "last_hour_mean_extension"})
    for time_s, value in zip(radius["time_s"], radius["radius_cm"]):
        rows.append({"variable": "surface_radius_cm", "time_h": f"{time_s / 3600:.17g}", "value": f"{value:.17g}", "segment": "attachment_observation"})
    for time_s, value in zip(radius_line_time, radius_line):
        rows.append({"variable": "surface_radius_cm", "time_h": f"{time_s / 3600:.17g}", "value": f"{value:.17g}", "segment": "linear_interpolation_within_observations"})
    path = source_dir / "fig02_environment_radius.csv"
    _write_rows(path, ["variable", "time_h", "value", "segment"], rows)
    plotted = _read_rows(path)

    def series(variable, segment):
        selected = [row for row in plotted if row["variable"] == variable and row["segment"] == segment]
        return (
            np.asarray([float(row["time_h"]) for row in selected]),
            np.asarray([float(row["value"]) for row in selected]),
        )

    fig, axes = plt.subplots(1, 3, figsize=(10.4, 3.45), layout="constrained")
    for axis, variable, ylabel, color, label in (
        (axes[0], "environment_temperature_C", "环境温度 / °C", COLORS["blue"], r"$T_e$"),
        (axes[1], "environment_Ce", r"等效边界水分 $C_e$ / (kg/kg)", COLORS["green"], r"$C_e$"),
    ):
        obs_h, obs_v = series(variable, "attachment_observation")
        ext_h, ext_v = series(variable, "last_hour_mean_extension")
        axis.plot(obs_h, obs_v, color=color, linewidth=1.2, label=f"附件1 {label}")
        axis.scatter(obs_h[::8], obs_v[::8], s=7, color=color, zorder=3)
        axis.plot(ext_h, ext_v, "--", color=COLORS["gold"], linewidth=1.4, label="末小时均值保持")
        axis.axvline(environment_end_s / 3600.0, color=COLORS["gray"], ls=":", linewidth=0.9)
        axis.set(xlabel="时间 / h", ylabel=ylabel, xlim=(0, 72))
        inset = axis.inset_axes([0.43, 0.42, 0.54, 0.52])
        inset.plot(obs_h, obs_v, color=color, linewidth=1.0)
        inset.scatter(obs_h[::12], obs_v[::12], s=5, color=color)
        inset.set_xlim(0, 4)
        inset.tick_params(labelsize=6)
        inset.set_title("附件1：0–4 h", fontsize=7)
    axes[0].legend(frameon=False, fontsize=7, loc="lower right")
    obs_h, obs_r = series("surface_radius_cm", "attachment_observation")
    line_h, line_r = series("surface_radius_cm", "linear_interpolation_within_observations")
    axes[2].plot(line_h, line_r, color=COLORS["red"], linewidth=1.3, label="观测间线性插值")
    axes[2].scatter(obs_h, obs_r, s=8, facecolor="white", edgecolor=COLORS["red"], linewidth=0.6, label="附件2观测点", zorder=3)
    axes[2].set(xlabel="时间 / h", ylabel="材料表面半径 / cm", xlim=(0, 72))
    axes[2].text(0.98, 0.96, "附件2覆盖 0–72 h\n无外推、无限幅", transform=axes[2].transAxes, ha="right", va="top", fontsize=7, color=COLORS["gray"])
    axes[2].legend(frameon=False, fontsize=7, loc="center right", bbox_to_anchor=(0.98, 0.53))
    for axis, label in zip(axes, ["(a)", "(b)", "(c)"]):
        _panel_label(axis, label)
    _save(fig, figure_dir / "fig02_environment_radius.pdf")


def _q1_q2_early(source_dir: Path, figure_dir: Path) -> None:
    source = _verify_q2_figure_source()
    data = np.genfromtxt(source, delimiter=",", names=True)
    rows = []
    for row in data:
        rows.append({name: f"{float(row[name]):.17g}" for name in data.dtype.names})
    path = source_dir / "fig03_q1_q2_early.csv"
    _write_rows(path, list(data.dtype.names), rows)
    plotted = np.genfromtxt(path, delimiter=",", names=True)
    time_min = plotted["time_s"] / 60.0
    fig, axes = plt.subplots(2, 2, figsize=(8.6, 5.8), sharex=True, layout="constrained")
    series = [
        (axes[0, 0], "q1_center_T", "q2_center_T", "中心温度", "温度 / °C", False),
        (axes[0, 1], "q1_surface_T", "q2_surface_T", "表面温度", "温度 / °C", False),
        (axes[1, 0], "q1_center_C", "q2_center_C", "中心含水率变化", r"$(C-2.55)\times10^5$", True),
        (axes[1, 1], "q1_surface_C", "q2_surface_C", "表面含水率", "干基含水率 / (kg/kg)", False),
    ]
    for axis, q1_name, q2_name, title, ylabel, centered in series:
        q1_values = (plotted[q1_name] - 2.55) * 1e5 if centered else plotted[q1_name]
        q2_values = (plotted[q2_name] - 2.55) * 1e5 if centered else plotted[q2_name]
        axis.plot(time_min, q1_values, "--", color=COLORS["gray"], label="Q1 附录2模型")
        axis.plot(time_min, q2_values, color=COLORS["blue"], label="Q2 附录3变物性")
        axis.set(title=title, ylabel=ylabel)
    axes[1, 0].set_xlabel("时间 / min")
    axes[1, 1].set_xlabel("时间 / min")
    axes[0, 0].legend(frameon=False, fontsize=8)
    for axis, label in zip(axes.ravel(), ["(a)", "(b)", "(c)", "(d)"]):
        _panel_label(axis, label)
    _save(fig, figure_dir / "fig03_q1_q2_early.pdf")


def _physical_radius(
    source_dir: Path,
    figure_dir: Path,
    q3_record: dict,
    q3_fields: dict,
    q4_record: dict,
    q4_fields: dict,
) -> None:
    def archived_profile(question, fields, index):
        if question == "Q3":
            radii = np.arange(21, dtype=float) / 10.0
            values = np.asarray(fields["moisture"][index], dtype=float)
            return radii, values, 2.0
        surface = float(fields["surface_radius_m"][index] * 100.0)
        fixed_r = np.asarray(fields["fixed_radius_m"], dtype=float) * 100.0
        fixed_C = np.asarray(fields["moisture"][index, :21], dtype=float)
        keep = np.isfinite(fixed_C) & (fixed_r < surface - 1e-10)
        radii = np.r_[fixed_r[keep], surface]
        values = np.r_[fixed_C[keep], float(fields["moisture"][index, 21])]
        return radii, values, surface

    field_rows = []
    boundary_rows = []
    radial_grid = np.linspace(0.0, 2.0, 101)
    for question, fields in (("Q3", q3_fields), ("Q4", q4_fields)):
        indices = np.unique(np.r_[np.arange(0, len(fields["time_s"]), 5), len(fields["time_s"]) - 1])
        for index in indices:
            radii, values, surface = archived_profile(question, fields, int(index))
            interpolated = np.full_like(radial_grid, np.nan)
            valid = radial_grid <= surface + 1e-10
            interpolated[valid] = np.interp(radial_grid[valid], radii, values)
            time_h = float(fields["time_s"][index] / 3600.0)
            boundary_rows.append({
                "question": question,
                "time_h": f"{time_h:.17g}",
                "surface_radius_cm": f"{surface:.17g}",
            })
            for radius_cm, value in zip(radial_grid, interpolated):
                field_rows.append({
                    "question": question,
                    "time_h": f"{time_h:.17g}",
                    "radius_cm": f"{radius_cm:.17g}",
                    "C": "" if not np.isfinite(value) else f"{value:.17g}",
                    "surface_radius_cm": f"{surface:.17g}",
                    "value_origin": "linear_radial_interpolation_of_archived_outputs",
                })
    field_path = source_dir / "fig04_moisture_field.csv"
    boundary_path = source_dir / "fig04_surface_boundary.csv"
    _write_rows(
        field_path,
        ["question", "time_h", "radius_cm", "C", "surface_radius_cm", "value_origin"],
        field_rows,
    )
    _write_rows(boundary_path, ["question", "time_h", "surface_radius_cm"], boundary_rows)

    profile_rows = []
    for question, record, fields in (("Q3", q3_record, q3_fields), ("Q4", q4_record, q4_fields)):
        for time_label, target_s in (("24 h", 86400.0), ("event", float(record["root"]["time_s"]))):
            index = int(np.argmin(abs(fields["time_s"] - target_s)))
            if abs(float(fields["time_s"][index]) - target_s) > 1e-8:
                raise ValueError(f"Missing exact {question} profile time {target_s}")
            radii, values, surface = archived_profile(question, fields, index)
            for radius_cm, value in zip(radii, values):
                profile_rows.append({
                    "question": question,
                    "time_label": time_label,
                    "time_h": f"{fields['time_s'][index] / 3600:.17g}",
                    "radius_cm": f"{radius_cm:.17g}",
                    "C": f"{value:.17g}",
                    "point_type": "dynamic_surface" if np.isclose(radius_cm, surface) else "fixed_radius",
                })
    profile_path = source_dir / "fig04_physical_profiles.csv"
    _write_rows(
        profile_path,
        ["question", "time_label", "time_h", "radius_cm", "C", "point_type"],
        profile_rows,
    )

    plotted_field = _read_rows(field_path)
    plotted_boundary = _read_rows(boundary_path)
    plotted_profiles = _read_rows(profile_path)

    def field_matrix(question):
        selected = [row for row in plotted_field if row["question"] == question]
        times = np.asarray(sorted({float(row["time_h"]) for row in selected}))
        radii = np.asarray(sorted({float(row["radius_cm"]) for row in selected}))
        time_index = {value: index for index, value in enumerate(times)}
        radius_index = {value: index for index, value in enumerate(radii)}
        matrix = np.full((len(radii), len(times)), np.nan)
        for row in selected:
            if row["C"]:
                matrix[radius_index[float(row["radius_cm"])], time_index[float(row["time_h"])]] = float(row["C"])
        return times, radii, matrix

    fig, axes = plt.subplots(2, 2, figsize=(10.4, 6.5), layout="constrained")
    meshes = []
    for axis, question, title in zip(axes[0], ["Q3", "Q4"], ["Q3 固定物理域", "Q4 收缩物理域"]):
        times, radii, matrix = field_matrix(question)
        mesh = axis.pcolormesh(times, radii, matrix, shading="auto", cmap="viridis", vmin=0.05, vmax=2.55)
        meshes.append(mesh)
        axis.contour(times, radii, matrix, levels=[0.15], colors="white", linewidths=1.0)
        boundary = [row for row in plotted_boundary if row["question"] == question]
        axis.plot(
            [float(row["time_h"]) for row in boundary],
            [float(row["surface_radius_cm"]) for row in boundary],
            color="#E6C04B", linewidth=1.6, label="物理表面 R(t)", zorder=4,
        )
        axis.set(xlabel="时间 / h", ylabel="物理半径 / cm", title=title)
        axis.set_ylim(0.0, max(2.03, float(np.nanmax(radii)) + 0.03))
        axis.legend(frameon=False, fontsize=7, loc="lower left")
    colorbar = fig.colorbar(meshes[-1], ax=axes[0, :].tolist(), shrink=0.88, pad=0.02)
    colorbar.set_label("干基含水率 / (kg/kg)")

    for axis, time_label, title in zip(
        axes[1], ["24 h", "event"], ["同一 24 h 径向剖面", "各自全域达标时径向剖面"]
    ):
        for question, color in (("Q3", COLORS["blue"]), ("Q4", COLORS["red"])):
            points = sorted(
                [row for row in plotted_profiles if row["question"] == question and row["time_label"] == time_label],
                key=lambda row: float(row["radius_cm"]),
            )
            surface = [row for row in points if row["point_type"] == "dynamic_surface"][-1]
            axis.plot(
                [float(row["radius_cm"]) for row in points],
                [float(row["C"]) for row in points],
                color=color, marker="o", markersize=2.5, label=question,
            )
            axis.scatter(
                float(surface["radius_cm"]), float(surface["C"]), marker="D", s=27,
                color=color, edgecolor="white", linewidth=0.45, zorder=3,
            )
        axis.axhline(0.15, color=COLORS["gray"], ls=":", linewidth=0.9)
        axis.set(xlabel="物理半径 / cm", ylabel="干基含水率 / (kg/kg)", title=title)
    axes[1, 0].legend(frameon=False, fontsize=8)
    for axis, label in zip(axes.ravel(), ["(a)", "(b)", "(c)", "(d)"]):
        _panel_label(axis, label)
    _save(fig, figure_dir / "fig04_physical_radius_drying.pdf")


def _criteria_and_numerics(source_dir: Path, figure_dir: Path, verification: dict, record: dict, fields: dict) -> None:
    rows = [{
        "time_h": f"{summary[0] / 3600:.17g}",
        "surface_C": f"{summary[7]:.17g}",
        "mean_C": f"{summary[6]:.17g}",
        "global_max_C": f"{summary[2]:.17g}",
    } for summary in fields["summary"]]
    criteria_path = source_dir / "fig05_criteria.csv"
    _write_rows(criteria_path, ["time_h", "surface_C", "mean_C", "global_max_C"], rows)

    def sampled_crossing(column):
        times = np.asarray(fields["summary"][:, 0], dtype=float)
        values = np.asarray(fields["summary"][:, column], dtype=float)
        crossed = np.flatnonzero(values <= 0.15)
        if len(crossed) == 0 or crossed[0] == 0:
            raise ValueError("A bracketed drying-criterion crossing is required")
        right = int(crossed[0])
        left = right - 1
        fraction = (values[left] - 0.15) / (values[left] - values[right])
        return float(times[left] + fraction * (times[right] - times[left]))

    crossing_rows = [
        {"criterion": "surface_C", "label": "动态表面", "time_s": f"{sampled_crossing(7):.17g}", "method": "linear_interpolation_between_archived_60s_outputs"},
        {"criterion": "mean_C", "label": "体积平均", "time_s": f"{sampled_crossing(6):.17g}", "method": "linear_interpolation_between_archived_60s_outputs"},
        {"criterion": "global_max_C", "label": "全域最大", "time_s": f"{record['root']['time_s']:.17g}", "method": "full_grid_continuous_event_root"},
    ]
    crossing_path = source_dir / "fig05_crossings.csv"
    _write_rows(crossing_path, ["criterion", "label", "time_s", "method"], crossing_rows)
    numerical = [
        {"layer": "空间", "setting": "N=10240→20480，同BDF设置", "time_scale_s": verification["spatial"][-1]["root_time_difference_s"]},
        {"layer": "时间", "setting": "N=20480，基础→收紧/半步BDF", "time_scale_s": verification["temporal"][0]["root_time_difference_s"]},
        {"layer": "方法", "setting": "N=5120，BDF→Radau", "time_scale_s": verification["method"]["comparison"]["root_time_difference_s"]},
        {"layer": "根定位", "setting": "N=20480正式根括号", "time_scale_s": verification["root_resolution"]["formal_bracket_width_s"]},
    ]
    numerical_path = source_dir / "fig05_numerical_layers.csv"
    _write_rows(
        numerical_path,
        ["layer", "setting", "time_scale_s"],
        [{**item, "time_scale_s": f"{item['time_scale_s']:.17g}"} for item in numerical],
    )
    plotted = _read_rows(criteria_path)
    crossings = _read_rows(crossing_path)
    plotted_numerical = _read_rows(numerical_path)
    time_h = np.asarray([float(row["time_h"]) for row in plotted])
    fig, axes = plt.subplots(1, 2, figsize=(10.0, 3.9), layout="constrained")
    styles = [
        ("surface_C", COLORS["red"], "-", "动态表面"),
        ("mean_C", COLORS["gold"], "--", "体积平均"),
        ("global_max_C", COLORS["blue"], "-", "全域最大"),
    ]
    for name, color, style, label in styles:
        values = np.asarray([float(row[name]) for row in plotted])
        axes[0].plot(time_h, values, style, color=color, label=label, linewidth=1.4)
    axes[0].axhline(0.15, color=COLORS["gray"], ls=":", label="全域判据")
    axes[0].set(xlabel="时间 / h", ylabel="干基含水率 / (kg/kg)")
    axes[0].legend(
        frameon=False, fontsize=7.5, ncols=4, loc="upper center",
        bbox_to_anchor=(0.5, -0.17), borderaxespad=0.0,
    )
    crossing_colors = {"surface_C": COLORS["red"], "mean_C": COLORS["gold"], "global_max_C": COLORS["blue"]}
    for offset, crossing in enumerate(crossings):
        value_h = float(crossing["time_s"]) / 3600.0
        color = crossing_colors[crossing["criterion"]]
        axes[0].axvline(value_h, color=color, ls=":", linewidth=0.8)
        axes[0].annotate(
            f"{crossing['label']} {value_h:.2f} h", xy=(value_h, 0.15),
            xytext=(3 + offset * 13, 12 + offset * 12), textcoords="offset points",
            fontsize=7, color=color, arrowprops={"arrowstyle": "-", "color": color, "lw": 0.7},
        )
    inset = axes[0].inset_axes([0.48, 0.40, 0.49, 0.50])
    for name, color, style, _ in styles:
        inset.plot(time_h, [float(row[name]) for row in plotted], style, color=color, linewidth=1.0)
    inset.axhline(0.15, color=COLORS["gray"], ls=":", linewidth=0.7)
    inset.set_xlim(record["root"]["time_h"] - 2.0, record["root"]["time_h"] + 0.05)
    inset.set_ylim(0.145, 0.17)
    inset.tick_params(labelsize=6)
    inset.set_title("全域判据近根窗口", fontsize=7)

    values = [float(item["time_scale_s"]) for item in plotted_numerical]
    x = np.arange(4)
    axes[1].vlines(x, 1e-7, values, color=[COLORS["blue"], COLORS["gold"], COLORS["red"], COLORS["gray"]], linewidth=1.4)
    axes[1].scatter(x, values, color=[COLORS["blue"], COLORS["gold"], COLORS["red"], COLORS["gray"]], s=32, zorder=3)
    axes[1].set_yscale("log")
    axes[1].set_ylim(5e-7, 3e-1)
    axes[1].set_xticks(x, [item["layer"] for item in plotted_numerical], fontsize=8)
    axes[1].set(ylabel="临界时间数值差异尺度 / s", title="数值层分开报告")
    for index, item in enumerate(plotted_numerical):
        offset = -17 if index == 0 else 8
        axes[1].annotate(
            item["setting"], (index, values[index]), xytext=(0, offset),
            textcoords="offset points", ha="center", fontsize=6.5, rotation=12,
        )
    axes[1].grid(axis="y", which="both", color="#DDDDDD", linewidth=0.5)
    _panel_label(axes[0], "(a)")
    _panel_label(axes[1], "(b)")
    _save(fig, figure_dir / "fig05_criteria_numerical_layers.pdf")


def _mechanism_and_structure(
    source_dir: Path, figure_dir: Path, verification: dict, q4_record: dict, q4_fields: dict
) -> None:
    sensitivity = verified_summary("results/q4/sensitivity")
    case_rows = []
    for item in verification["table6_summary"]:
        case_rows.append({"case": item["case"][0], "time_h": f"{item['time_h']:.17g}", "radius_cm": f"{item['event_radius_cm']:.17g}"})
    case_path = source_dir / "fig06_cases.csv"
    _write_rows(case_path, ["case", "time_h", "radius_cm"], case_rows)

    cmax_rows = []
    for item in verification["table6_summary"]:
        case_name = item["case"]
        record, fields = load_q4_run(Path("results/q4/runs") / case_name)
        indices = np.unique(np.r_[np.arange(0, len(fields["summary"]), 5), len(fields["summary"]) - 1])
        for index in indices:
            cmax_rows.append({
                "case": case_name[0],
                "time_h": f"{fields['summary'][index, 0] / 3600:.17g}",
                "Cmax": f"{fields['summary'][index, 2]:.17g}",
                "event_time_h": f"{record['root']['time_h']:.17g}",
            })
    cmax_path = source_dir / "fig06_case_cmax.csv"
    _write_rows(cmax_path, ["case", "time_h", "Cmax", "event_time_h"], cmax_rows)

    n = q4_record["identity"]["case"]["N"] + 1
    root_C = np.asarray(q4_fields["near_states"][1, n:], dtype=float)
    crossover = 0.15 / np.log(1.0 / 0.175)
    C_grid = np.unique(np.r_[np.geomspace(0.04, 2.55, 360), crossover, root_C[0], root_C[-1]])
    ratio_rows = [
        {"C": f"{value:.17g}", "D4_over_D3": f"{0.175 * np.exp(0.15 / value):.17g}"}
        for value in C_grid
    ]
    ratio_path = source_dir / "fig06_diffusivity_ratio.csv"
    _write_rows(ratio_path, ["C", "D4_over_D3"], ratio_rows)
    marker_rows = [
        {"state": "crossover", "C": f"{crossover:.17g}", "D4_over_D3": "1"},
        {"state": "formal_root_center", "C": f"{root_C[0]:.17g}", "D4_over_D3": f"{0.175 * np.exp(0.15 / root_C[0]):.17g}"},
        {"state": "formal_root_surface", "C": f"{root_C[-1]:.17g}", "D4_over_D3": f"{0.175 * np.exp(0.15 / root_C[-1]):.17g}"},
    ]
    marker_path = source_dir / "fig06_diffusivity_markers.csv"
    _write_rows(marker_path, ["state", "C", "D4_over_D3"], marker_rows)
    sensitivity_rows = [
        {
            "scenario": item["scenario"],
            "event_time_h": f"{item['event_time_h']:.17g}",
            "delta_vs_linear_min": f"{item['event_delta_vs_linear_s'] / 60:.17g}",
        }
        for item in sensitivity["scenarios"]
    ]
    structural_path = source_dir / "fig06_structural_scenarios.csv"
    _write_rows(structural_path, ["scenario", "event_time_h", "delta_vs_linear_min"], sensitivity_rows)

    plotted_cases = _read_rows(case_path)
    plotted_cmax = _read_rows(cmax_path)
    plotted_ratio = _read_rows(ratio_path)
    plotted_markers = _read_rows(marker_path)
    plotted_structural = _read_rows(structural_path)
    fig, axes = plt.subplots(2, 2, figsize=(10.2, 6.4), layout="constrained")
    case_times = [float(row["time_h"]) for row in plotted_cases]
    x = np.arange(4)
    axes[0, 0].plot(x, case_times, color=COLORS["blue_dark"], linewidth=1.0)
    axes[0, 0].scatter(x, case_times, c=["#6B8EAD", COLORS["green"], "#C08A34", COLORS["red"]], s=48, zorder=3)
    for index, value in enumerate(case_times):
        axes[0, 0].annotate(f"{value:.2f} h", (index, value), xytext=(0, 7), textcoords="offset points", ha="center", fontsize=7)
    axes[0, 0].set_xticks(x, ["A\n附3固定", "B\n附3收缩", "C\n附4固定", "D\n附4收缩"])
    axes[0, 0].set(ylabel="全域达标时间 / h", title="物性 × 几何的 A–D 对照")

    case_colors = {"A": "#6B8EAD", "B": COLORS["green"], "C": "#C08A34", "D": COLORS["red"]}
    for case in ["A", "B", "C", "D"]:
        selected = [row for row in plotted_cmax if row["case"] == case]
        axes[0, 1].plot(
            [float(row["time_h"]) for row in selected],
            [float(row["Cmax"]) for row in selected],
            color=case_colors[case], label=case, linewidth=1.2,
        )
        axes[0, 1].scatter(
            float(selected[-1]["time_h"]), float(selected[-1]["Cmax"]),
            color=case_colors[case], s=15, zorder=3,
        )
    axes[0, 1].axhline(0.15, color=COLORS["gray"], ls=":", linewidth=0.9)
    axes[0, 1].set(xlabel="时间 / h", ylabel=r"全域最大含水率 $C_{\max}$", title="A–D 全过程判据轨迹")
    axes[0, 1].legend(frameon=False, ncols=4, fontsize=7)

    ratio_C = np.asarray([float(row["C"]) for row in plotted_ratio])
    ratio_value = np.asarray([float(row["D4_over_D3"]) for row in plotted_ratio])
    axes[1, 0].plot(ratio_C, ratio_value, color=COLORS["blue_dark"], linewidth=1.4)
    axes[1, 0].axhline(1.0, color=COLORS["gray"], ls=":", linewidth=0.9)
    marker_style = {
        "crossover": (COLORS["gold"], "交点"),
        "formal_root_center": (COLORS["blue"], "正式根中心"),
        "formal_root_surface": (COLORS["red"], "正式根表面"),
    }
    for row in plotted_markers:
        color, label = marker_style[row["state"]]
        marker_c = float(row["C"])
        marker_ratio = float(row["D4_over_D3"])
        axes[1, 0].scatter(marker_c, marker_ratio, color=color, s=30, label=label, zorder=3)
        if row["state"] in {"crossover", "formal_root_surface"}:
            axes[1, 0].annotate(
                f"C={marker_c:.4f}\n比值={marker_ratio:.2f}",
                (marker_c, marker_ratio), xytext=(6, 7), textcoords="offset points",
                fontsize=6.5, color=color,
            )
    axes[1, 0].set_xscale("log")
    axes[1, 0].set_yscale("log")
    axes[1, 0].set(xlabel="干基含水率 C / (kg/kg)", ylabel=r"$D_4/D_3$", title="干表层扩散系数比值反转")
    axes[1, 0].legend(frameon=False, fontsize=7)

    scenario_plot = [row for row in plotted_structural if row["scenario"] != "linear"]
    values = [float(row["delta_vs_linear_min"]) for row in scenario_plot]
    labels = ["PCHIP", "半径下移", "半径上移", "末值环境"]
    sx = np.arange(4)
    axes[1, 1].axhline(0, color="#444444", linewidth=0.8)
    axes[1, 1].vlines(sx, 0, values, color=[COLORS["blue"] if value < 0 else COLORS["red"] for value in values], linewidth=1.4)
    axes[1, 1].scatter(sx, values, color=[COLORS["blue"] if value < 0 else COLORS["red"] for value in values], s=36, zorder=3)
    for index, value in enumerate(values):
        axes[1, 1].annotate(f"{value:+.2f}", (index, value), xytext=(0, 7 if value >= 0 else -12), textcoords="offset points", ha="center", fontsize=7)
    axes[1, 1].set_xticks(sx, labels, rotation=12, ha="right")
    axes[1, 1].set(ylabel="相对线性基准 / min", title="确定性结构情景（非置信区间）")
    axes[1, 1].set_ylim(min(values) - 2.0, max(values) + 2.0)
    for axis, label in zip(axes.ravel(), ["(a)", "(b)", "(c)", "(d)"]):
        _panel_label(axis, label)
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
    _environment_and_radius(source_dir, figure_dir, q4_record, q4_fields)
    _q1_q2_early(source_dir, figure_dir)
    _physical_radius(source_dir, figure_dir, q3_record, q3_fields, q4_record, q4_fields)
    _criteria_and_numerics(source_dir, figure_dir, q4_verification, q4_record, q4_fields)
    _mechanism_and_structure(
        source_dir, figure_dir, q4_verification, q4_record, q4_fields
    )

    pdf_paths = sorted(figure_dir.glob("fig*.pdf"))
    if len(pdf_paths) != 6:
        raise RuntimeError(f"Expected six main paper figures, found {len(pdf_paths)}")
    drawio_path = figure_dir / "fig01_model_roadmap.drawio"
    if not drawio_path.exists():
        raise FileNotFoundError(drawio_path)
    write_json("results/paper_figure_manifest.json", {
        "schema_version": 3,
        "font": font,
        "generator": file_record("paper_figures.py"),
        "drawio_source": file_record(drawio_path, TEXT_HASH_SCHEME),
        "evidence": {
            "q2_figure_manifest": file_record("results/q2/figure_manifest.json"),
            "q3_verification": file_record("results/q3/verification.json"),
            "q4_verification": file_record("results/q4/verification.json"),
            "q4_sensitivity": file_record("results/q4/sensitivity/summary.json"),
            "q4_radius_input": file_record("results/q4/radius_input_manifest.json"),
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

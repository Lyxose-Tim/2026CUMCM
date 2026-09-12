"""Generate publication-ready Q2 PDF figures and their bound CSV sources."""
import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from q1.archive import load_archive as load_q1_archive

from .archive import load_archive
from .export import verified_source
from .model import properties


def save_rows(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


def setup():
    plt.rcParams.update({
        "font.family": ["Microsoft YaHei", "SimHei", "Arial"],
        "axes.unicode_minus": False,
        "font.size": 9,
        "axes.grid": True,
        "grid.alpha": 0.22,
        "savefig.bbox": "tight",
    })


def save(fig, path):
    fig.savefig(path, format="pdf")
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default="results/q2")
    parser.add_argument("--figures", default="figures/q2")
    args = parser.parse_args()
    directory, figure_dir = Path(args.directory), Path(args.figures)
    source_dir = directory / "figure_data"
    figure_dir.mkdir(parents=True, exist_ok=True)
    source_dir.mkdir(parents=True, exist_ok=True)
    setup()

    data, _, manifest, _ = verified_source(directory)
    time_h = data["time_s"] / 3600
    radius = np.arange(21) / 10

    indices = [0, 1800, 14400, 86400, 259200]
    labels = ["0 h", "0.5 h", "4 h", "24 h", "72 h"]
    rows = []
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 3.8))
    for index, label in zip(indices, labels):
        axes[0].plot(radius, data["temperature_C"][index], label=label)
        axes[1].plot(radius, data["moisture"][index], label=label)
        rows.extend([
            [int(index), float(r), float(T), float(C)]
            for r, T, C in zip(radius, data["temperature_C"][index], data["moisture"][index])
        ])
    axes[0].set(xlabel="径向位置 / cm", ylabel="温度 / °C", title="径向温度剖面")
    axes[1].set(xlabel="径向位置 / cm", ylabel=r"水分浓度 / kg kg$^{-1}$", title="径向水分剖面")
    axes[1].legend(frameon=False, ncol=2)
    fig.tight_layout()
    save(fig, figure_dir / "q2_radial_profiles.pdf")
    save_rows(source_dir / "q2_radial_profiles.csv", ["time_s", "radius_cm", "temperature_C", "moisture"], rows)

    stride = 60
    selected = slice(None, None, stride)
    rows = zip(
        data["time_s"][selected], data["temperature_C"][selected, 0],
        data["temperature_C"][selected, -1], data["moisture"][selected, 0],
        data["moisture"][selected, -1],
    )
    save_rows(source_dir / "q2_center_surface_72h.csv", [
        "time_s", "center_temperature_C", "surface_temperature_C",
        "center_moisture", "surface_moisture",
    ], rows)
    fig, axes = plt.subplots(2, 1, figsize=(8.8, 6.0), sharex=True)
    axes[0].plot(time_h, data["temperature_C"][:, 0], label="中心")
    axes[0].plot(time_h, data["temperature_C"][:, -1], label="表面")
    axes[0].set(ylabel="温度 / °C", title="中心与表面 72 h 轨迹")
    axes[0].legend(frameon=False)
    axes[1].plot(time_h, data["moisture"][:, 0], label="中心")
    axes[1].plot(time_h, data["moisture"][:, -1], label="表面")
    axes[1].set(xlabel="时间 / h", ylabel=r"水分浓度 / kg kg$^{-1}$")
    fig.tight_layout()
    save(fig, figure_dir / "q2_center_surface_72h.pdf")

    p = manifest["configuration"]["parameters"]
    sample = np.arange(0, len(time_h), 60)
    T = data["temperature_C"][sample][:, [0, -1]]
    C = data["moisture"][sample][:, [0, -1]]
    rho, cp, k, D, _ = properties(T, C, p)
    property_rows = []
    for j, location in enumerate(("center", "surface")):
        property_rows.extend(zip(data["time_s"][sample], [location] * len(sample), rho[:, j], cp[:, j], k[:, j], D[:, j]))
    save_rows(source_dir / "q2_property_evolution.csv", ["time_s", "location", "rho", "cp", "k", "D"], property_rows)
    fig, axes = plt.subplots(2, 2, figsize=(9.8, 6.6), sharex=True)
    for j, label in enumerate(("中心", "表面")):
        axes[0, 0].plot(time_h[sample], rho[:, j], label=label)
        axes[0, 1].plot(time_h[sample], cp[:, j], label=label)
        axes[1, 0].plot(time_h[sample], k[:, j], label=label)
        axes[1, 1].plot(time_h[sample], D[:, j], label=label)
    for ax, ylabel in zip(axes.ravel(), (
        r"$\rho$ / kg m$^{-3}$", r"$c_p$ / J kg$^{-1}$ K$^{-1}$",
        r"$k$ / W m$^{-1}$ K$^{-1}$", r"$D$ / m$^2$ s$^{-1}$",
    )):
        ax.set_ylabel(ylabel)
    axes[0, 0].legend(frameon=False)
    axes[1, 0].set_xlabel("时间 / h")
    axes[1, 1].set_xlabel("时间 / h")
    fig.tight_layout()
    save(fig, figure_dir / "q2_property_evolution.pdf")

    q1, q1_geometry, _ = load_q1_archive("results/q1/archive")
    q1_T = q1["temperature_C"][:, q1_geometry["output_indices"]]
    q1_C = q1["moisture"][:, q1_geometry["output_indices"]]
    delta_T = data["temperature_C"][:1801] - q1_T
    delta_C = data["moisture"][:1801] - q1_C
    comparison_rows = zip(
        data["time_s"][:1801], data["temperature_C"][:1801, 0], q1_T[:, 0],
        data["temperature_C"][:1801, -1], q1_T[:, -1],
        data["moisture"][:1801, 0], q1_C[:, 0], data["moisture"][:1801, -1], q1_C[:, -1],
    )
    save_rows(source_dir / "q1_q2_first_1800s.csv", [
        "time_s", "q2_center_T", "q1_center_T", "q2_surface_T", "q1_surface_T",
        "q2_center_C", "q1_center_C", "q2_surface_C", "q1_surface_C",
    ], comparison_rows)
    fig, axes = plt.subplots(1, 2, figsize=(10.0, 3.8))
    axes[0].plot(data["time_s"][:1801], np.max(np.abs(delta_T), axis=1))
    axes[1].plot(data["time_s"][:1801], np.max(np.abs(delta_C), axis=1))
    axes[0].set(xlabel="时间 / s", ylabel="最大绝对差 / °C", title="Q1/Q2 温度差异")
    axes[1].set(xlabel="时间 / s", ylabel=r"最大绝对差 / kg kg$^{-1}$", title="Q1/Q2 水分差异")
    fig.tight_layout()
    save(fig, figure_dir / "q1_q2_first_1800s.pdf")

    with np.load(directory / "environment_scenarios.npz") as source:
        scenarios = {key: source[key] for key in source.files}
    modes = ["last_hour_mean", *manifest["configuration"]["environment"]["scenario_extensions"]]
    scenario_time = scenarios["time_s"] / 3600
    scenario_rows = []
    fig, axes = plt.subplots(1, 2, figsize=(10.0, 3.8))
    axes[0].plot(time_h[::3600], data["temperature_C"][::3600, 0], label="末小时均值")
    axes[1].plot(time_h[::3600], data["moisture"][::3600, 0], label="末小时均值")
    for mode, label in (("terminal_hold", "末值保持"), ("nominal", "50°C, 0.05")):
        t_values = scenarios[f"{mode}_temperature_C"]
        c_values = scenarios[f"{mode}_moisture"]
        axes[0].plot(scenario_time, t_values[:, 0], label=label)
        axes[1].plot(scenario_time, c_values[:, 0], label=label)
        scenario_rows.extend(zip(scenarios["time_s"], [mode] * len(scenario_time), t_values[:, 0], t_values[:, -1], c_values[:, 0], c_values[:, -1]))
    scenario_rows.extend(zip(data["time_s"][::3600], [modes[0]] * len(data["time_s"][::3600]), data["temperature_C"][::3600, 0], data["temperature_C"][::3600, -1], data["moisture"][::3600, 0], data["moisture"][::3600, -1]))
    save_rows(source_dir / "q2_environment_scenarios.csv", ["time_s", "mode", "center_T", "surface_T", "center_C", "surface_C"], scenario_rows)
    axes[0].set(xlabel="时间 / h", ylabel="中心温度 / °C", title="长期环境假设对温度的影响")
    axes[1].set(xlabel="时间 / h", ylabel=r"中心水分 / kg kg$^{-1}$", title="长期环境假设对水分的影响")
    axes[1].legend(frameon=False)
    fig.tight_layout()
    save(fig, figure_dir / "q2_environment_scenarios.pdf")

    convergence = json.loads((directory / "convergence.json").read_text(encoding="utf-8"))
    records = [item for item in convergence if "difference" in item]
    save_rows(source_dir / "q2_grid_convergence.csv", ["N", "max_abs_T", "max_abs_C", "order_T", "order_C"], [
        [item["N"], item["difference"]["T"]["max_abs"], item["difference"]["C"]["max_abs"], item.get("observed_order", {}).get("T"), item.get("observed_order", {}).get("C")]
        for item in records
    ])
    fig, ax = plt.subplots(figsize=(6.8, 4.0))
    ax.loglog([item["N"] for item in records], [item["difference"]["T"]["max_abs"] for item in records], "o-", label="温度")
    twin = ax.twinx()
    twin.loglog([item["N"] for item in records], [item["difference"]["C"]["max_abs"] for item in records], "s-", color="#C44E52", label="水分")
    ax.set(xlabel="径向区间数 N", ylabel="温度最大差 / °C", title="空间网格收敛")
    twin.set_ylabel(r"水分最大差 / kg kg$^{-1}$")
    fig.tight_layout()
    save(fig, figure_dir / "q2_grid_convergence.pdf")


if __name__ == "__main__":
    main()

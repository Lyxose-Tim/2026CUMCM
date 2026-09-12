"""Paper-ready Q4 figures from verified numeric sources."""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

from q2.archive import write_json
from q2.inputs import sha256
from q2.provenance import portable_artifact_sha256
from q4.validation import verified


def make(directory="results/q4", figure_dir="figures/q4"):
    directory, figure_dir = Path(directory), Path(figure_dir)
    source = directory / "figure_data"
    source.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)
    verification, record, fields = verified(directory)
    available = {font.name for font in font_manager.fontManager.ttflist}
    font = next((name for name in ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC"] if name in available), None)
    if font is None:
        raise RuntimeError("A Chinese font is required")
    plt.rcParams.update({"font.family": font, "font.size": 9, "axes.unicode_minus": False,
                         "pdf.fonttype": 42, "axes.spines.top": False, "axes.spines.right": False})
    trace = np.loadtxt(directory / "runs" / verification["formal_case"] / "accepted_steps.csv", delimiter=",", skiprows=1)
    response = np.vstack([fields["summary"][:1], trace[:, :12], np.asarray(record["root"]["near_summary"])])
    response = response[np.argsort(response[:, 0], kind="stable")]
    np.savetxt(source / "response.csv", response, delimiter=",", fmt="%.17g", comments="",
               header="time_s,radius_m,Cmax,argmax_xi,argmax_radius_m,center_C,mean_C,surface_C,Cmin,Tmin_C,Tmax_C,radial_increase")
    np.savetxt(source / "radius.csv", np.c_[fields["time_s"], fields["surface_radius_m"]],
               delimiter=",", fmt="%.17g", comments="", header="time_s,surface_radius_m")
    times = [21600, 43200, 86400, 129600, record["root"]["time_s"]]
    rows = []
    for t in times:
        idx = int(np.argmin(abs(fields["time_s"] - t)))
        values = fields["moisture"][idx, :21]
        rows.extend(np.c_[np.full(21, fields["time_s"][idx]), fields["fixed_radius_m"] * 100, values].tolist())
    np.savetxt(source / "fixed_radius_profiles.csv", rows, delimiter=",", fmt="%.17g",
               comments="", header="time_s,radius_cm,C")
    summary = []
    import json
    for item in verification["table6_summary"]:
        time_h = item["time_h"] if item["time_h"] is not None else item["horizon_h"]
        radius_cm = item["event_radius_cm"] if item["event_radius_cm"] is not None else np.nan
        surface = item["surface_C_at_event"] if item["surface_C_at_event"] is not None else np.nan
        center = item["center_C_at_event"] if item["center_C_at_event"] is not None else np.nan
        summary.append([time_h, radius_cm, surface, center])
    np.savetxt(source / "case_summary.csv", summary, delimiter=",", fmt="%.17g",
               comments="", header="time_h,event_radius_cm,surface_C,center_C")

    files = []
    def save(fig, name):
        fig.savefig(figure_dir / f"{name}.pdf", bbox_inches="tight")
        plt.close(fig)
        files.append(f"{name}.pdf")

    response = np.loadtxt(source / "response.csv", delimiter=",", skiprows=1)
    radius = np.loadtxt(source / "radius.csv", delimiter=",", skiprows=1)
    profiles = np.loadtxt(source / "fixed_radius_profiles.csv", delimiter=",", skiprows=1)

    fig, ax1 = plt.subplots(figsize=(6.4, 3.3), layout="constrained")
    ax1.plot(response[:, 0] / 3600, response[:, 2], color="#176B8B", label="全域最大值", linewidth=1.7)
    ax1.plot(response[:, 0] / 3600, response[:, 6], "--", color="#B47B23", label="材料平均")
    ax1.plot(response[:, 0] / 3600, response[:, 7], color="#A64949", label="表面")
    ax1.axhline(0.15, color="#555555", ls=":", label="0.15 阈值")
    ax1.set(xlabel="时间 / h", ylabel="干基含水率 / (kg/kg)", xlim=(0, record["root"]["time_h"]))
    ax2 = ax1.twinx()
    ax2.plot(radius[:, 0] / 3600, radius[:, 1] * 100, color="#407F46", alpha=0.8, label="表面半径")
    ax2.set(ylabel="半径 / cm")
    lines = ax1.get_lines() + ax2.get_lines()
    ax1.legend(lines, [line.get_label() for line in lines], frameon=False, fontsize=8)
    save(fig, "q4_moisture_radius")

    fig, ax = plt.subplots(figsize=(6.4, 3.2), layout="constrained")
    colors = plt.colormaps["viridis"](np.linspace(0.05, 0.85, len(times)))
    for t, color in zip(times, colors):
        idx = int(np.argmin(abs(fields["time_s"] - t)))
        subset = profiles[profiles[:, 0] == fields["time_s"][idx]]
        ok = np.isfinite(subset[:, 2])
        label = f"{fields['time_s'][idx] / 3600:.0f} h" if t != record["root"]["time_s"] else f"结束 {record['root']['time_h']:.4f} h"
        ax.plot(subset[ok, 1], subset[ok, 2], color=color, label=label)
    ax.set(xlabel="固定物理半径 / cm", ylabel="干基含水率 / (kg/kg)")
    ax.legend(frameon=False, fontsize=7)
    save(fig, "q4_fixed_radius_profiles")

    fig, ax = plt.subplots(figsize=(5.8, 3.0), layout="constrained")
    labels = ["A: 附录3固定", "B: 附录3收缩", "C: 附录4固定", "D: 附录4收缩", "正式"]
    times_h = [item["time_h"] if item["time_h"] is not None else item["horizon_h"] for item in verification["table6_summary"]]
    ax.bar(np.arange(len(times_h)), times_h, color=["#6B8EAD", "#407F46", "#C08A34", "#A64949", "#183A59"])
    for i, item in enumerate(verification["table6_summary"]):
        if item["status"] != "event":
            ax.text(i, times_h[i], ">72 h", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(np.arange(len(times_h)), labels, rotation=25, ha="right")
    ax.set(ylabel="临界时间 / h")
    save(fig, "q4_case_comparison")

    write_json(directory / "figure_manifest.json", {
        "font": font,
        "source_code_sha256": portable_artifact_sha256("q4/figures.py"),
        "verification_sha256": portable_artifact_sha256(directory / "verification.json"),
        "csv": {p.name: portable_artifact_sha256(p) for p in sorted(source.glob("*.csv"))},
        "pdf": {name: sha256(figure_dir / name) for name in files},
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", default="results/q4")
    parser.add_argument("--figure-dir", default="figures/q4")
    args = parser.parse_args()
    make(args.directory, args.figure_dir)

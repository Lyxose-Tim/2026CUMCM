"""Generate Q1 sensitivity tables, vector plots and report from checked run archives."""
import argparse
import csv
from pathlib import Path

import numpy as np

from .archive import write_json
from .inputs import read_config, sha256
from .sensitivity import load_series
from .sensitivity_metrics import METRICS, UNITS


LABELS = {"h":"h","hm":"hm","D_prefactor":"D前因子"}
METRIC_LABELS = dict(zip(METRICS,("中心升温量","表面升温量","中心含水率","表面含水率","平均失水量")))


def write_csv(path, rows):
    with Path(path).open("w",encoding="utf-8",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with Path(path).open(encoding="utf-8",newline="") as stream:
        return list(csv.DictReader(stream))


def verified_runs(root):
    manifest=read_config(root/"manifest.json")
    if manifest["status"]!="numerically_verified" or sha256(root/"verification.json")!=manifest["verification_sha256"]:
        raise ValueError("Unverified or stale sensitivity results cannot be exported")
    verification=read_config(root/"verification.json")
    if verification["status"]!="numerically_verified":
        raise ValueError("Sensitivity verification did not pass")
    records={}
    for key,expected in manifest["run_records"].items():
        folder=root/"runs"/key
        if sha256(folder/"run.json")!=expected:
            raise ValueError(f"Run record hash mismatch: {key}")
        rec=read_config(folder/"run.json")
        if not rec["passed"] or not all(sha256(folder/f)==h for f,h in rec["files"].items()):
            raise ValueError(f"Invalid run archive: {key}")
        records[key]=rec
    protected=read_config(root/"protected_baseline.json")
    if not all(sha256(p)==h for p,h in protected.items()):
        raise ValueError("Protected baseline artifacts have changed")
    return manifest,verification,records


def draw_figures(source, figure_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    available={f.name for f in font_manager.fontManager.ttflist}
    font=next((f for f in ("Microsoft YaHei","SimHei","Noto Sans CJK SC","WenQuanYi Zen Hei") if f in available),None)
    if font is None:
        raise RuntimeError("A Chinese font is required for paper figures")
    plt.rcParams.update({"font.family":font,"font.size":9,"axes.unicode_minus":False,"pdf.fonttype":42,
                         "axes.spines.top":False,"axes.spines.right":False})
    figure_dir.mkdir(parents=True,exist_ok=True)
    rows=read_csv(source/"response.csv")
    params=("h","hm","D_prefactor")
    deltas=(-.2,-.1,.1,.2)
    colors=("#537EAA","#9CB9D5","#D79A77","#BB513B")
    def save(fig,name):
        fig.savefig(figure_dir/f"{name}.pdf",bbox_inches="tight")
        plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(8.6,5.2),layout="constrained")
    for ax,metric in zip(axes.flat,("center_rise_K","surface_rise_K","surface_moisture","mean_loss")):
        for j,(delta,color) in enumerate(zip(deltas,colors)):
            values=[float(next(r for r in rows if r["parameter"]==p and float(r["relative_change"])==delta)[metric+"_relative_pct"]) for p in params]
            ax.barh(np.arange(3)+(j-1.5)*.18,values,height=.17,color=color,label=f"{delta:+.0%}")
        ax.axvline(0,color="#555555",linewidth=.6)
        ax.set(yticks=range(3),yticklabels=[LABELS[p] for p in params],
               xlabel=METRIC_LABELS[metric]+"相对变化 / %")
        ax.grid(axis="x",alpha=.15)
    axes[0,0].legend(frameon=False,ncol=2,fontsize=7,loc="lower right")
    save(fig,"parameter_response")
    elastic=read_csv(source/"elasticities.csv")
    fig,axes=plt.subplots(1,3,figsize=(9,2.8),layout="constrained")
    for ax,param,metric in zip(axes,params,("center_rise_K","mean_loss","mean_loss")):
        values=[next(r for r in rows if r["parameter"]==param and float(r["relative_change"])==d) for d in deltas]
        x=np.array([-.2,-.1,0,.1,.2])
        y=[float(r[metric+"_relative_pct"]) for r in values]
        y.insert(2,0.)
        S=float(next(r for r in elastic if r["parameter"]==param and r["metric"]==metric and float(r["delta"])==.1)["central"])
        ax.plot(100*x,y,"o-",markersize=4,color="#297AA5",label="实际情景响应")
        ax.plot(100*x,100*S*x,"--",color="#888888",label="±10%中心差分线性近似")
        ax.set(xlabel=LABELS[param]+"相对变化 / %",ylabel=METRIC_LABELS[metric]+"相对变化 / %",xticks=[-20,-10,0,10,20])
        ax.grid(alpha=.15)
    axes[0].legend(frameon=False,fontsize=6.7,loc="upper left")
    save(fig,"finite_perturbation_nonlinearity")
    checks=read_csv(source/"numeric_checks.csv")
    fig,axes=plt.subplots(1,2,figsize=(8.6,3),layout="constrained")
    for ax,field,budget in zip(axes,("T","C"),(8e-4,8e-6)):
        for case in ("h_minus20","h_plus20","hm_minus20","hm_plus20","D_prefactor_minus20","D_prefactor_plus20"):
            subset=[r for r in checks if r["case"]==case and r["kind"]=="space" and r["field"]==field]
            x=[int(r["fine_N"]) for r in subset]
            y=[float(r["max_abs"]) for r in subset]
            ax.loglog(x,y,"o-",markersize=3,label=case.replace("D_prefactor","D前因子").replace("_minus20"," −20%").replace("_plus20"," +20%"))
        ax.axhline(budget,color="#777777",linestyle=":",label="空间预算")
        ax.set(xlabel="细网格区间数 N",ylabel="相邻网格"+("温度差 / °C" if field=="T" else "含水率差 / (kg/kg)"))
    axes[0].legend(frameon=False,fontsize=6.5,ncol=2)
    save(fig,"extreme_scenario_convergence")
    (source/"font.txt").write_text(font+"; embedded TrueType (PDF fonttype 42)\n",encoding="utf-8")
    return font


def generate(root=Path("results/q1_sensitivity"),figure_dir=Path("figures/q1_sensitivity"),report=Path("reports/Q1_SENSITIVITY_REPORT.md")):
    root,figure_dir,report=map(Path,(root,figure_dir,report))
    if figure_dir.resolve().is_relative_to(Path("figures/q1").resolve()):
        raise ValueError("Refuse to overwrite baseline figures")
    manifest,v,records=verified_runs(root)
    source=root/"figure_data"
    source.mkdir(exist_ok=True)
    rows=[]
    for response in v["responses"]:
        rows.append({"case":response["id"],"parameter":response["parameter"] or "baseline",
                     "relative_change":response["relative_change"],**response["endpoint"],
                     **{k+"_difference":d for k,d in response["endpoint_difference"].items()}})
    write_csv(source/"endpoints.csv",rows)
    q0=rows[0]
    response_rows=[]
    for row in rows[1:]:
        response_rows.append({"case":row["case"],"parameter":row["parameter"],"relative_change":row["relative_change"],
                              **{m+"_relative_pct":100*row[m+"_difference"]/q0[m] for m in METRICS}})
    write_csv(source/"response.csv",response_rows)
    elastic_rows=[]
    for e in v["elasticities"]:
        elastic_rows.append({**e,
            "minus_response_resolved":abs(e["minus_value"]-e["baseline"])>2*e["global_resolution"],
            "plus_response_resolved":abs(e["plus_value"]-e["baseline"])>2*e["global_resolution"]})
    write_csv(source/"elasticities.csv",elastic_rows)
    differences=[]
    for r in v["responses"]:
        for field,check in r["field_difference"].items():
            differences.append({"case":r["id"],"field":field,**check})
    write_csv(source/"field_differences.csv",differences)
    checks=[]
    for case,check in v["extreme_checks"].items():
        specs=[("space",n,c) for n,c in zip(manifest["design"]["extreme_grids"][1:],check["space_pairs"])]
        specs += [("time",manifest["design"]["production_N"],check["time"])]
        if "radau" in check:
            specs += [("Radau",manifest["design"]["production_N"],check["radau"])]
        for kind,N,c in specs:
            for field,values in c.items():
                checks.append({"case":case,"kind":kind,"fine_N":N,"field":field,**values})
    write_csv(source/"numeric_checks.csv",checks)
    # Independently recover endpoint functionals from raw arrays, including the
    # full final internal profile for the mean (not the stored mean functional).
    max_readback=0.
    N=manifest["design"]["production_N"]
    p=manifest["configuration"]["parameters"]
    for row in read_csv(source/"endpoints.csv"):
        data=load_series(root/"runs"/f"{row['case']}_N{N}_BDF_base"/"series.npz")
        if data["temperature_C"].shape!=(1801,21) or not np.array_equal(data["time_s"],np.arange(1801.)):
            raise ValueError("Scenario output axes do not match Q1 contract")
        direct=[data["temperature_C"][-1,0]-p["T0"],data["temperature_C"][-1,-1]-p["T0"],
                data["moisture"][-1,0],data["moisture"][-1,-1],
                p["C0"]-np.average(data["final_moisture"],weights=data["volume_m3"])]
        max_readback=max(max_readback,max(abs(float(row[m])-x) for m,x in zip(METRICS,direct)))
    if max_readback>1e-12:
        raise ValueError("CSV endpoints disagree with raw scenario arrays")
    font=draw_figures(source,figure_dir)
    # The report's tables read serialized CSVs, as do the plots above.
    rows=read_csv(source/"endpoints.csv")
    elastic=read_csv(source/"elasticities.csv")
    checks=read_csv(source/"numeric_checks.csv")
    lines=["# 第一问参数灵敏度结果与评测整改","",
           "本报告落实 Issue #3 的固定1800 s灵敏度补充，并与 Issue #4 的[鲁棒性设计](Q1_ROBUSTNESS_DESIGN.md)分开交付。有效传质闭合、无显式潜热和热湿解耦等基准假设保持不变；这些数值实验不构成实物验证。", "",
           f"共13组生产情景（基准及12组单因素扰动）与20次附加复核，总计{manifest['runs']}次积分。生产网格 N={N}，全部比较每秒21个正式半径；六组±20%极端情景使用5120/10240/20480网格复核和更严格BDF设置，另对hm+20%与D前因子−20%采用Radau。所有记录中的数值验收通过。", "",
           "## 1. 固定1800 s响应","",
           "升温量为T−28，单位K；含水率与平均失水量单位均为kg水/kg干药材。平均失水量由完整内部控制体的体积权重计算，不等于真实蒸发质量。表中显示六位不代表实验精度；计算、弹性和图源保留float64。", "",
           "| 情景 | 中心升温 | 表面升温 | 中心C | 表面C | 平均失水 |","| --- | ---: | ---: | ---: | ---: | ---: |"]
    for row in rows:
        name="基准" if row["case"]=="baseline" else f"{LABELS[row['parameter']]} {float(row['relative_change']):+.0%}"
        lines.append("| "+name+" | "+" | ".join(f"{float(row[m]):.6f}" for m in METRICS)+" |")
    lines += ["","## 2. 参数排序与有限扰动非线性","",
              "中心差分弹性Sδ与正/负单边弹性E+、E−的定义见[实施契约](Q1_SENSITIVITY_SPEC.md)。δ表示相对扰动幅度，以下数值是有限扰动的响应比，不是经实验识别的材料常数。", "",
              "| 参数 | 响应量 | S10% | S20% | E−20% | E+20% |","| --- | --- | ---: | ---: | ---: | ---: |"]
    for param,metric in (("h","center_rise_K"),("h","surface_rise_K"),("hm","surface_moisture"),("D_prefactor","surface_moisture"),("hm","mean_loss"),("D_prefactor","mean_loss")):
        pair=[next(r for r in elastic if r["parameter"]==param and r["metric"]==metric and float(r["delta"])==d) for d in (.1,.2)]
        a,b=pair
        lines.append(f"| {LABELS[param]} | {METRIC_LABELS[metric]} | {float(a['central']):.6f} | {float(b['central']):.6f} | {float(b['minus']):.6f} | {float(b['plus']):.6f} |")
    loss_rank=sorted((r for r in elastic if r["metric"]=="mean_loss" and float(r["delta"])==.1),key=lambda r:abs(float(r["central"])),reverse=True)
    center_max=max(abs(r["endpoint_difference"]["center_moisture"]) for r in v["responses"])
    unaffected={f:max(r["field_difference"][f]["max_abs"] for r in v["responses"][1:] if r["unaffected_field"]==f) for f in ("T","C")}
    min_heat_response=min(abs(r["endpoint_difference"][m]) for r in v["responses"][1:] if r["parameter"]=="h"
                          for m in ("center_rise_K","surface_rise_K"))
    min_water_response=min(abs(r["endpoint_difference"][m]) for r in v["responses"][1:] if r["parameter"]!="h"
                           for m in ("surface_moisture","mean_loss"))
    lines += ["",f"按平均失水量的|S10%|排序为 {' > '.join(LABELS[r['parameter']] for r in loss_rank)}。在该解耦模型中，h只作用于热方程；hm与D前因子只作用于水分方程，因此不把温度与失水响应拼成一个综合排名。",
              "",f"非耦合场的全输出最大差分别为温度{unaffected['T']:.3e} °C、含水率{unaffected['C']:.3e} kg/kg，处于数值级。保存实际差值，没有裁剪成零。",
              "",f"用于主要排序的受影响响应中，温度最小变化为{min_heat_response:.6f} K（h扰动的中心/表面升温量），水分最小变化为{min_water_response:.6f} kg/kg（hm或D前因子扰动的表面C/平均失水量），分别为两解数值目标合计的{min_heat_response/.002:.1f}倍与{min_water_response/2e-5:.1f}倍。这是按既定预算作的分辨率筛选，不是严格误差界或实验显著性检验。",
              "",f"中心含水率变化的最大幅度为{center_max:.3e} kg/kg。均匀初值和短预热时段下，中心传质响应远弱于表面；正负两侧分别给出可分辨性标记（elasticities.csv的minus/plus_response_resolved）。当差值低于保守的两解全局预算（2×10⁻⁵ kg/kg），不将其解释为已解析的物理效应。D前因子+20%的中心差超过此筛选尺度，−20%一侧则未超过；不能把同一弹性行的两侧都笼统称作可分辨。",
              "","hm增大加强表面移除，D前因子增大加强内部向表面的补给；二者均可能增加整体失水，却对表面C产生相反方向的响应。单边弹性的不同说明±20%不是对称线性效果；两个幅度的中心差分接近也不等于响应严格线性。",
              "","## 3. 数值检查与分辨率","",
              "空间预算为8×10⁻⁴ °C与8×10⁻⁶ kg/kg，时间预算为2×10⁻⁴ °C与2×10⁻⁶ kg/kg。下表取六组极端情景的最大值。", "",
              "| 复核 | 温度最大差 / °C | 含水率最大差 / (kg/kg) |","| --- | ---: | ---: |"]
    for label,kind,n in (("5120→10240","space",10240),("10240→20480","space",20480),("收紧BDF","time",20480),("Radau对照","Radau",20480)):
        vals=[max(float(r["max_abs"]) for r in checks if r["kind"]==kind and int(r["fine_N"])==n and r["field"]==f) for f in ("T","C")]
        lines.append(f"| {label} | {vals[0]:.6e} | {vals[1]:.6e} |")
    bal={f:max(r["balance"][f]["max_balance"] for r in records.values()) for f in ("T","C")}
    quad={f:max(r["balance"][f]["max_quadrature_difference"] for r in records.values()) for f in ("T","C")}
    trials=sum(len(r["diagnostics"]["trial_failures"]) for r in records.values())
    lines += ["",f"33次运行的归一化余额最大值：热{bal['T']:.3e}、水分{bal['C']:.3e}；独立求积复核差：热{quad['T']:.3e}、水分{quad['C']:.3e}。所有接受步及每秒输出均通过正性和历史包络检查，各运行表面梯度残差通过早期1%/后期0.1%的既定门槛。",
              "",f"共记录{trials}次非正C试探失败，逐次时间、节点、数值和阶段在run.json中；积分从该段原始初值缩小步长重试，没有更改D(C)，没有非正接受状态。该记录不能被描述为接受解被裁剪或修改物性。",
              "",f"原参数新运行与已发布全精度归档的全输出最大差为温度{v['baseline_reproduction']['T']['max_abs']:.3e} °C、水分{v['baseline_reproduction']['C']['max_abs']:.3e} kg/kg，均在时间预算内。原输入和原结果、Excel、图PDF的逐文件哈希未变。",
              "","空间差连续两次下降且进入预算，实际阶见verification.json；这些检查不是严格误差上界。±10%情景在受检极端范围内部，但没有逐一增加三网格/时间对照；不能把端点复核推广成参数连续域的数学误差保证。两组Radau复核只核验时间推进，不替代空间基准。",
              "","本轮修正两处扩展验证问题：包络使用历史环境极值，允许合法的降温滞后；表面水分梯度核验使用该情景实际D前因子和指数。它们没有改变正式基准PDE或题给物性。","",
              "## 4. 图、数据和证据范围","",
              "- [参数响应图](../figures/q1_sensitivity/parameter_response.pdf)：四个主要输出的相对变化，温度使用升温量。",
              "- [有限扰动非线性图](../figures/q1_sensitivity/finite_perturbation_nonlinearity.pdf)：实际曲线与±10%中心差分线性近似。",
              "- [极端情景收敛图](../figures/q1_sensitivity/extreme_scenario_convergence.pdf)：最大相邻网格差与空间预算。",
              "- [全精度情景及验证清单](../results/q1_sensitivity/manifest.json)、[图源CSV](../results/q1_sensitivity/figure_data/)、[复现入口](../REPRODUCE.md)。",
              "","图、表从相同已核验的场归档生成。±10%和±20%属于有界单因素设定，未使用参数误差分布；因此本报告不提供置信区间、不宣称联合扰动鲁棒性或实物准确率。没有因灵敏度较大而调整题给参数。闭合、潜热和实物数据缺口见[鲁棒性设计](Q1_ROBUSTNESS_DESIGN.md)。",
              "","本轮数值补充与设计交付完成后仍需小组交叉审核。第二至第四问、联合/环境扰动实验和整篇论文不在本次交付中。",""]
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text("\n".join(lines),encoding="utf-8")
    artifacts=list(source.glob("*"))+list(figure_dir.glob("*.pdf"))+[report]
    write_json(root/"export_verification.json",{"passed":True,"max_endpoint_readback_difference":max_readback,
                "verified_raw_run_records":len(records),"font":font,"csv_and_figures_same_source":True,
                "artifact_sha256":{p.as_posix():sha256(p) for p in artifacts},
                "generator_sha256":sha256(Path(__file__)),"verification_sha256":sha256(root/"verification.json")})
    print(f"Generated checked sensitivity report and figures; endpoint readback {max_readback:.3e}")


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory",default="results/q1_sensitivity")
    parser.add_argument("--figure-dir",default="figures/q1_sensitivity")
    parser.add_argument("--report",default="reports/Q1_SENSITIVITY_REPORT.md")
    a=parser.parse_args()
    generate(a.directory,a.figure_dir,a.report)

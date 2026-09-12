"""Four paper-ready vector figures read their independently saved CSV sources."""
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
from q3.validation import verified


def make(directory="results/q3",figure_dir="figures/q3"):
    directory,figure_dir=Path(directory),Path(figure_dir)
    source=directory/"figure_data"
    source.mkdir(exist_ok=True)
    figure_dir.mkdir(parents=True,exist_ok=True)
    v,r,f=verified(directory)
    available={font.name for font in font_manager.fontManager.ttflist}
    font=next((x for x in ["Microsoft YaHei","SimHei","Noto Sans CJK SC"] if x in available),None)
    if font is None:
        raise RuntimeError("A Chinese font is required")
    plt.rcParams.update({"font.family":font,"font.size":9,"axes.unicode_minus":False,
                         "pdf.fonttype":42,"axes.spines.top":False,"axes.spines.right":False})
    trace=np.loadtxt(directory/"runs"/v["formal_case"]/"accepted_steps.csv",delimiter=",",skiprows=1)
    # Include the initial state and precise event plus post-event evidence.
    response=np.vstack([f["summary"][:1],trace[:,:10],np.asarray(r["root"]["near_summary"])])
    response=response[np.argsort(response[:,0],kind="stable")]
    np.savetxt(source/"response.csv",response,delimiter=",",fmt="%.17g",comments="",
               header="time_s,Cmax,argmax_radius_m,center_C,mean_C,surface_C,Cmin,Tmin_C,Tmax_C,radial_increase")
    times=[21600,43200,86400,129600,172800,r["root"]["time_s"]]
    rows=[]
    for t in times:
        idx=int(np.argmin(abs(f["time_s"]-t)))
        rows.extend(np.c_[np.full(21,t),np.arange(21)/10,f["moisture"][idx]].tolist())
    np.savetxt(source/"profiles.csv",rows,delimiter=",",fmt="%.17g",comments="",header="time_s,radius_cm,C")
    n=len(f["radius_m"])
    np.savetxt(source/"endpoint_profile.csv",np.c_[f["radius_m"]*100,f["near_states"][1,n:]],
               delimiter=",",fmt="%.17g",comments="",header="radius_cm,C")
    conv=[]
    import json
    for N in [5120,10240,20480,40960]:
        run=json.loads((directory/"runs"/f"base_N{N}"/"run.json").read_text(encoding="utf-8"))
        conv.append([N,run["root"]["time_s"],run["diagnostics"]["max_surface_gradient_relative_residual"]])
    np.savetxt(source/"convergence.csv",conv,delimiter=",",fmt="%.17g",comments="",header="N,time_s,max_surface_gradient_relative_residual")
    # All plotting below rereads the serialized sources.
    response=np.loadtxt(source/"response.csv",delimiter=",",skiprows=1)
    profiles=np.loadtxt(source/"profiles.csv",delimiter=",",skiprows=1)
    endpoint=np.loadtxt(source/"endpoint_profile.csv",delimiter=",",skiprows=1)
    conv=np.loadtxt(source/"convergence.csv",delimiter=",",skiprows=1)
    end=r["root"]["time_s"]
    files=[]
    def save(fig,name):
        fig.savefig(figure_dir/f"{name}.pdf",bbox_inches="tight")
        plt.close(fig)
        files.append(f"{name}.pdf")
    fig,ax=plt.subplots(figsize=(6.4,3.4),layout="constrained")
    ax.plot(response[:,0]/3600,response[:,1],color="#176B8B",label="全域最大值",linewidth=1.7)
    stride=max(1,len(response)//30)
    ax.plot(response[::stride,0]/3600,response[::stride,3],"o",mfc="none",mec="#183A59",ms=4,label="中心（抽样标记）")
    ax.plot(response[:,0]/3600,response[:,4],"--",color="#B47B23",label="体积平均")
    ax.plot(response[:,0]/3600,response[:,5],color="#A64949",label="表面")
    ax.axhline(.15,color="#555555",ls=":",label="0.15 阈值")
    ax.axvline(end/3600,color="#777777",ls=":",lw=.8)
    ax.set(xlabel="时间 / h",ylabel="干基含水率 / (kg/kg)",xlim=(0,end/3600),ylim=(0,2.65))
    ax.legend(frameon=False,fontsize=8)
    save(fig,"q3_moisture_curves")
    fig,axes=plt.subplots(1,2,figsize=(7.3,3),layout="constrained")
    near=response[abs(response[:,0]-end)<900]
    axes[0].plot((near[:,0]-end)/3600,near[:,1],".-",color="#176B8B",ms=3)
    axes[0].axhline(.15,color="#555555",ls=":")
    axes[0].axvline(0,color="#777777",ls=":",lw=.8)
    axes[0].set(xlabel="距临界时刻 / h",ylabel="全域最大含水率 / (kg/kg)")
    close=np.asarray(r["root"]["near_summary"])
    axes[1].plot(close[:,0]-end,(close[:,1]-.15)*1e7,"o-",color="#176B8B",ms=4)
    error=v["estimated_numerical_time_change_s"]*abs(v["slope_C_per_s"])*1e7
    axes[1].axhspan(-error,error,color="#888888",alpha=.16,label="估计数值误差量级")
    axes[1].axhline(0,color="#555555",ls=":")
    axes[1].set(xlabel="距临界时刻 / s",ylabel="(全域最大值 − 0.15) × 10⁷",xlim=(-1.1,1.1))
    axes[1].legend(frameon=False,fontsize=7,loc="upper right")
    save(fig,"q3_threshold_zoom")
    fig,axes=plt.subplots(1,2,figsize=(7.3,3),layout="constrained")
    colors=plt.colormaps["viridis"](np.linspace(.05,.85,len(times)))
    for t,color in zip(times,colors):
        subset=profiles[profiles[:,0]==t]
        label=f"{t/3600:.0f} h" if t!=end else f"结束 {end/3600:.4f} h"
        axes[0].plot(subset[:,1],subset[:,2],color=color,label=label)
    axes[0].set(xlabel="半径 / cm",ylabel="干基含水率 / (kg/kg)",xlim=(0,2))
    axes[0].legend(frameon=False,fontsize=7)
    subset=endpoint[endpoint[:,0]>=1.98]
    axes[1].plot(subset[:,0],subset[:,1],color="#176B8B")
    axes[1].set(xlabel="表层半径 / cm",ylabel="结束时含水率 / (kg/kg)",xlim=(1.98,2))
    save(fig,"q3_radial_profiles")
    fig,axes=plt.subplots(1,2,figsize=(7.3,3),layout="constrained")
    difference=conv[:-1,1]-conv[1:,1]
    axes[0].loglog(conv[1:,0],abs(difference),"o-",color="#176B8B",label="相邻网格时间差")
    axes[0].loglog(conv[1:,0],abs(difference[0])*(conv[1,0]/conv[1:,0])**2,"--",color="#A64949",label="二阶参考")
    axes[0].set(xlabel="细网格区间数 N",ylabel="临界时间差 / s")
    axes[0].legend(frameon=False,fontsize=8)
    axes[1].plot(1e8/conv[:,0]**2,conv[:,1]-end,"o-",color="#176B8B")
    axes[1].set(xlabel="10⁸ / N²",ylabel="基准时间 − 正式时间 / s")
    save(fig,"q3_convergence")
    write_json(directory/"figure_manifest.json",{
        "font":font,"source_code_sha256":portable_artifact_sha256("q3/figures.py"),
        "verification_sha256":portable_artifact_sha256(directory/"verification.json"),
        "csv":{p.name:portable_artifact_sha256(p) for p in sorted(source.glob("*.csv"))},
        "pdf":{name:sha256(figure_dir/name) for name in files}})


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--directory",default="results/q3")
    p.add_argument("--figure-dir",default="figures/q3")
    args=p.parse_args()
    make(args.directory,args.figure_dir)

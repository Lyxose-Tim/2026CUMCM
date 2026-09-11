"""Vector figures read their saved CSV sources; all values originate in one archive."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

from .export import verified_source,TABLE_TIMES


def make_figures(directory="results/q1",figure_dir="figures/q1"):
    directory,figure_dir = Path(directory),Path(figure_dir)
    source = directory/"figure_data"
    source.mkdir(parents=True,exist_ok=True)
    figure_dir.mkdir(parents=True,exist_ok=True)
    data,g,m,v = verified_source(directory)
    available = {f.name for f in font_manager.fontManager.ttflist}
    font = next((f for f in ["Microsoft YaHei","SimHei","Noto Sans CJK SC","WenQuanYi Zen Hei"] if f in available),None)
    if font is None:
        raise RuntimeError("Install/configure a Chinese font before producing paper figures")
    plt.rcParams.update({"font.family":font,"font.size":9,"axes.unicode_minus":False,"pdf.fonttype":42,"ps.fonttype":42,"axes.spines.top":False,"axes.spines.right":False,"lines.linewidth":1.5})
    environment = np.loadtxt(directory/"environment.csv",delimiter=",",skiprows=1)
    np.savetxt(source/"environment.csv",environment,delimiter=",",header="time_s,temperature_C,equivalent_moisture",comments="")
    response = np.c_[data["time_s"],data["temperature_C"][:,0],data["temperature_C"][:,-1],data["temperature_C"]@g["volume_m3"]/g["volume_m3"].sum(),data["moisture"][:,0],data["moisture"][:,-1],data["moisture"]@g["volume_m3"]/g["volume_m3"].sum()]
    np.savetxt(source/"response.csv",response,delimiter=",",header="time_s,center_temperature_C,surface_temperature_C,mean_temperature_C,center_moisture,surface_moisture,mean_moisture",comments="")
    profiles = np.c_[np.repeat(TABLE_TIMES,len(g["radius_m"])),np.tile(g["radius_m"]*100,len(TABLE_TIMES)),data["temperature_C"][TABLE_TIMES].ravel(),data["moisture"][TABLE_TIMES].ravel()]
    np.savetxt(source/"profiles.csv",profiles,delimiter=",",header="time_s,radius_cm,temperature_C,moisture",comments="")
    history = json.loads((directory/"convergence.json").read_text(encoding="utf-8"))
    conv = np.array([[r["N"],r["difference"]["T"]["max_abs"],r["difference"]["C"]["max_abs"],r["difference"]["T"]["early_surface_max"],r["difference"]["C"]["early_surface_max"]] for r in history if "difference" in r])
    np.savetxt(source/"convergence.csv",conv,delimiter=",",header="N,max_temperature_difference,max_moisture_difference,early_surface_temperature_difference,early_surface_moisture_difference",comments="")
    # Rendering uses the serialized sources, which the independent export audit rereads.
    env = np.loadtxt(source/"environment.csv",delimiter=",",skiprows=1)
    response = np.loadtxt(source/"response.csv",delimiter=",",skiprows=1)
    profiles = np.loadtxt(source/"profiles.csv",delimiter=",",skiprows=1)
    conv = np.loadtxt(source/"convergence.csv",delimiter=",",skiprows=1)
    def save(fig,name):
        fig.savefig(figure_dir/f"{name}.pdf",bbox_inches="tight")
        plt.close(fig)
    fig,ax = plt.subplots(1,2,figsize=(8,2.7),layout="constrained")
    for i,label in enumerate(["环境温度 / °C","等效环境含水率 / (kg/kg)"]):
        ax[i].plot(env[:,0],env[:,i+1],color=["#BB513B","#297AA5"][i])
        ax[i].scatter(env[:,0],env[:,i+1],s=7,color=["#BB513B","#297AA5"][i],zorder=3)
        ax[i].set(xlabel="时间 / s",ylabel=label,xlim=(0,1800))
    save(fig,"environment")
    fig,ax = plt.subplots(1,2,figsize=(8,3.1),layout="constrained")
    colors = plt.colormaps["viridis"](np.linspace(.05,.9,len(TABLE_TIMES)))
    for t,color in zip(TABLE_TIMES,colors):
        subset = profiles[profiles[:,0]==t]
        for i in range(2):
            ax[i].plot(subset[:,1],subset[:,i+2],color=color,label=f"{t} s")
    ax[0].set(xlabel="距轴线的径向距离 / cm",ylabel="温度 / °C",xlim=(0,2))
    ax[1].set(xlabel="距轴线的径向距离 / cm",ylabel="干基含水率 / (kg/kg)",xlim=(0,2))
    ax[0].legend(frameon=False,ncol=2,fontsize=7,loc="upper left")
    save(fig,"radial_profiles")
    fig,ax = plt.subplots(1,2,figsize=(8,2.9),layout="constrained")
    for i in range(2):
        for j,(label,color,style) in enumerate([("中心","#365F91","-"),("表面","#BB513B","-"),("体积平均","#518561","--")]):
            ax[i].plot(response[:,0],response[:,1+3*i+j],label=label,color=color,linestyle=style)
        ax[i].set(xlabel="时间 / s",ylabel=["温度 / °C","干基含水率 / (kg/kg)"][i],xlim=(0,1800))
        ax[i].legend(frameon=False,fontsize=8)
    save(fig,"center_surface_response")
    fig,ax = plt.subplots(1,2,figsize=(8,2.9),layout="constrained")
    for i,name in enumerate(["T","C"]):
        ax[i].loglog(conv[:,0],conv[:,i+1],"o-",markersize=3,color=["#BB513B","#297AA5"][i],label="全输出最大差")
        ax[i].loglog(conv[:,0],conv[:,i+3],"--",color="#777777",label="前60 s表面最大差")
        ax[i].axhline(m["configuration"]["budgets"][f"space_{name}"],color="#518561",linestyle=":",label="空间预算")
        ax[i].set(xlabel="细网格区间数 N",ylabel=["相邻网格温度差 / °C","相邻网格含水率差 / (kg/kg)"][i])
        ax[i].legend(frameon=False,fontsize=7)
    save(fig,"convergence")
    (source/"font.txt").write_text(font+"; embedded TrueType (PDF fonttype 42)\n",encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory",default="results/q1")
    parser.add_argument("--figure-dir",default="figures/q1")
    args = parser.parse_args()
    make_figures(args.directory,args.figure_dir)

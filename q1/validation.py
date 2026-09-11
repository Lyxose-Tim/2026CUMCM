"""Checks with explicitly scaled errors, independent references and locations."""
import numpy as np

from .fvm import Grid, RadialModel, diffusivity, harmonic
from .reference import bessel_series
from .solver import integrate


def difference(coarse, fine, times):
    records = {}
    for name, u, v in zip(["T","C"],coarse,fine):
        err = abs(u-v)
        location = np.unravel_index(err.argmax(),err.shape)
        early = (times>=1) & (times<=60)
        records[name] = {"max_abs":float(err[location]),"time_s":float(times[location[0]]),"radius_cm":location[1]/10,"early_surface_max":float(err[early,-1].max())}
    return records


def boundary_check(sol, grid, p, env):
    Te,Ce = env(sol.times)
    records = {}
    for name,u,a,beta,exterior,scale in [
        ("T",sol.temperature_C,p["k"],p["h"],Te,p["h"]*13.513),
        ("C",sol.moisture,diffusivity(sol.moisture[:,-1],p["D_prefactor"],p["D_exponent"])[0],p["hm"],Ce,p["hm"]*(2.55-0.01963))]:
        gradient = (3*u[:,-1]-4*u[:,-2]+u[:,-3])/(2*grid.dr)
        residual = abs(-a*gradient-beta*(u[:,-1]-exterior))/scale
        early = (sol.times>=1)&(sol.times<=60)
        late = (sol.times>=100)&(sol.times<=1800)
        e,l = float(residual[early].max()),float(residual[late].max())
        records[name] = {"early":e,"late":l,"passed":e<=0.01 and l<=0.001}
    return records


def balance_check(sol,grid,p):
    volume = grid.volume.sum()
    changes = np.c_[p["rho"]*p["cp"]*((sol.temperature_C-p["T0"])@grid.volume),(sol.moisture-p["C0"])@grid.volume]
    scale = np.array([p["rho"]*p["cp"]*volume*13.513,p["C0"]*volume])
    residual = abs(changes+grid.area[-1]*sol.boundary_integrals)/scale
    qdiff = grid.area[-1]*sol.integration_check/scale
    report = {name:{"max_balance":float(residual[:,i].max()),"max_quadrature_difference":float(qdiff[:,i].max()),"passed":bool(residual[:,i].max()<=1e-8 and qdiff[:,i].max()<=1e-10)} for i,name in enumerate(["T","C"])}
    return report,np.c_[sol.times,residual,qdiff]


def analytic_check(grid,p,settings):
    D0 = float(diffusivity(np.array([p["C0"]]),p["D_prefactor"],p["D_exponent"])[0][0])
    times = np.array([1.,2,5,10,30,60,100,300,600,1800])
    model = RadialModel(grid,p,lambda t:(38.,0.02),constant_D=D0)
    sol = integrate(model,settings,breaks=[0,1800],output_times=times)
    result, reference = {},[]
    for name,u,ue,u0,a,b,beta,budget in [
        ("T",sol.output(grid)[0],38.,28.,p["k"],p["rho"]*p["cp"],p["h"],8e-4),
        ("C",sol.output(grid)[1],0.02,2.55,D0,1,p["hm"],8e-6)]:
        v,info = bessel_series(np.linspace(0,1,21),times,a/(b*grid.R**2),beta*grid.R/a)
        exact = ue+(u0-ue)*v
        err = abs(u-exact)
        loc = np.unravel_index(err.argmax(),err.shape)
        result[name] = {**info,"max_abs":float(err.max()),"time_s":float(times[loc[0]]),"radius_cm":loc[1]/10,"budget":budget,"passed":bool(err.max()<=budget)}
        reference.append(np.c_[np.repeat(times,21),np.tile(np.linspace(0,2,21),len(times)),u.ravel(),exact.ravel(),err.ravel()])
    return result,reference


def spatial_metrics():
    records = []
    for N in [40,80,160]:
        g = Grid(N)
        C = 1+(g.r/g.R)**2
        D,Dp = diffusivity(C)
        H,_,_ = harmonic(D,Dp)
        exact = 4*D/g.R**2+4*g.r**2*Dp/g.R**4
        err = abs(g.divergence(g.flux(C,H,boundary_flux=-2*D[-1]/g.R))-exact)/(7e-9/g.R**2)
        records.append({"N":N,"internal":float(err[:-1].max()),"surface":float(err[-1]),"weighted":float(err@g.volume/g.volume.sum())})
    return records

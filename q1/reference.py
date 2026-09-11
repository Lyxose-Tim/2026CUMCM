"""Independent full Bessel expansion for a constant-coefficient Robin cylinder."""
import numpy as np
from scipy.optimize import brentq
from scipy.special import j0, j1, jn_zeros


def bessel_series(r_over_R, times, a_over_b_R2, Bi, tolerance=1e-10):
    if Bi <= 0 or min(times) <= 0:
        raise ValueError("Expansion benchmark requires Bi > 0 and t > 0")
    previous = None
    for count in [32,64,128,256,512,1024,2048,4096,8192]:
        zeros = np.r_[0., jn_zeros(0,count)]
        roots = np.array([brentq(lambda mu: mu*j1(mu)-Bi*j0(mu),lo,hi,xtol=1e-13) for lo,hi in zip(zeros[:-1],zeros[1:])])
        A = 2*j1(roots)/(roots*(j0(roots)**2+j1(roots)**2))
        result = (np.exp(-np.outer(times,roots**2)*a_over_b_R2)*A) @ j0(np.outer(roots,r_over_R))
        if previous is not None:
            difference = float(np.max(abs(result-previous)))
            if difference < tolerance:
                return result,{"modes":count,"truncation_difference":difference,"first_roots":roots[:3].tolist(),"first_coefficients":A[:3].tolist()}
        previous = result
    raise RuntimeError("Bessel truncation failed to converge")

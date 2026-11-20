from collections.abc import Callable
import numpy as np
from rocketcea.cea_obj_w_units import CEA_Obj
from scipy.integrate import cumulative_trapezoid
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq


def _cea_object(inputs: dict) -> CEA_Obj:
    return CEA_Obj(
        oxName=inputs["oxidizer"],
        fuelName=inputs["fuel"],
        pressure_units="Pa",
        sonic_velocity_units="m/s",
        density_units="kg/m^3",
        temperature_units="K",
    )


def eps_from_mach(inputs: dict, mach: float) -> float:
    """Solve CEA area ratio eps for a given supersonic Mach number."""
    c = _cea_object(inputs)
    mach = max(mach, 1 + 1e-6)

    def residual(eps):
        return mach - c.get_MachNumber(Pc=inputs["Pc"], MR=inputs["MR"], eps=eps)

    upper = max(1000.0, float(inputs.get("eps") or 1000.0) * 1.1)
    return brentq(residual, 1, upper)


def entry_conditions(inputs: dict) -> float:
    return max(_cea_object(inputs).get_MachNumber(
        Pc=inputs["Pc"], MR=inputs["MR"], eps=inputs["effective_throat_eps"]
    ), 1 + 1e-6)


def exit_mach(inputs: dict) -> float:
    c = _cea_object(inputs)
    return max(c.get_MachNumber(Pc=inputs["Pc"], MR=inputs["MR"], eps=inputs["eps"]), 1 + 1e-6)


def gamma_from_eps(inputs: dict, eps: float) -> float:
    return _cea_object(inputs).get_exit_MolWt_gamma(Pc=inputs["Pc"], MR=inputs["MR"], eps=eps)[1]


def prandtl_meyer_from_mach(inputs: dict) -> Callable[[float], float]:
    """Build exact real-gas Prandtl-Meyer interpolator nu(M) = integral(sqrt(M^2 - 1) dV / V)."""
    c = _cea_object(inputs)
    eps_max = max(150.0, float(inputs.get("eps") or 150.0) * 1.1)
    eps_range = 1.0 + np.geomspace(1e-4, eps_max - 1.0, num=80)

    mach_list = [1.0]
    vel_list = [c.get_SonicVelocities(Pc=inputs["Pc"], MR=inputs["MR"], eps=eps_max)[1]]
    for eps in eps_range:
        m = c.get_MachNumber(Pc=inputs["Pc"], MR=inputs["MR"], eps=eps)
        v = c.get_SonicVelocities(Pc=inputs["Pc"], MR=inputs["MR"], eps=eps)[2] * m
        if m > mach_list[-1] and v > vel_list[-1]:
            mach_list.append(m)
            vel_list.append(v)

    m_arr = np.asarray(mach_list, dtype=float)
    v_arr = np.asarray(vel_list, dtype=float)
    integrand = np.sqrt(np.maximum(0.0, m_arr**2 - 1.0)) / v_arr
    nu_arr = np.concatenate(([0.0], cumulative_trapezoid(integrand, v_arr)))
    interp = PchipInterpolator(m_arr, nu_arr)
    return lambda mach: 0.0 if mach <= 1.0 else float(interp(mach))


def sonic_throat_state(inputs: dict) -> tuple[float, float, float, float, float, float, float]:
    """Return (v_t, rho_t, mu_t, Pr, gamma, T0, T_t) at the sonic throat (M = 1)."""
    c = _cea_object(inputs)
    pc, mr = inputs["Pc"], inputs["MR"]
    eps_ref = float(inputs.get("eps") or 40.0)
    v_t = float(c.get_SonicVelocities(Pc=pc, MR=mr, eps=eps_ref)[1])
    rho_t = float(c.get_Densities(Pc=pc, MR=mr, eps=eps_ref)[1])
    _, visc_mp, _, pr = c.get_Throat_Transport(Pc=pc, MR=mr)
    mu_t = float(visc_mp) * 1.0e-4
    _, gamma = c.get_Throat_MolWt_gamma(Pc=pc, MR=mr)
    t0, t_t, _ = c.get_Temperatures(Pc=pc, MR=mr, eps=eps_ref)
    return v_t, rho_t, mu_t, float(pr), float(gamma), float(t0), float(t_t)


def pressure_from_eps(inputs: dict, eps: float) -> float:
    c = _cea_object(inputs)
    return inputs["Pc"] / c.get_PcOvPe(Pc=inputs["Pc"], MR=inputs["MR"], eps=eps)


def eps_from_pressure_ratio(inputs: dict) -> float:
    pr = inputs.get("pressure_ratio", inputs.get("pr"))
    return float(_cea_object(inputs).get_eps_at_PcOvPe(Pc=inputs["Pc"], MR=inputs["MR"], PcOvPe=pr))


def ideal_expansion_pressure(inputs: dict) -> float:
    return pressure_from_eps(inputs, inputs["eps"])


def cfd_setup(inputs: dict) -> dict:
    c = _cea_object(inputs)
    entry_mach = entry_conditions(inputs)
    return {
        "combustion_end_total_temperature": c.get_Tcomb(Pc=inputs["Pc"], MR=inputs["MR"]),
        "combustion_end_total_pressure": inputs["Pc"],
        "inlet_velocity": c.get_SonicVelocities(
            Pc=inputs["Pc"], MR=inputs["MR"], eps=inputs["effective_throat_eps"]
        )[2] * entry_mach,
    }


def effective_throat_conditions(inputs: dict) -> tuple[float, float]:
    c = _cea_object(inputs)
    throat_eps = inputs["effective_throat_eps"]
    if throat_eps <= 1:
        effective_throat_velocity = c.get_SonicVelocities(Pc=inputs["Pc"], MR=inputs["MR"], eps=inputs["eps"])[1]
        effective_throat_rho = c.get_Densities(Pc=inputs["Pc"], MR=inputs["MR"], eps=inputs["eps"])[1]
    else:
        effective_throat_velocity = c.get_SonicVelocities(Pc=inputs["Pc"], MR=inputs["MR"], eps=throat_eps)[2] * \
        c.get_MachNumber(Pc=inputs["Pc"], MR=inputs["MR"], eps=throat_eps)
        effective_throat_rho = c.get_Densities(Pc=inputs["Pc"], MR=inputs["MR"], eps=throat_eps)[2]
    return effective_throat_velocity, effective_throat_rho


def exit_conditions(inputs: dict) -> tuple[float, float]:
    c = _cea_object(inputs)
    eps = inputs["eps"]
    exit_velocity = c.get_SonicVelocities(Pc=inputs["Pc"], MR=inputs["MR"], eps=eps)[2] * \
        c.get_MachNumber(Pc=inputs["Pc"], MR=inputs["MR"], eps=eps)
    exit_rho = c.get_Densities(Pc=inputs["Pc"], MR=inputs["MR"], eps=eps)[2]
    return exit_velocity, exit_rho

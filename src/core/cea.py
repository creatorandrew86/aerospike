from collections.abc import Callable
from functools import lru_cache
import numpy as np
from rocketcea.cea_obj_w_units import CEA_Obj
from scipy.integrate import cumulative_trapezoid
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq


# ponytail: @lru_cache on cea.py scalar keys eliminates all redundant CEA work;
# remaining O(N) Python segment loops in spike_component (~4 ms at N=50, ~0.25-0.5 s at N=10000)
# only justify vectorizing if high-N (>1000) sweeps measurably lag.
@lru_cache(maxsize=16)
def _cached_cea_object(oxidizer: str, fuel: str) -> CEA_Obj:
    return CEA_Obj(
        oxName=oxidizer,
        fuelName=fuel,
        pressure_units="Pa",
        sonic_velocity_units="m/s",
        density_units="kg/m^3",
        temperature_units="K",
    )


def _cea_object(inputs: dict) -> CEA_Obj:
    return _cached_cea_object(inputs["oxidizer"], inputs["fuel"])


@lru_cache(maxsize=4096)
def _eps_from_mach(oxidizer: str, fuel: str, pc: float, mr: float, mach: float, upper: float) -> float:
    c = _cached_cea_object(oxidizer, fuel)

    def residual(eps):
        return mach - c.get_MachNumber(Pc=pc, MR=mr, eps=eps)

    return brentq(residual, 1, upper)


def eps_from_mach(inputs: dict, mach: float) -> float:
    """Solve CEA area ratio eps for a given supersonic Mach number."""
    mach = max(float(mach), 1 + 1e-6)
    upper = max(1000.0, float(inputs.get("eps") or 1000.0) * 1.1)
    return _eps_from_mach(inputs["oxidizer"], inputs["fuel"], float(inputs["Pc"]), float(inputs["MR"]), mach, upper)


@lru_cache(maxsize=1024)
def _mach_from_eps(oxidizer: str, fuel: str, pc: float, mr: float, eps: float) -> float:
    return max(_cached_cea_object(oxidizer, fuel).get_MachNumber(Pc=pc, MR=mr, eps=eps), 1 + 1e-6)


def entry_conditions(inputs: dict) -> float:
    return _mach_from_eps(
        inputs["oxidizer"], inputs["fuel"], float(inputs["Pc"]), float(inputs["MR"]), float(inputs["effective_throat_eps"])
    )


def exit_mach(inputs: dict) -> float:
    return _mach_from_eps(
        inputs["oxidizer"], inputs["fuel"], float(inputs["Pc"]), float(inputs["MR"]), float(inputs["eps"])
    )


@lru_cache(maxsize=1024)
def _gamma_from_eps(oxidizer: str, fuel: str, pc: float, mr: float, eps: float) -> float:
    return _cached_cea_object(oxidizer, fuel).get_exit_MolWt_gamma(Pc=pc, MR=mr, eps=eps)[1]


def gamma_from_eps(inputs: dict, eps: float) -> float:
    return _gamma_from_eps(inputs["oxidizer"], inputs["fuel"], float(inputs["Pc"]), float(inputs["MR"]), float(eps))


@lru_cache(maxsize=128)
def _prandtl_meyer_from_mach(oxidizer: str, fuel: str, pc: float, mr: float, eps_max: float) -> Callable[[float], float]:
    """Build exact real-gas Prandtl-Meyer interpolator nu(M) = integral(sqrt(M^2 - 1) dV / V)."""
    c = _cached_cea_object(oxidizer, fuel)
    eps_range = 1.0 + np.geomspace(1e-4, eps_max - 1.0, num=80)

    mach_list = [1.0]
    vel_list = [c.get_SonicVelocities(Pc=pc, MR=mr, eps=eps_max)[1]]
    for eps in eps_range:
        m = c.get_MachNumber(Pc=pc, MR=mr, eps=eps)
        v = c.get_SonicVelocities(Pc=pc, MR=mr, eps=eps)[2] * m
        if m > mach_list[-1] and v > vel_list[-1]:
            mach_list.append(m)
            vel_list.append(v)

    m_arr = np.asarray(mach_list, dtype=float)
    v_arr = np.asarray(vel_list, dtype=float)
    integrand = np.sqrt(np.maximum(0.0, m_arr**2 - 1.0)) / v_arr
    nu_arr = np.concatenate(([0.0], cumulative_trapezoid(integrand, v_arr)))
    interp = PchipInterpolator(m_arr, nu_arr)
    return lambda mach: 0.0 if mach <= 1.0 else float(interp(mach))


def prandtl_meyer_from_mach(inputs: dict) -> Callable[[float], float]:
    """Build exact real-gas Prandtl-Meyer interpolator nu(M) = integral(sqrt(M^2 - 1) dV / V)."""
    eps_max = max(150.0, float(inputs.get("eps") or 150.0) * 1.1)
    return _prandtl_meyer_from_mach(inputs["oxidizer"], inputs["fuel"], float(inputs["Pc"]), float(inputs["MR"]), eps_max)


@lru_cache(maxsize=512)
def _sonic_throat_state(
    oxidizer: str, fuel: str, pc: float, mr: float, eps_ref: float
) -> tuple[float, float, float, float, float, float, float]:
    c = _cached_cea_object(oxidizer, fuel)
    v_t = float(c.get_SonicVelocities(Pc=pc, MR=mr, eps=eps_ref)[1])
    rho_t = float(c.get_Densities(Pc=pc, MR=mr, eps=eps_ref)[1])
    _, visc_mp, _, pr = c.get_Throat_Transport(Pc=pc, MR=mr)
    mu_t = float(visc_mp) * 1.0e-4
    _, gamma = c.get_Throat_MolWt_gamma(Pc=pc, MR=mr)
    t0, t_t, _ = c.get_Temperatures(Pc=pc, MR=mr, eps=eps_ref)
    return v_t, rho_t, mu_t, float(pr), float(gamma), float(t0), float(t_t)


def sonic_throat_state(inputs: dict) -> tuple[float, float, float, float, float, float, float]:
    """Return (v_t, rho_t, mu_t, Pr, gamma, T0, T_t) at the sonic throat (M = 1)."""
    eps_ref = float(inputs.get("eps") or 40.0)
    return _sonic_throat_state(inputs["oxidizer"], inputs["fuel"], float(inputs["Pc"]), float(inputs["MR"]), eps_ref)


@lru_cache(maxsize=16384)
def _pressure_from_eps(oxidizer: str, fuel: str, pc: float, mr: float, eps: float) -> float:
    return pc / _cached_cea_object(oxidizer, fuel).get_PcOvPe(Pc=pc, MR=mr, eps=eps)


def pressure_from_eps(inputs: dict, eps: float) -> float:
    return _pressure_from_eps(inputs["oxidizer"], inputs["fuel"], float(inputs["Pc"]), float(inputs["MR"]), float(eps))


@lru_cache(maxsize=512)
def _eps_from_pressure_ratio(oxidizer: str, fuel: str, pc: float, mr: float, pr: float) -> float:
    return float(_cached_cea_object(oxidizer, fuel).get_eps_at_PcOvPe(Pc=pc, MR=mr, PcOvPe=pr))


def eps_from_pressure_ratio(inputs: dict) -> float:
    pr = inputs.get("pressure_ratio", inputs.get("pr"))
    pr_val = float(pr) if pr is not None else None
    return _eps_from_pressure_ratio(inputs["oxidizer"], inputs["fuel"], float(inputs["Pc"]), float(inputs["MR"]), pr_val)


def ideal_expansion_pressure(inputs: dict) -> float:
    return pressure_from_eps(inputs, inputs["eps"])


@lru_cache(maxsize=512)
def _cfd_setup(oxidizer: str, fuel: str, pc: float, mr: float, effective_throat_eps: float) -> tuple[float, float]:
    c = _cached_cea_object(oxidizer, fuel)
    entry_mach = _mach_from_eps(oxidizer, fuel, pc, mr, effective_throat_eps)
    return (
        c.get_Tcomb(Pc=pc, MR=mr),
        c.get_SonicVelocities(Pc=pc, MR=mr, eps=effective_throat_eps)[2] * entry_mach,
    )


def cfd_setup(inputs: dict) -> dict:
    t_comb, v_inlet = _cfd_setup(
        inputs["oxidizer"], inputs["fuel"], float(inputs["Pc"]), float(inputs["MR"]), float(inputs["effective_throat_eps"])
    )
    return {
        "combustion_end_total_temperature": t_comb,
        "combustion_end_total_pressure": inputs["Pc"],
        "inlet_velocity": v_inlet,
    }


@lru_cache(maxsize=512)
def _effective_throat_conditions(
    oxidizer: str, fuel: str, pc: float, mr: float, throat_eps: float, eps_if_sonic: float | None
) -> tuple[float, float]:
    c = _cached_cea_object(oxidizer, fuel)
    if throat_eps <= 1:
        effective_throat_velocity = c.get_SonicVelocities(Pc=pc, MR=mr, eps=eps_if_sonic)[1]
        effective_throat_rho = c.get_Densities(Pc=pc, MR=mr, eps=eps_if_sonic)[1]
    else:
        effective_throat_velocity = (
            c.get_SonicVelocities(Pc=pc, MR=mr, eps=throat_eps)[2]
            * c.get_MachNumber(Pc=pc, MR=mr, eps=throat_eps)
        )
        effective_throat_rho = c.get_Densities(Pc=pc, MR=mr, eps=throat_eps)[2]
    return effective_throat_velocity, effective_throat_rho


def effective_throat_conditions(inputs: dict) -> tuple[float, float]:
    throat_eps = float(inputs["effective_throat_eps"])
    eps_if_sonic = float(inputs["eps"]) if throat_eps <= 1 else None
    return _effective_throat_conditions(
        inputs["oxidizer"], inputs["fuel"], float(inputs["Pc"]), float(inputs["MR"]), throat_eps, eps_if_sonic
    )


@lru_cache(maxsize=512)
def _exit_conditions(oxidizer: str, fuel: str, pc: float, mr: float, eps: float) -> tuple[float, float]:
    c = _cached_cea_object(oxidizer, fuel)
    exit_velocity = c.get_SonicVelocities(Pc=pc, MR=mr, eps=eps)[2] * c.get_MachNumber(Pc=pc, MR=mr, eps=eps)
    exit_rho = c.get_Densities(Pc=pc, MR=mr, eps=eps)[2]
    return exit_velocity, exit_rho


def exit_conditions(inputs: dict) -> tuple[float, float]:
    return _exit_conditions(inputs["oxidizer"], inputs["fuel"], float(inputs["Pc"]), float(inputs["MR"]), float(inputs["eps"]))

from collections.abc import Callable
import numpy as np
from rocketcea.cea_obj_w_units import CEA_Obj
from scipy.interpolate import interp1d
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
    c = _cea_object(inputs)
    mach = max(mach, 1 + 1e-6)

    def residual(eps):
        return mach - c.get_MachNumber(Pc=inputs["Pc"], MR=inputs["MR"], eps=eps)

    return brentq(residual, 1, 1000)


def entry_conditions(inputs: dict) -> float:
    return max(_cea_object(inputs).get_MachNumber(
        Pc=inputs["Pc"], MR=inputs["MR"], eps=inputs["effective_throat_eps"]
    ), 1 + 1e-6)


def exit_mach(inputs: dict) -> float:
    c = _cea_object(inputs)
    return max(c.get_MachNumber(Pc=inputs["Pc"], MR=inputs["MR"], eps=inputs["eps"]), 1 + 1e-6)


def gamma_from_eps(inputs: dict, eps: float) -> float:
    return _cea_object(inputs).get_exit_MolWt_gamma(Pc=inputs["Pc"], MR=inputs["MR"], eps=eps)[1]


def gamma_from_mach(inputs: dict) -> Callable[[float], float]:
    c = _cea_object(inputs)
    _, gamma_throat = c.get_Throat_MolWt_gamma(Pc=inputs["Pc"], MR=inputs["MR"])
    eps_range = np.geomspace(1.005, max(150.0, inputs.get("eps", 150.0)), num=80)

    mach_list = [1.0]
    gamma_list = [gamma_throat]
    for eps in eps_range:
        mach_list.append(c.get_MachNumber(Pc=inputs["Pc"], MR=inputs["MR"], eps=eps))
        gamma_list.append(c.get_exit_MolWt_gamma(Pc=inputs["Pc"], MR=inputs["MR"], eps=eps)[1])

    return interp1d(mach_list, gamma_list, kind="cubic", fill_value="extrapolate")


def ideal_expansion_pressure(inputs: dict) -> float:
    c = _cea_object(inputs)
    return inputs["Pc"] / c.get_PcOvPe(Pc=inputs["Pc"], MR=inputs["MR"], eps=inputs["eps"])


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

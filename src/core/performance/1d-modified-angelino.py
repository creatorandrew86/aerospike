"""1D Modified Aerospike Thrust Model Formulation.

Functions:
- throat_area(inputs, results): Computes the physical effective throat area
  normal to the inflow (A_t = mfr / (rho_t * v_t)).
- thruster_component(inputs, results, ambient_pressure): Calculates the axial
  thrust of the primary thruster, summing momentum flux projected by cos(theta_t)
  and static pressure force across the oblique throat characteristic surface.
- spike_component(inputs, results, ambient_pressure): Integrates the isentropic
  static pressure over the projected axial wall area of the contoured spike.
- base_component(inputs, results, ambient_pressure): Computes recirculating base
  wake pressure thrust over the blunt aft face of a truncated spike (0 if untruncated).
- thrust(inputs, results, ambient_pressure): Computes the total axial thrust,
  thrust coefficient (Cf), specific impulse (Isp), and component breakdown dictionary.
"""

import math
from core import cea
from core.geometry import _mach_angle, _prandtl_meyer_angle

G0 = 9.80665


def throat_area(inputs: dict, results: dict) -> float:
    v_t, rho_t = cea.effective_throat_conditions(inputs)
    return results["mfr"] / (rho_t * v_t)


def thruster_component(inputs: dict, results: dict, ambient_pressure: float) -> float:
    v_t, _ = cea.effective_throat_conditions(inputs)
    p_t = cea.pressure_from_eps(inputs, inputs["effective_throat_eps"])
    mfr = results["mfr"]
    a_t = throat_area(inputs, results)

    gamma_fn = cea.gamma_from_mach(inputs)
    m_entry = cea.entry_conditions(inputs)
    m_exit = cea.exit_mach(inputs)
    theta_t = _prandtl_meyer_angle(m_exit, gamma_fn) - _prandtl_meyer_angle(m_entry, gamma_fn)
    mu_t = _mach_angle(m_entry)

    area_factor = math.sin(mu_t + theta_t) / math.sin(mu_t)
    f_momentum = mfr * v_t * math.cos(theta_t)
    f_pressure = (p_t - ambient_pressure) * a_t * area_factor
    return f_momentum + f_pressure


def spike_component(inputs: dict, results: dict, ambient_pressure: float) -> float:
    r_x = results["R_x"]
    toroidal = results.get("aerospike_type") == "toroidal"
    p = [cea.pressure_from_eps(inputs, eps) for eps in results["eps_x"]]
    span = results.get("length") or results.get("width", 1.0)

    f_spike = 0.0
    for i in range(len(r_x) - 1):
        if toroidal:
            r1 = results["radius"] - r_x[i]
            r2 = results["radius"] - r_x[i + 1]
            a_proj = math.pi * (r1**2 - r2**2)
        else:
            a_proj = 2.0 * span * (r_x[i + 1] - r_x[i])
        p_avg = 0.5 * (p[i] + p[i + 1])
        f_spike += max(p_avg - ambient_pressure, 0.0) * a_proj
    return f_spike


def base_component(inputs: dict, results: dict, ambient_pressure: float) -> float:
    truncate = inputs.get("truncate_percent", 100)
    if truncate > 1.0:
        truncate /= 100.0
    if truncate >= 1.0:
        return 0.0

    r_x = results["R_x"]
    if results.get("aerospike_type") == "toroidal":
        base_radius = max(0.0, results["radius"] - r_x[-1])
        a_base = math.pi * base_radius**2
    else:
        base_height = max(0.0, results.get("nozzle_size", max(r_x)) - r_x[-1])
        span = results.get("length") or results.get("width", 1.0)
        a_base = 2.0 * span * base_height

    p_tip = cea.pressure_from_eps(inputs, results["eps_x"][-1])
    return max(0.4 * p_tip - ambient_pressure, 0.0) * a_base


def thrust(inputs: dict, results: dict, ambient_pressure: float) -> tuple[float, float, float, dict]:
    f_thruster = thruster_component(inputs, results, ambient_pressure)
    f_spike = spike_component(inputs, results, ambient_pressure)
    f_base = base_component(inputs, results, ambient_pressure)
    f_total = f_thruster + f_spike + f_base

    a_star = throat_area(inputs, results) / inputs["effective_throat_eps"]
    cf = f_total / (inputs["Pc"] * a_star)
    isp = f_total / (results["mfr"] * G0)
    components = {"thruster": f_thruster, "spike": f_spike, "base": f_base}
    return cf, f_total, isp, components



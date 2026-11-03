"""1D Design-Calibrated Aerospike Thrust Model Formulation.

Functions:
- throat_area(inputs, results): Computes the physical effective throat area
  normal to the flow (A_t = mfr / (rho_t * v_t)).
- throat_pressure_component(inputs, results, ambient_pressure): Static pressure
  force across the oblique throat characteristic surface.
- spike_component(inputs, results, ambient_pressure, full_length): Integrates
  static pressure over the projected axial wall area of the spike contour.
- base_component(inputs, results, ambient_pressure): Recirculating base wake
  pressure thrust over the blunt aft face of a truncated spike (0 if untruncated).
- throat_momentum_component(inputs, results): Solves for design-calibrated effective
  throat axial momentum flux at 100% full-length reference point.
- thrust(inputs, results, ambient_pressure): Computes total axial thrust,
  thrust coefficient (Cf), specific impulse (Isp), and component breakdown dictionary.
"""

import math
from core import cea
from core.geometry import _mach_angle, _prandtl_meyer_angle

G0 = 9.80665


def throat_area(inputs: dict, results: dict) -> float:
    v_t, rho_t = cea.effective_throat_conditions(inputs)
    return results["mfr"] / (rho_t * v_t)


def throat_pressure_component(inputs: dict, results: dict, ambient_pressure: float) -> float:
    p_t = cea.pressure_from_eps(inputs, inputs["effective_throat_eps"])
    a_t = throat_area(inputs, results)
    gamma_fn = cea.gamma_from_mach(inputs)
    m_entry = cea.entry_conditions(inputs)
    m_exit = cea.exit_mach(inputs)
    theta_t = _prandtl_meyer_angle(m_exit, gamma_fn) - _prandtl_meyer_angle(m_entry, gamma_fn)
    mu_t = _mach_angle(m_entry)
    a_t_proj = a_t * math.sin(mu_t + theta_t) / math.sin(mu_t)
    return (p_t - ambient_pressure) * a_t_proj


def spike_component(inputs: dict, results: dict, ambient_pressure: float, full_length: bool = False) -> float:
    r_x = results["R_x_full"] if full_length else results["R_x"]
    eps_x = results["eps_x_full"] if full_length else results["eps_x"]
    toroidal = results.get("aerospike_type") == "toroidal"
    p = [cea.pressure_from_eps(inputs, eps) for eps in eps_x]
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


def throat_momentum_component(inputs: dict, results: dict) -> float:
    p_d = cea.pressure_from_eps(inputs, inputs["eps"])
    v_e, _ = cea.exit_conditions(inputs)
    f_ideal_design = results["mfr"] * v_e
    f_spike_full = spike_component(inputs, results, p_d, full_length=True)
    f_throat_press_design = throat_pressure_component(inputs, results, p_d)
    return f_ideal_design - (f_spike_full + f_throat_press_design)


def thrust(inputs: dict, results: dict, ambient_pressure: float) -> tuple[float, float, float, dict]:
    f_throat_mom = throat_momentum_component(inputs, results)
    f_throat_press = throat_pressure_component(inputs, results, ambient_pressure)
    f_spike = spike_component(inputs, results, ambient_pressure)
    f_base = base_component(inputs, results, ambient_pressure)
    f_total = f_throat_mom + f_throat_press + f_spike + f_base

    a_star = throat_area(inputs, results) / inputs["effective_throat_eps"]
    cf = f_total / (inputs["Pc"] * a_star)
    isp = f_total / (results["mfr"] * G0)
    components = {
        "throat_momentum": f_throat_mom,
        "throat_pressure": f_throat_press,
        "spike": f_spike,
        "base": f_base,
    }
    return cf, f_total, isp, components


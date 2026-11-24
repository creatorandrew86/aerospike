"""Quasi-1D Streamtube Aerospike Thrust Model Formulation."""

import math
from core import cea

G0 = 9.80665
# ponytail: hardcoded streamtube efficiency; expose in UI when user-tunable loss calibration is needed
ETA = 0.97


def throat_area(inputs: dict, results: dict) -> float:
    """Compute physical effective throat area normal to the flow."""
    v_t, rho_t = cea.effective_throat_conditions(inputs)
    return results["mfr"] / (rho_t * v_t)


def thruster_component(inputs: dict, results: dict, ambient_pressure: float, eta: float = ETA) -> float:
    """Compute primary thruster momentum and static pressure thrust."""
    v_t, rho_t = cea.effective_throat_conditions(inputs)
    p_t = cea.pressure_from_eps(inputs, inputs["effective_throat_eps"])
    a_t = results["mfr"] / (rho_t * v_t)
    return eta * results["mfr"] * v_t + (eta * p_t - ambient_pressure) * a_t


def spike_component(inputs: dict, results: dict, ambient_pressure: float, eta: float = ETA) -> float:
    """Integrate streamtube static pressure thrust along the spike wall."""
    eps_x = results["eps_x"]
    a_star = throat_area(inputs, results) / inputs["effective_throat_eps"]
    p = [cea.pressure_from_eps(inputs, eps) for eps in eps_x]
    return sum(
        max(eta * 0.5 * (p[i] + p[i + 1]) - ambient_pressure, 0.0) * a_star * (eps_x[i + 1] - eps_x[i])
        for i in range(len(eps_x) - 1)
    )


def base_component(inputs: dict, results: dict, ambient_pressure: float) -> float:
    """Compute recirculating base wake pressure thrust for a truncated spike."""
    truncate = inputs.get("truncate_percent", 100)
    if truncate is None:
        return 0.0
    if truncate > 1.0:
        truncate /= 100.0
    if truncate >= 1.0:
        return 0.0

    r_x = results["R_x"]
    if results.get("aerospike_type") == "toroidal":
        a_base = math.pi * max(0.0, results["radius"] - r_x[-1]) ** 2
    else:
        base_height = max(0.0, results.get("nozzle_size", max(r_x)) - r_x[-1])
        span = results.get("length") or results.get("width", 1.0)
        a_base = 2.0 * span * base_height

    p_tip = cea.pressure_from_eps(inputs, results["eps_x"][-1])
    return max(0.4 * p_tip - ambient_pressure, 0.0) * a_base


def thrust(
    inputs: dict, results: dict, ambient_pressure: float, eta: float = ETA
) -> tuple[float, float, float, dict]:
    """Compute Cf, total thrust, Isp, and thrust component breakdown."""
    f_thruster = thruster_component(inputs, results, ambient_pressure, eta=eta)
    f_spike = spike_component(inputs, results, ambient_pressure, eta=eta)
    f_base = base_component(inputs, results, ambient_pressure)
    f_total = f_thruster + f_spike + f_base

    a_star = throat_area(inputs, results) / inputs["effective_throat_eps"]
    cf = f_total / (inputs["Pc"] * a_star)
    isp = f_total / (results["mfr"] * G0)
    return cf, f_total, isp, {"thruster": f_thruster, "spike": f_spike, "base": f_base}

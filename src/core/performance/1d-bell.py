"""1D Bell Nozzle Thrust Model.

Functions:
- throat_area(inputs, results): Computes the physical effective throat area
  normal to the flow (A_t = mfr / (rho_t * v_t)).
- thrust(inputs, results, ambient_pressure): Evaluates bell nozzle thrust using
  the aerospike's design area ratio (eps) with momentum and pressure terms
  (F = mfr * v_e + (p_e - p_a) * A_e), thrust coefficient (Cf), and specific impulse (Isp).
"""

from core import cea

G0 = 9.80665


def throat_area(inputs: dict, results: dict) -> float:
    v_t, rho_t = cea.effective_throat_conditions(inputs)
    return results["mfr"] / (rho_t * v_t)


def thrust(inputs: dict, results: dict, ambient_pressure: float) -> tuple[float, float, float, dict]:
    eps = inputs["eps"]
    v_e, _ = cea.exit_conditions(inputs)
    p_e = cea.pressure_from_eps(inputs, eps)

    mfr = results["mfr"]
    a_star = throat_area(inputs, results) / inputs["effective_throat_eps"]
    a_e = eps * a_star

    f_momentum = mfr * v_e
    f_pressure = (p_e - ambient_pressure) * a_e
    f_total = f_momentum + f_pressure

    cf = f_total / (inputs["Pc"] * a_star)
    isp = f_total / (mfr * G0)
    components = {"momentum": f_momentum, "pressure": f_pressure}
    return cf, f_total, isp, components


"""1D Ideal Expansion Rocket Nozzle Thrust Model.

Functions:
- throat_area(inputs, results): Computes the physical effective throat area
  normal to the flow (A_t = mfr / (rho_t * v_t)).
- ideal_eps(inputs, ambient_pressure): Determines the ideal isentropic expansion
  area ratio where exit static pressure equals ambient pressure (p_e = p_a).
- thrust(inputs, results, ambient_pressure): Computes ideal thrust (F = mfr * v_e),
  thrust coefficient (Cf), specific impulse (Isp), and component dictionary.
"""

from core import cea

G0 = 9.80665


def throat_area(inputs: dict, results: dict) -> float:
    v_t, rho_t = cea.effective_throat_conditions(inputs)
    return results["mfr"] / (rho_t * v_t)


def ideal_eps(inputs: dict, ambient_pressure: float) -> float:
    c = cea._cea_object(inputs)
    pc = inputs["Pc"]
    pa_eff = max(ambient_pressure, 1.0)
    pc_ov_pe = max(min(pc / pa_eff, 1e7), 1.0001)
    return c.get_eps_at_PcOvPe(Pc=pc, MR=inputs["MR"], PcOvPe=pc_ov_pe)


def thrust(inputs: dict, results: dict, ambient_pressure: float) -> tuple[float, float, float, dict]:
    c = cea._cea_object(inputs)
    eps = ideal_eps(inputs, ambient_pressure)
    m_exit = c.get_MachNumber(Pc=inputs["Pc"], MR=inputs["MR"], eps=eps)
    v_exit = c.get_SonicVelocities(Pc=inputs["Pc"], MR=inputs["MR"], eps=eps)[2] * m_exit

    mfr = results["mfr"]
    f_total = mfr * v_exit

    a_star = throat_area(inputs, results) / inputs["effective_throat_eps"]
    cf = f_total / (inputs["Pc"] * a_star)
    isp = f_total / (mfr * G0)
    components = {"momentum": f_total, "pressure": 0.0}
    return cf, f_total, isp, components


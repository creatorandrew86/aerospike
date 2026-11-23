from math import hypot


def graph_output(ui):
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt

    results = ui.case["results"]
    x, y = results["x"], results["R_x"]
    max_radius = results["nozzle_size"]
    radius = [max_radius - value for value in y]
    plt.figure()
    plt.plot(radius, x, color='black')
    plt.plot([-value for value in radius], x, color='black')
    lw = plt.rcParams["lines.linewidth"]
    plt.scatter([max_radius, -max_radius], [0.0, 0.0], s=(2 * lw) ** 2, color='red', edgecolors='none', zorder=5)
    teps = float(ui.case.get("definition", {}).get("effective_throat_eps") or 1.0)
    throat_length = results.get("throat_length")
    if teps > 1.0 and throat_length and len(radius) >= 2:
        dr, dx = radius[1] - radius[0], x[1] - x[0]
        seg = hypot(dr, dx)
        if seg > 0:
            u_r, u_x = dr / seg, dx / seg
            r_entry, x_entry = max_radius + throat_length * u_x, -throat_length * u_r
            plt.plot([r_entry, radius[0]], [x_entry, x[0]], color='black')
            plt.plot([-r_entry, -radius[0]], [x_entry, x[0]], color='black')
    truncate_percent = ui.case.get("definition", {}).get("truncate_percent")
    if truncate_percent is None:
        try:
            truncate_percent = float(ui.input_truncate_percentage.get())
        except (ValueError, TypeError):
            truncate_percent = 100
    if truncate_percent < 100:
        plt.plot([radius[-1], -radius[-1]], [x[-1], x[-1]], color='black', linestyle='--')
    plt.gca().set_aspect('equal', adjustable='box')
    plt.xlabel('R')
    plt.ylabel('x')
    plt.grid()
    plt.show()


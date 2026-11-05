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


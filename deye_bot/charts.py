"""PNG dashboard: three stacked panels (one axis each, never dual-axis)."""
import io
from datetime import datetime
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

# Reference data-viz palette (light mode): categorical slots 1-3, plus violet for the battery.
SURFACE, INK, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
PV, LOAD, GRID_C, BATT = "#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7"


def render(samples, hours, tz="Europe/Helsinki"):
    """Return PNG bytes, or None when there is nothing to plot."""
    if len(samples) < 2:
        return None
    zone = ZoneInfo(tz)
    t = [datetime.fromtimestamp(s.ts, zone) for s in samples]
    kw = lambda attr: [getattr(s, attr) / 1000 for s in samples]  # noqa: E731

    fig, axes = plt.subplots(3, 1, figsize=(8, 8), sharex=True, facecolor=SURFACE,
                             gridspec_kw={"height_ratios": [3, 2, 2]})
    for ax in axes:
        ax.set_facecolor(SURFACE)
        ax.grid(axis="y", color=GRID, linewidth=0.8)
        ax.tick_params(colors=MUTED, labelsize=9, length=0)
        for side in ("top", "right", "left"):
            ax.spines[side].set_visible(False)
        ax.spines["bottom"].set_color(GRID)

    p = axes[0]
    p.plot(t, kw("pv_w"), color=PV, linewidth=1.8, label="PV")
    p.plot(t, kw("load_w"), color=LOAD, linewidth=1.8, label="Load")
    p.plot(t, kw("grid_w"), color=GRID_C, linewidth=1.8, label="Grid (+ import / − export)")
    p.axhline(0, color=MUTED, linewidth=0.8)
    p.set_title("Power flows, kW", loc="left", color=INK, fontsize=11)
    p.legend(frameon=False, labelcolor=INK, fontsize=9, loc="lower right", bbox_to_anchor=(1, 1), ncols=3)

    b = axes[1]
    b.plot(t, kw("battery_w"), color=BATT, linewidth=1.8)
    b.axhline(0, color=MUTED, linewidth=0.8)
    b.set_title("Battery power, kW (+ discharging / − charging)", loc="left", color=INK, fontsize=11)

    s = axes[2]
    s.plot(t, [x.soc for x in samples], color=BATT, linewidth=1.8)
    s.set_ylim(0, 100)
    s.set_title("Battery SOC, %", loc="left", color=INK, fontsize=11)
    s.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=zone))
    s.xaxis.set_major_locator(mdates.AutoDateLocator(tz=zone, minticks=4, maxticks=12))

    fig.suptitle(f"Last {hours:g} h", x=0.01, ha="left", color=MUTED, fontsize=9)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, facecolor=SURFACE)
    plt.close(fig)
    return buf.getvalue()

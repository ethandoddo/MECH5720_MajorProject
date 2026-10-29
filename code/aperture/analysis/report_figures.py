"""Figures for the report's method section, drawn from the same constants the capture code uses.

  python -m aperture.analysis.report_figures    writes ../Report/images/patterns.png and blur_model.png

patterns.png    the panel images the server sends for each experiment, 128 x 160 pixels as the
                panel shows them, with the lens pupil outlined
blur_model.png  the thin-lens blur diameter against object distance for the open pupil and
                for one tile of a 3 x 3 and a 5 x 5 sub-aperture scan, which is the blur a
                refocused target keeps
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle
from PIL import Image, ImageDraw

from aperture import config as cfg
from aperture import patterns

OUT = cfg.ROOT.parent / "Report" / "images"

SENSOR_PITCH_MM = 22.3 / 5184      # Canon EOS 60D, 5184 px across a 22.3 mm sensor
FOCUS_MM = 1000.0                  # the focus distance the depth and refocus tests use
WAVELENGTH_MM = 550e-6
SCANS = (3, 5)
DPI = 600                          # column-width figures print at 3.3 in, so about 2000 px wide

INK = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e6e5e1"
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")   # validated categorical slots 1 to 3 on white

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
    "mathtext.fontset": "stix",
    "font.size": 8,
    "axes.labelsize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "axes.edgecolor": MUTED,
    "axes.labelcolor": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "pdf.fonttype": 42,
})


def star(points=5, inner=0.42):
    """a five-point star filling the pupil, the one custom bokeh shape"""
    size = int(round(patterns.pupil_px()))
    img = Image.new("L", (size, size), 0)
    r_out = size / 2
    ang = np.pi / 2 + np.arange(2 * points) * np.pi / points
    rad = np.where(np.arange(2 * points) % 2 == 0, r_out, r_out * inner)
    poly = [(r_out + r * np.cos(a), r_out - r * np.sin(a)) for r, a in zip(rad, ang)]
    ImageDraw.Draw(img).polygon(poly, fill=255)
    out = patterns.blank()
    x0 = (cfg.PANEL_W - size) // 2
    y0 = (cfg.PANEL_H - size) // 2
    out[y0:y0 + size, x0:x0 + size] = np.asarray(img) > 127
    return out


def fig_patterns():
    panels = [
        ("(a) open", patterns.build("open")),
        ("(b) Zhou A", patterns.build("zhou_a")),
        ("(c) Zhou B", patterns.build("zhou_b")),
        ("(d) Levin", patterns.build("levin")),
        ("(e) tile 1", patterns.build("scan0")),
        ("(f) star", star()),
    ]
    fig, axes = plt.subplots(1, 6, figsize=(3.3, 0.8))
    for ax, (title, mask) in zip(axes.flat, panels):
        ax.imshow(mask, cmap="gray", vmin=0, vmax=1, interpolation="nearest")
        cx, cy = (cfg.PANEL_W - 1) / 2, (cfg.PANEL_H - 1) / 2
        ax.add_patch(Circle((cx, cy), patterns.pupil_px() / 2, fill=False, ec=SERIES[1], lw=0.6, ls=(0, (2, 1.5))))
        ax.set_title(title, fontsize=6, color=INK, pad=2)
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_edgecolor(MUTED)
            s.set_linewidth(0.5)
    fig.subplots_adjust(left=0.005, right=0.995, top=0.83, bottom=0.01, wspace=0.06)
    fig.savefig(OUT / "patterns.png", dpi=DPI)
    plt.close(fig)


def blur_px(z, diameter_mm, square=False):
    """geometric defocus diameter and the diffraction width of the same opening, added in quadrature.
    The diffraction width is the first-zero diameter: 2.44 lambda v / d for the round pupil and
    2 lambda v / d for a square scan tile"""
    v = 1.0 / (1.0 / cfg.FOCAL_MM - 1.0 / FOCUS_MM)
    geo = diameter_mm * v * np.abs(1.0 / FOCUS_MM - 1.0 / z) / SENSOR_PITCH_MM
    diff = (2.0 if square else 2.44) * WAVELENGTH_MM * v / diameter_mm / SENSOR_PITCH_MM
    return np.hypot(geo, diff)


def fig_blur():
    z = np.linspace(650.0, 1350.0, 1401)
    fig, ax = plt.subplots(figsize=(3.3, 1.8))
    curves = [("open pupil", cfg.PUPIL_MM, "-", False)] + \
        [(rf"{n}$\times${n} tile", cfg.PUPIL_MM / n, ls, True) for n, ls in zip(SCANS, ("--", ":"))]
    # direct labels at z = 1180 mm, where the three curves sit furthest apart on the log axis:
    # the open pupil and 3 x 3 labels above their lines, the 5 x 5 label below its line
    label_z = 1180.0
    offsets = ((1.25, "bottom"), (1.25, "bottom"), (0.75, "top"))
    for (name, d, ls, sq), colour, (k, va) in zip(curves, SERIES, offsets):
        ax.plot(z, blur_px(z, d, sq), color=colour, lw=1.4, ls=ls, label=name, zorder=3)
        ax.text(label_z, blur_px(np.array([label_z]), d, sq)[0] * k, name, color=INK, fontsize=6.5, ha="left", va=va)
    for zt in (700, 850, 1000, 1150, 1300):
        ax.axvline(zt, color=MUTED, lw=0.4, ls=(0, (1, 2)), zorder=1)
    ax.set_yscale("log")
    ax.set_ylim(0.4, 400)
    ax.set_xlim(650, 1350)
    ax.set_xlabel("object distance $z$ (mm)")
    ax.set_ylabel("blur diameter (px)")
    ax.grid(axis="y", which="major", color=GRID, lw=0.5)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(loc="lower left", fontsize=6.5, frameon=False, handlelength=2.2)
    fig.tight_layout(pad=0.3)
    fig.savefig(OUT / "blur_model.png", dpi=DPI)
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    fig_patterns()
    fig_blur()
    print(f"wrote patterns.png and blur_model.png to {OUT}")

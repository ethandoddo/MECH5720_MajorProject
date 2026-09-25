"""Aperture patterns as PANEL_W x PANEL_H binary images, True where light passes.

Every pattern is drawn in millimetres on the lens pupil and converted to panel pixels
with PANEL_PITCH_MM, so the same pattern lands at the same physical size whichever
backend shows it. make() returns a PIL "L" image with 255 in the open pixels, or the
inverse when PANEL_INVERT is set.
"""
from pathlib import Path

import numpy as np
from PIL import Image

import config as cfg

OPEN = set("1#X*O")
SHUT = set("0._-")


def pupil_px(diameter_mm=None):
    return (diameter_mm or cfg.PUPIL_MM) / cfg.PANEL_PITCH_MM


def _grid():
    yy, xx = np.indices((cfg.PANEL_H, cfg.PANEL_W))
    return yy - (cfg.PANEL_H - 1) / 2, xx - (cfg.PANEL_W - 1) / 2


def blank():
    return np.zeros((cfg.PANEL_H, cfg.PANEL_W), dtype=bool)


def disc(diameter_mm=None):
    yy, xx = _grid()
    return np.hypot(yy, xx) <= pupil_px(diameter_mm) / 2


def white(**_):
    return ~blank()


def black(**_):
    return blank()


def load_design(path):
    """bool grid, True = open; 0/1 grids (space or comma separated) or character grids, as in Lab 3"""
    lines = [l.rstrip() for l in Path(path).read_text().splitlines() if l.strip()]
    rows = []
    for l in lines:
        toks = l.replace(",", " ").split() if " " in l.strip() or "," in l else list(l)
        bad = set(toks) - OPEN - SHUT
        if bad:
            raise ValueError(f"{path}: unknown symbols {sorted(bad)}")
        rows.append([t in OPEN for t in toks])
    widths = {len(r) for r in rows}
    if len(widths) != 1:
        raise ValueError(f"{path}: ragged rows, widths {sorted(widths)}")
    return np.array(rows, dtype=bool)


def raster(design, width_px):
    """nearest-neighbour rasterisation of a cell grid onto a centred square of width_px panel pixels"""
    n_rows, n_cols = design.shape
    yy, xx = _grid()
    u = (xx + width_px / 2) / width_px          # 0..1 across the design
    v = (yy + width_px / 2) / width_px
    inside = (u >= 0) & (u < 1) & (v >= 0) & (v < 1)
    col = np.clip((u * n_cols).astype(int), 0, n_cols - 1)
    row = np.clip((v * n_rows).astype(int), 0, n_rows - 1)
    return inside & design[row, col]


def coded(name, diameter_mm=None):
    """a Lab 3 style mask file scaled so its outer edge sits on the pupil diameter"""
    return raster(load_design(cfg.MASK_DIR / f"{name}.txt"), pupil_px(diameter_mm))


def subaperture(i, n=None, diameter_mm=None):
    """tile i of an n x n scan over the pupil, row major from the top left, clipped to the disc"""
    n = n or cfg.SCAN_N
    width = pupil_px(diameter_mm)
    r, c = divmod(i, n)
    yy, xx = _grid()
    u = (xx + width / 2) / width
    v = (yy + width / 2) / width
    tile = (u >= c / n) & (u < (c + 1) / n) & (v >= r / n) & (v < (r + 1) / n)
    return tile & disc(diameter_mm)


def shape_png(path, diameter_mm=None):
    """any black and white PNG, white = open, scaled to fit the pupil and centred: custom bokeh"""
    img = Image.open(path).convert("L")
    width = int(round(pupil_px(diameter_mm)))
    scale = width / max(img.size)
    size = (max(1, int(round(img.width * scale))), max(1, int(round(img.height * scale))))
    img = img.resize(size, Image.NEAREST)
    out = blank()
    x0 = (cfg.PANEL_W - size[0]) // 2
    y0 = (cfg.PANEL_H - size[1]) // 2
    out[y0:y0 + size[1], x0:x0 + size[0]] = np.asarray(img) > 127
    return out


def mask_names():
    return sorted(p.stem for p in cfg.MASK_DIR.glob("*.txt"))


def names():
    scans = [f"scan{i}" for i in range(cfg.SCAN_N * cfg.SCAN_N)]
    return ["open", "white", "black"] + mask_names() + scans


def build(name, diameter_mm=None):
    """bool array for a pattern name; masks/<name>.txt, scanN, or a path to a PNG"""
    if name == "open":
        return disc(diameter_mm)
    if name == "white":
        return white()
    if name == "black":
        return black()
    if name.startswith("scan") and name[4:].isdigit():
        return subaperture(int(name[4:]), diameter_mm=diameter_mm)
    if name.lower().endswith(".png"):
        return shape_png(name, diameter_mm)
    if (cfg.MASK_DIR / f"{name}.txt").exists():
        return coded(name, diameter_mm)
    raise KeyError(f"no pattern called {name!r}; have {names()}")


def to_image(open_mask):
    px = np.where(open_mask, 255, 0).astype(np.uint8)
    if cfg.PANEL_INVERT:
        px = 255 - px
    return Image.fromarray(px)


def make(name, diameter_mm=None):
    return to_image(build(name, diameter_mm))


if __name__ == "__main__":
    import sys
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else cfg.ROOT / "out" / "patterns"
    out.mkdir(parents=True, exist_ok=True)
    for n in names():
        make(n).save(out / f"{n}.png")
    print(f"pupil {cfg.PUPIL_MM:.1f} mm = {pupil_px():.1f} px; wrote {len(names())} patterns to {out}")

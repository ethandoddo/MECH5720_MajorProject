"""Aperture patterns as PANEL_W x PANEL_H binary images, True where light passes.

Every pattern is drawn in millimetres on the lens pupil and converted to panel pixels
with PANEL_PITCH_MM, so the same pattern lands at the same physical size whichever
backend shows it. make() returns a PIL "L" image with 255 in the open pixels, or the
inverse when PANEL_INVERT is set.

A pattern name is a built-in name, a mask file name, or a path to a PNG or GIF. Frame k
of a GIF is "<path>.gif#k", and expand() turns a GIF into one name per frame, so a
sequence takes one photo of each frame. "scan4" is tile 4 of the SCAN_N x SCAN_N scan
and "scan5_12" is tile 12 of a 5 x 5 scan, for any size.
"""
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageSequence

from aperture import config as cfg

OPEN = set("1#X*O")
SHUT = set("0._-")
IMAGE_EXT = (".png", ".gif")
GIF_DEFAULT_MS = 100        # browsers play a delay of 10 ms or less, or none, as 100 ms


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


def shape_png(path, diameter_mm=None, image_scale=1.0):
    """any PNG as an aperture, scaled to the pupil and centred: custom bokeh"""
    return shape_image(Image.open(path), diameter_mm, image_scale)


def open_pixels(img):
    """True where light passes. In an image with transparency, such as the sprites, the
    transparent pixels are open, like clear glass, and every opaque pixel is shut whatever its
    colour, black or grey. In an image with no transparency white is open. A screenshot often
    carries an alpha channel with every pixel opaque, and that counts as no transparency"""
    if img.has_transparency_data:
        clear = np.asarray(img.convert("RGBA"))[..., 3] <= 127
        if clear.any():
            return clear
    return np.asarray(img.convert("L")) > 127


def shape_image(img, diameter_mm=None, image_scale=1.0):
    """the current frame of a PIL image as an aperture: its longest side is image_scale times
    the pupil diameter, centred. 0.71 fits the whole image inside the round pupil; above 1
    the edges that run off the panel are cut"""
    mask = Image.fromarray(open_pixels(img).astype(np.uint8) * 255)
    width = int(round(pupil_px(diameter_mm) * image_scale))
    scale = width / max(mask.size)
    w, h = max(1, int(round(mask.width * scale))), max(1, int(round(mask.height * scale)))
    src = np.asarray(mask.resize((w, h), Image.NEAREST)) > 127
    out = blank()
    x0, y0 = (cfg.PANEL_W - w) // 2, (cfg.PANEL_H - h) // 2
    sx, sy = max(0, -x0), max(0, -y0)                 # rows and columns that fall off the panel
    dx, dy = max(0, x0), max(0, y0)
    cw, ch = min(w - sx, cfg.PANEL_W - dx), min(h - sy, cfg.PANEL_H - dy)
    out[dy:dy + ch, dx:dx + cw] = src[sy:sy + ch, sx:sx + cw]
    return out


def split_frame(name):
    """("walk.gif", 3) for "walk.gif#3"; (name, None) for anything else"""
    base, sep, frame = name.rpartition("#")
    if sep and frame.isdigit() and base.lower().endswith(".gif"):
        return base, int(frame)
    return name, None


def is_image(name):
    return split_frame(name)[0].lower().endswith(IMAGE_EXT)


def gif_frame(path, i, diameter_mm=None, image_scale=1.0):
    """frame i of a GIF, as shape_png does a PNG; later frames come out composited, as a browser shows them"""
    with Image.open(path) as img:
        n = getattr(img, "n_frames", 1)
        if not 0 <= i < n:
            raise ValueError(f"{path} has {n} frames, no frame {i}")
        img.seek(i)
        return shape_image(img, diameter_mm, image_scale)


def gif_play(path, diameter_mm=None, image_scale=1.0, rotation_deg=0.0):
    """every frame of a GIF as a panel image with its delay in ms, in one pass, for playback"""
    images, delays = [], []
    with Image.open(path) as img:
        for fr in ImageSequence.Iterator(img):
            images.append(to_image(rotate(shape_image(fr, diameter_mm, image_scale), rotation_deg)))
            ms = fr.info.get("duration") or 0
            delays.append(ms if ms > 10 else GIF_DEFAULT_MS)
    return images, delays


def expand(name):
    """a GIF becomes one name per frame, walk.gif#0, walk.gif#1 and so on; any other name stays as it is"""
    base, frame = split_frame(name)
    if frame is None and base.lower().endswith(".gif"):
        with Image.open(base) as img:
            return [f"{base}#{i}" for i in range(getattr(img, "n_frames", 1))]
    return [name]


def tag(name):
    """the pattern name as it goes into file names: an image path becomes its file stem, a GIF
    frame adds _fNN, and anything else that is unsafe in a file name becomes an underscore"""
    base, frame = split_frame(name)
    t = Path(base).stem + ("" if frame is None else f"_f{frame:02d}") if is_image(name) else name
    return re.sub(r"[^\w.-]", "_", t)


def mask_names():
    return sorted(p.stem for p in cfg.MASK_DIR.glob("*.txt"))


def names():
    scans = [f"scan{i}" for i in range(cfg.SCAN_N * cfg.SCAN_N)]
    return ["open", "white", "black"] + mask_names() + scans


def rotate(mask, deg):
    """the mask turned deg degrees anticlockwise, as the panel image shows it, about the panel
    centre, nearest neighbour. The centre sits between pixels on both axes, so 90 degree steps
    map pixel to pixel exactly; other angles resample. What turns off the panel is lost"""
    if not deg % 360:
        return mask
    yy, xx = _grid()                                   # offsets from the panel centre
    t = np.deg2rad(deg)
    sx = np.rint(np.cos(t) * xx - np.sin(t) * yy + (cfg.PANEL_W - 1) / 2).astype(int)
    sy = np.rint(np.sin(t) * xx + np.cos(t) * yy + (cfg.PANEL_H - 1) / 2).astype(int)
    inside = (sx >= 0) & (sx < cfg.PANEL_W) & (sy >= 0) & (sy < cfg.PANEL_H)
    out = blank()
    out[inside] = mask[sy[inside], sx[inside]]
    return out


def build(name, diameter_mm=None, image_scale=1.0, rotation_deg=0.0):
    """bool array for a pattern name; assets/masks/<name>.txt, scanN, a path to a PNG or GIF, or <path>.gif#k.
    A GIF with no frame number gives its first frame. image_scale sizes images only;
    rotation_deg turns any pattern, anticlockwise"""
    return rotate(_build(name, diameter_mm, image_scale), rotation_deg)


def _build(name, diameter_mm, image_scale):
    if name == "open":
        return disc(diameter_mm)
    if name == "white":
        return white()
    if name == "black":
        return black()
    if name.startswith("scan") and name[4:].isdigit():
        return subaperture(int(name[4:]), diameter_mm=diameter_mm)
    m = re.fullmatch(r"scan(\d+)_(\d+)", name)
    if m:
        n, i = int(m.group(1)), int(m.group(2))
        if n < 1 or i >= n * n:
            raise KeyError(f"{name!r}: a {n} x {n} scan has tiles 0 to {n * n - 1}")
        return subaperture(i, n, diameter_mm)
    if is_image(name):
        base, frame = split_frame(name)
        if base.lower().endswith(".gif"):
            return gif_frame(base, frame or 0, diameter_mm, image_scale)
        return shape_png(base, diameter_mm, image_scale)
    if (cfg.MASK_DIR / f"{name}.txt").exists():
        return coded(name, diameter_mm)
    raise KeyError(f"no pattern called {name!r}; have {names()}")


def to_image(open_mask):
    px = np.where(open_mask, 255, 0).astype(np.uint8)
    if cfg.PANEL_INVERT:
        px = 255 - px
    return Image.fromarray(px)


def make(name, diameter_mm=None, image_scale=1.0, rotation_deg=0.0):
    return to_image(build(name, diameter_mm, image_scale, rotation_deg))


if __name__ == "__main__":
    import sys
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else cfg.ROOT / "out" / "patterns"
    out.mkdir(parents=True, exist_ok=True)
    for n in names():
        make(n).save(out / f"{n}.png")
    print(f"pupil {cfg.PUPIL_MM:.1f} mm = {pupil_px():.1f} px; wrote {len(names())} patterns to {out}")

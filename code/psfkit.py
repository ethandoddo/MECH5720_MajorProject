"""PSF extraction, width, spectrum and a match against the displayed pattern.

The extraction and spectrum follow the Lab 3 psf module. The pattern match follows Lab 3
masks.fit_pose: the design is drawn as a template at a sweep of cell pitches, rotations and
flips, and normalised cross-correlation over shifts (cv2.matchTemplate, TM_CCOEFF_NORMED)
scores each one. The best score is the NCC the gates quote.
"""
from collections import namedtuple

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter

Pose = namedtuple("Pose", "deg flip pitch ncc")


# ---- extraction -------------------------------------------------------------------------

def peak(img, win):
    hp = gaussian_filter(img, 8) - gaussian_filter(img, win, mode="constant")
    return tuple(int(v) for v in np.unravel_index(np.argmax(hp), img.shape))


def locate(img, win, frac=0.1):
    """integer centroid of everything above frac of the peak within win of the brightest blob"""
    r0, c0 = peak(img, win)
    rs = slice(max(r0 - win, 0), min(r0 + win + 1, img.shape[0]))
    cs = slice(max(c0 - win, 0), min(c0 + win + 1, img.shape[1]))
    s = gaussian_filter(img, 2)
    w = s[rs, cs] - np.median(s[rs, cs])
    w[w < frac * w.max()] = 0
    tot = w.sum()
    if tot <= 0:
        raise ValueError("no psf energy above background")
    yy, xx = np.mgrid[rs, cs]
    return int(round((w * yy).sum() / tot)), int(round((w * xx).sum() / tot))


def crop(img, centre, size):
    h = size // 2
    r, c = centre
    return np.pad(img, h)[r:r + size, c:c + size]


def extract(img, size, centre=None):
    """(background-subtracted non-negative crop, centre) about the brightest blob"""
    centre = centre or locate(img, size)
    p = crop(img, centre, size)
    edges = np.concatenate([p[0], p[-1], p[:, 0], p[:, -1]])
    return np.clip(p - np.median(edges), 0, None), centre


def extent(p, frac=0.1):
    """width in px of the box holding everything above frac of the max"""
    rows, cols = np.nonzero(p > frac * p.max())
    if rows.size == 0:
        return 0
    return int(max(np.ptp(rows), np.ptp(cols)) + 1)


def energy(p, frac=0.05, margin=0.15):
    """sum over the box holding everything above frac of the smoothed max, grown by margin.
    Summing the whole crop would add the positive half of the clipped noise, which for a
    faint kernel outweighs the kernel itself"""
    s = gaussian_filter(p, 1.0)
    rows, cols = np.nonzero(s > frac * s.max())
    if rows.size == 0:
        return 0.0
    h = int(margin * max(np.ptp(rows), np.ptp(cols)) + 2)
    r0, r1 = max(rows.min() - h, 0), min(rows.max() + h + 1, p.shape[0])
    c0, c1 = max(cols.min() - h, 0), min(cols.max() + h + 1, p.shape[1])
    return float(p[r0:r1, c0:c1].sum())


# ---- spectrum ---------------------------------------------------------------------------

def fit(a, size):
    h, w = a.shape
    out = np.zeros((size, size), dtype=a.dtype)
    sr, sc = max((h - size) // 2, 0), max((w - size) // 2, 0)
    dr, dc = max((size - h) // 2, 0), max((size - w) // 2, 0)
    hh, ww = min(h, size), min(w, size)
    out[dr:dr + hh, dc:dc + ww] = a[sr:sr + hh, sc:sc + ww]
    return out


def spectrum(p, size=256):
    """|F| of the zero-padded kernel, dc centred and scaled to 1"""
    f = np.abs(np.fft.fftshift(np.fft.fft2(fit(p, size))))
    dc = f[size // 2, size // 2]
    if dc == 0:
        raise ValueError("empty kernel")
    return f / dc


def freq_radius(size):
    yy, xx = np.indices((size, size))
    return np.hypot(yy - size // 2, xx - size // 2) / size


def dips(mag, extent_px, band, rel=0.1):
    """boolean map of spectrum samples that sit below rel of the local envelope, inside the
    (lo, hi) cycles/px band. The envelope is a maximum filter about two null spacings wide,
    so a dip is a zero crossing relative to the spectrum around it rather than a point that
    is small because the whole high-frequency region is small"""
    from scipy.ndimage import maximum_filter
    n = mag.shape[0]
    w = int(2 * n / max(extent_px, 1)) + 1
    env = maximum_filter(mag, size=w)
    f = freq_radius(n)
    return (mag < rel * env) & (f >= band[0]) & (f <= band[1])


def shared_dip_fraction(dip_a, dip_b):
    """(dips in a, dips in b, shared, shared / smaller set)"""
    a, b, s = int(dip_a.sum()), int(dip_b.sum()), int((dip_a & dip_b).sum())
    return a, b, s, (s / min(a, b) if min(a, b) else 0.0)


# ---- pattern match ----------------------------------------------------------------------

def cell_span(d):
    cols = np.nonzero(d.any(0))[0]
    return int(cols[-1] - cols[0] + 1)


def template(d, pitch, deg, flip, size, blur=0.0):
    g = d[:, ::-1] if flip else d
    yy, xx = np.indices((size, size)) - (size - 1) / 2
    t = np.deg2rad(deg)
    u = xx * np.cos(t) - yy * np.sin(t)
    v = xx * np.sin(t) + yy * np.cos(t)
    col = np.floor(u / pitch + g.shape[1] / 2).astype(int)
    row = np.floor(v / pitch + g.shape[0] / 2).astype(int)
    ok = (col >= 0) & (col < g.shape[1]) & (row >= 0) & (row < g.shape[0])
    out = np.zeros((size, size))
    out[ok] = g[row[ok], col[ok]]
    return gaussian_filter(out, blur) if blur else out


def _best(d, img, size, degs, flips, pitches, blur):
    best = Pose(0.0, False, 1.0, -2.0)
    for flip in flips:
        for deg in degs:
            for pitch in pitches:
                t = template(d, pitch, deg, flip, size, blur).astype(np.float32)
                r = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED)
                if r.max() > best.ncc:
                    best = Pose(float(deg), flip, float(pitch), float(r.max()))
    return best


def match_design(p, design, degs=np.arange(0, 360, 3.0), flips=(False, True), blur=1.5):
    """pose of the design that best matches kernel p by NCC over shifts, pitch, angle and flip

    A lens images the pupil inverted and the panel may be mounted at any angle, so the sweep
    covers the full circle and both mirror images. The pitch sweep runs about the kernel
    extent divided by the design's cell span, then refines.
    """
    d = np.asarray(design, dtype=bool)
    size = p.shape[0]
    pad = size // 4
    img = np.pad(p / p.max(), pad).astype(np.float32)
    pitch0 = max(extent(p), 1) / cell_span(d)
    c = _best(d, img, size, degs, flips, pitch0 * np.linspace(0.75, 1.25, 11), blur)
    fine = c.deg + np.arange(-3, 3.01, 0.5) if len(degs) > 1 else (c.deg,)
    return _best(d, img, size, fine, (c.flip,), c.pitch * np.linspace(0.93, 1.07, 15), blur)


# ---- registration -----------------------------------------------------------------------

def shift_between(a, b):
    """(dy, dx, response) sub-pixel translation carrying b onto a by phase correlation"""
    win = cv2.createHanningWindow((a.shape[1], a.shape[0]), cv2.CV_64F)
    (dx, dy), resp = cv2.phaseCorrelate(a.astype(np.float64), b.astype(np.float64), win)
    return float(dy), float(dx), float(resp)

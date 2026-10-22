"""Scores every photo in this folder with one method and writes results.json next to it.

Run from the code folder: .venv/bin/python captures/flutter_5s_ISO100_f11/score.py
Each coded or box photo: sweep the blur length (lam 0.05, both directions for coded), keep the
lowest MSE, then RL 40 iterations at that length. Car speed = blur length / code time.
Scoring: flutter_deblur's Scorer, then the best of +-3 rows and +-12 binned px around its shift
(MSE after a gain and offset fit, middle half-width of the overlap). Detail = NCC of the 8 to 32
full-res px band against the reference over the same region."""
import json
import sys
from pathlib import Path

import numpy as np
import rawpy
from scipy.ndimage import gaussian_filter
from scipy.signal import fftconvolve

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import flutter_deblur as fd  # noqa: E402

B = 4
DIR = {"Run19_100ms_invert": "coded", "Run17_box_100ms_invert": "box", "Run16_100ms_invert": "impulse_and_dark",
       "Run14_100ms_invert": "bright_light", "Run8_100ms_invert": "leakage"}


def at(name):
    """a file in this folder from its run-prefixed name"""
    prefix = next(p for p in DIR if name.startswith(p + "_"))
    return str(HERE / DIR[prefix] / name)


class Score:
    def __init__(self, ref):
        self.R, self.sc = ref, fd.Scorer(ref, 160 // B)

    def region(self, a, dy, dx):
        h, w = self.R.shape
        ys, yd = slice(max(0, -dy), min(h, h - dy)), slice(max(0, dy), min(h, h + dy))
        xs, xd = slice(max(0, -dx), min(w, w - dx)), slice(max(0, dx), min(w, w + dx))
        p, q = a[ys, xs], self.R[yd, xd]
        half = w // 2
        x0 = (p.shape[1] - half) // 2
        return p[:, x0:x0 + half], q[:, x0:x0 + half]

    def fit(self, a, dy, dx):
        p, q = self.region(a, dy, dx)
        p, q = p.ravel() / self.sc.scale, q.ravel() / self.sc.scale
        vp, vq = p.var(), q.var()
        c = np.mean((p - p.mean()) * (q - q.mean()))
        return float(vq - c * c / vp), float(c / np.sqrt(vp * vq))

    def __call__(self, a):
        s = self.sc(a)
        (mse, ncc), dy, dx = min((self.fit(a, s["dy"] + j, s["dx"] + i), s["dy"] + j, s["dx"] + i)
                                 for j in range(-3, 4) for i in range(-48 // B, 48 // B + 1))
        p, q = self.region(a, dy, dx)
        band = lambda x: gaussian_filter(x, 8 / B) - gaussian_filter(x, 32 / B)  # noqa: E731
        detail = float(np.corrcoef(band(p).ravel(), band(q).ravel())[0, 1])
        return {"mse": round(mse, 5), "ncc": round(ncc, 3), "detail": round(detail, 3)}


def kern(code, L, left):
    k = fd.code_psf(code, L / B, 0.0, left)
    return k


def wiener(img, k, lam=0.05):
    return fd.deconvolve(img, k, lam)


def rl(img, k, iters=40):
    pad = len(k) + 16
    rows = np.pad(np.maximum(img, 1e-6), ((0, 0), (pad, pad)), mode="reflect")
    x = np.full_like(rows, rows.mean())
    kk, kf = k[None, :], k[::-1][None, :]
    for _ in range(iters):
        est = np.maximum(fftconvolve(x, kk, mode="same", axes=1), 1e-9)
        x = x * fftconvolve(rows / est, kf, mode="same", axes=1)
    return x[:, pad:pad + img.shape[1]]


def raw_stats(path):
    with rawpy.imread(path) as r:
        a = r.raw_image_visible.astype(float)
        bl, wl = np.mean(r.black_level_per_channel), r.white_level
    n = (a - bl) / (wl - bl)
    return float(n.mean()), float(n.std()), float(np.percentile(n, 99.9)), float(np.mean(a >= wl - 1))


def moving(prefix, tag, ref_tag="00_reference"):
    """sweep a coded or box photo, then RL 40 at the best length"""
    tr = json.load(open(at(f"{prefix}_{tag}.json")))
    code = [int(c) for c in tr["code"]]
    code_s = len(code) * tr["chop_ms"] / 1000
    S = Score(fd.load(at(f"{prefix}_{ref_tag}.cr2"), B))
    C = fd.load(at(f"{prefix}_{tag}.cr2"), B)
    dirs = (True, False) if 0 in code else (True,)
    best = None
    for L in range(200, 1201, 25):
        for left in dirs:
            s = S(wiener(C, kern(code, L, left)))
            if best is None or s["mse"] < best[2]["mse"]:
                best = (L, left, s)
    L, left, s = best
    print(f"  {prefix} {tag}: best {L} px {'left' if left else 'right'} {s}", flush=True)
    return {"run": prefix, "photo": tag, "blur_px": L, "direction": "left" if left or 0 not in code else "right",
            "code_s": code_s, "car_speed_px_s": round(L / code_s, 1),
            "as_is": S(C), "deblurred_lam0.05": s, "deblurred_RL40": S(rl(C, kern(code, L, left)))}


out = {"photos": [], "raw": {}}
for prefix, tag in [("Run19_100ms_invert", "01_coded"), ("Run17_box_100ms_invert", "01_box"),
                    ("Run14_100ms_invert", "02_coded"), ("Run14_100ms_invert", "03_box")]:
    out["photos"].append(moving(prefix, tag))
    json.dump(out, open(HERE / "results.json", "w"), indent=1)

for prefix in ("Run16_100ms_invert", "Run14_100ms_invert"):
    S = Score(fd.load(at(f"{prefix}_00_reference.cr2"), B))
    I = fd.load(at(f"{prefix}_01_impulse.cr2"), B)
    out["photos"].append({"run": prefix, "photo": "01_impulse", "as_is": S(I), "smoothed_2px_binned": S(gaussian_filter(I, 2))})
    print(f"  {prefix} impulse: {out['photos'][-1]}", flush=True)

for p in ["Run19_100ms_invert_00_reference", "Run19_100ms_invert_01_coded", "Run17_box_100ms_invert_00_reference",
          "Run17_box_100ms_invert_01_box", "Run16_100ms_invert_00_reference", "Run16_100ms_invert_01_impulse",
          "Run16_100ms_invert_04_dark", "Run14_100ms_invert_00_reference", "Run14_100ms_invert_01_impulse",
          "Run14_100ms_invert_02_coded", "Run14_100ms_invert_03_box", "Run14_100ms_invert_04_dark",
          "Run8_100ms_invert_03_box", "Run8_100ms_invert_04_leakage", "Run8_100ms_invert_05_dark"]:
    m, sd, p999, clip = raw_stats(at(f"{p}.cr2"))
    out["raw"][p] = {"mean": round(m, 5), "std": round(sd, 5), "p99.9": round(p999, 4), "clipped": clip}

r = out["raw"]
Lk = r["Run8_100ms_invert_04_leakage"]["mean"] - r["Run8_100ms_invert_05_dark"]["mean"]
Bx = r["Run8_100ms_invert_03_box"]["mean"] - r["Run8_100ms_invert_05_dark"]["mean"]
out["leak_fraction_run8"] = round(3.2 * Lk / (5 * Bx - 1.8 * Lk), 4)
json.dump(out, open(HERE / "results.json", "w"), indent=1)
print("leak", out["leak_fraction_run8"], "done")

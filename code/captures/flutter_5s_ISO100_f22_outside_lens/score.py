"""Scores every photo in this folder with one method, writes results.json and draws the pictures.

Run from the code folder: .venv/bin/python captures/flutter_5s_ISO100_f22_outside_lens/score.py
The method is the one in ../flutter_5s_ISO100_f11_outside_lens/score.py, plus:
- the blur sweep tries moving left only (the car always drives left; at f/22 the noise can make the
  time-reversed code score a few percent better, which is physically wrong)
- each photo is also scored at its best setting: lam 0.02 to 1, RL 5 to 80 iterations, impulse
  smoothed by sigma 1 to 4 binned px (4 to 16 full-res px)
Each coded or box photo: sweep the blur length (lam 0.05), keep the lowest MSE, then RL 40 at that
length. Car speed = blur length / code time. Scoring: flutter_deblur's Scorer, then the best of
+-3 rows and +-12 binned px around its shift (MSE after a gain and offset fit, middle half-width of
the overlap). Detail = NCC of the 8 to 32 full-res px band against the reference over the same
region."""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import rawpy
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import gaussian_filter
from scipy.signal import fftconvolve

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import flutter_deblur as fd  # noqa: E402

B = 4
DIR = {"Run3_f22_100ms_invert": "coded_and_impulse", "Run2_f22_100ms_invert": "box",
       "Run1_2_100ms_invert": "leakage_and_dark"}
LAMS, RL_ITERS, SIGMAS = (0.02, 0.05, 0.1, 0.2, 0.5, 1.0), (5, 10, 20, 40, 80), (1, 2, 3, 4)
# the "95" in the f/11 Run19 reference (binned y0, y1, x0, x1), found in each reference here by matching
TEMPLATE = HERE.parent / "flutter_5s_ISO100_f11_outside_lens/coded/Run19_100ms_invert_00_reference.cr2"
TEMPLATE_BOX = (330, 615, 665, 1010)
CROP = (660, 1000)


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
        return {"mse": round(mse, 5), "ncc": round(ncc, 3), "detail": round(detail, 3), "dy": dy, "dx": dx}

    def fitted(self, a, s):
        """a with the gain and offset that best match it to the reference over the scored region"""
        p, q = self.region(a, s["dy"], s["dx"])
        (g, o), *_ = np.linalg.lstsq(np.c_[p.ravel(), np.ones(p.size)], q.ravel(), rcond=None)
        return a * g + o


def kern(code, L):
    return fd.code_psf(code, L / B, 0.0, True)


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
    return {"mean": round(float(n.mean()), 5), "std": round(float(n.std()), 5),
            "p99.9": round(float(np.percentile(n, 99.9)), 4), "clipped": float(np.mean(a >= wl - 1))}


def exif(dng):
    e = Image.open(dng).getexif().get_ifd(0x8769)
    return {"f_number": float(e.get(33437)), "iso": int(e.get(34855)), "exposure_s": float(e.get(33434))}


def moving(S, prefix, tag):
    """sweep a coded or box photo moving left, then RL 40 and every setting at the best length"""
    tr = json.load(open(at(f"{prefix}_{tag}.json")))
    code = [int(c) for c in tr["code"]]
    code_s = len(code) * tr["chop_ms"] / 1000
    C = fd.load(at(f"{prefix}_{tag}.cr2"), B)
    curve = [(L, S(wiener(C, kern(code, L)))) for L in range(200, 1201, 25)]
    L, s = min(curve, key=lambda c: c[1]["mse"])
    k = kern(code, L)
    lam = {str(v): S(wiener(C, k, v)) for v in LAMS}
    its = {str(n): S(rl(C, k, n)) for n in RL_ITERS}
    print(f"  {prefix} {tag}: best {L} px left {s}", flush=True)
    return {"run": prefix, "photo": tag, "blur_px": L, "direction": "left", "code_s": code_s,
            "car_speed_px_s": round(L / code_s, 1), "as_is": S(C), "deblurred_lam0.05": s,
            "deblurred_RL40": its["40"], "lam": lam, "RL": its,
            "best_lam": float(min(lam, key=lambda v: lam[v]["mse"])),
            "best_RL_iters": int(min(its, key=lambda n: its[n]["mse"])),
            "sweep_mse": {str(L): c["mse"] for L, c in curve}}, C, k


# pictures

def u8(a, lo=None, hi=None):
    """as flutter_deblur.to_png draws it"""
    lo = np.percentile(a, 0.5) if lo is None else lo
    hi = np.percentile(a, 99.5) if hi is None else hi
    return (np.clip((a - lo) / max(hi - lo, 1e-12), 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)


def find_95(ref):
    y0, y1, x0, x1 = TEMPLATE_BOX
    t = fd.load(str(TEMPLATE), B)[y0:y1, x0:x1].astype(np.float32)
    _, _, _, (x, y) = cv2.minMaxLoc(cv2.matchTemplate(ref.astype(np.float32), t, cv2.TM_CCOEFF_NORMED))
    return y + (y1 - y0) // 2, x + (x1 - x0) // 2


def close_ups(R, panels):
    """the same part of the scene from each (image, score) around the "95", moved by each image's
    alignment and kept inside every image so no edge is blank"""
    cy, cx = find_95(R)
    h, w = R.shape
    dys, dxs = [0] + [s["dy"] for _, s in panels], [0] + [s["dx"] for _, s in panels]
    H, W = min(CROP[0], h - (max(dys) - min(dys))), min(CROP[1], w - (max(dxs) - min(dxs)))
    y0 = int(np.clip(cy - H // 2, max(dys), h - H + min(dys)))
    x0 = int(np.clip(cx - W // 2, max(dxs), w - W + min(dxs)))
    return [R[y0:y0 + H, x0:x0 + W]] + [a[y0 - s["dy"]:y0 - s["dy"] + H, x0 - s["dx"]:x0 - s["dx"] + W]
                                        for a, s in panels]


def labelled(img, text):
    im = Image.fromarray(img)
    d = ImageDraw.Draw(im)
    font = ImageFont.load_default(size=18)
    d.rectangle([0, 0, d.textbbox((4, 2), text, font=font)[2] + 4, 26], fill=0)
    d.text((4, 2), text, fill=255, font=font)
    return np.asarray(im)


def row(S, R, items, ref_title):
    """the reference and each (title, image, score) around the "95", fitted to the reference"""
    lo, hi = np.percentile(R, 0.5), np.percentile(R, 99.5)
    c = close_ups(R, [(S.fitted(a, s), s) for _, a, s in items])
    out = [labelled(u8(c[0], lo, hi), ref_title)]
    for (title, _, s), ci in zip(items, c[1:]):
        out.append(labelled(u8(ci, lo, hi), f"{title}  MSE {s['mse']:.4f}  detail {s['detail']:.2f}"))
    return out


def save_grid(rows, path):
    h = min(p.shape[0] for r in rows for p in r)
    w = min(p.shape[1] for r in rows for p in r)
    Image.fromarray(np.concatenate([np.concatenate([p[:h, :w] for p in r], 1) for r in rows], 0)).save(path)


out = {"photos": [], "raw": {}, "exif": {}}
CODED, BOX = "Run3_f22_100ms_invert", "Run2_f22_100ms_invert"

R3 = fd.load(at(f"{CODED}_00_reference.cr2"), B)
S3 = Score(R3)
coded, C, kc = moving(S3, CODED, "02_coded")
out["photos"].append(coded)
I = fd.load(at(f"{CODED}_01_impulse.cr2"), B)
sm = {str(v): S3(gaussian_filter(I, v)) for v in SIGMAS}
impulse = {"run": CODED, "photo": "01_impulse", "car_speed_px_s": coded["car_speed_px_s"],
           "speed_from": "this run's coded photo", "as_is": S3(I), "smoothed_2px_binned": sm["2"],
           "smoothed": sm, "best_sigma_binned": int(min(sm, key=lambda v: sm[v]["mse"]))}
out["photos"].append(impulse)
print(f"  {CODED} impulse: {impulse['as_is']} smoothed {impulse['smoothed_2px_binned']}", flush=True)
json.dump(out, open(HERE / "results.json", "w"), indent=1)

R2 = fd.load(at(f"{BOX}_00_reference.cr2"), B)
S2 = Score(R2)
box, X, kb = moving(S2, BOX, "03_box")
out["photos"].append(box)
json.dump(out, open(HERE / "results.json", "w"), indent=1)

for p in [f"{CODED}_00_reference", f"{CODED}_01_impulse", f"{CODED}_02_coded", f"{BOX}_00_reference",
          f"{BOX}_03_box", "Run1_2_100ms_invert_00_reference", "Run1_2_100ms_invert_02_leakage",
          "Run1_2_100ms_invert_03_dark"]:
    out["raw"][p] = raw_stats(at(f"{p}.cr2"))
    out["exif"][p] = exif(at(f"{p}.dng"))
r = out["raw"]
Lk = r["Run1_2_100ms_invert_02_leakage"]["mean"] - r["Run1_2_100ms_invert_03_dark"]["mean"]
Op = r["Run1_2_100ms_invert_00_reference"]["mean"] - r["Run1_2_100ms_invert_03_dark"]["mean"]
out["leak_fraction_run1_2"] = round(3.2 * Lk / (5 * Op - 1.8 * Lk), 4)
json.dump(out, open(HERE / "results.json", "w"), indent=1)

# pictures: full frame, unshifted; deblurs fitted to the reference and drawn with its black and white points
L = coded["blur_px"]
lo3, hi3 = np.percentile(R3, 0.5), np.percentile(R3, 99.5)
D = wiener(C, kc)
Image.fromarray(np.concatenate([u8(C), u8(S3.fitted(D, coded["deblurred_lam0.05"]), lo3, hi3), u8(R3, lo3, hi3)], 0)
                ).save(HERE / "compare.png")
bl = str(coded["best_lam"])
Db = wiener(C, kc, coded["best_lam"])
Image.fromarray(u8(S3.fitted(Db, coded["lam"][bl]), lo3, hi3)).save(HERE / f"deblurred_best_lam{bl}_{L}px.png")
Rr = rl(C, kc)
top = row(S3, R3, [("coded as is", C, coded["as_is"]), (f"coded deblurred lam 0.05, {L} px", D, coded["deblurred_lam0.05"]),
                   (f"coded deblurred RL40, {L} px", Rr, coded["deblurred_RL40"])], "reference (Run3_f22)")
save_grid([top[:2], top[2:]], HERE / "95_compare.png")
Lb = box["blur_px"]
r1 = row(S3, R3, [(f"coded deblurred lam {bl}, {L} px", Db, coded["lam"][bl]), ("impulse as is", I, impulse["as_is"]),
                  ("impulse smoothed 8 px", gaussian_filter(I, 2), impulse["smoothed_2px_binned"])], "reference (Run3_f22)")
r2 = row(S2, R2, [("box as is", X, box["as_is"]), (f"box deblurred lam 0.05, {Lb} px", wiener(X, kb), box["deblurred_lam0.05"]),
                  (f"box deblurred RL40, {Lb} px", rl(X, kb), box["deblurred_RL40"])], "reference (Run2_f22)")
save_grid([r1, r2], HERE / "95_baselines.png")
print("leak", out["leak_fraction_run1_2"], "done")

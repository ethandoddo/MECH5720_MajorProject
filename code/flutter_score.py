"""Checks and scores flutter runs that took reference, impulse, coded and box photos, and draws
the comparison pictures.

The method is the one in captures/flutter_5s_ISO100_f11/score.py, with the file lookup made
general, the blur sweep moving left only (the car always drives left; in dim light the
time-reversed code can score a few percent better by chance) and every photo also scored at its
best setting (lam 0.02 to 1, RL 5 to 80 iterations, impulse smoothed by sigma 1 to 4 binned px).
Run from the code folder, with the run's Name from the Flutter tab:
  .venv/bin/python flutter_score.py Run2_f22 [Run3_f22 ...] [--dir captures/flutter] [--out out/flutter]
  .venv/bin/python flutter_score.py Run2_f22 --pictures-only     (redraw from the saved <run>.json)
For each run: the manifest and traces are checked, each photo's raw level and EXIF are read,
coded and box are swept over blur length (lam 0.05, 200 to 1200 px in 25 px steps, --sweep to
change), RL 40 at the best length; the impulse is scored as is and smoothed (sigma 2 binned px).
A photo the run did not take, or that is no longer on disk, is skipped.
Writes <out>/<run>/<run>.json and the pictures:
  compare.png       coded / deblurred lam 0.05 / reference, full frame, as flutter_deblur.py draws it
  95_compare.png    the "95" up close: reference, coded as is, deblurred lam 0.05 and RL40
  95_baselines.png  (with box and impulse) every photo's "95": as taken on top, processed below
  <run>_<photo>*.png  each photo and deblur full frame, unshifted
Deblurred and close-up pictures are fitted to the reference (gain and offset, as in the score)
and drawn with the reference's black and white points."""
import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import rawpy
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import gaussian_filter
from scipy.signal import fftconvolve

CODE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CODE_DIR))
import flutter_deblur as fd  # noqa: E402

B = 4
CODE = "10001101101001011000001111010101"
# the "95" cut from Run19's reference (captures/flutter_5s_ISO100_f11/coded), binned 4 x 4, rows
# 330 to 615 and columns 665 to 1010; found in each new reference by matching
TEMPLATE = CODE_DIR / "flutter_95_template.npy"
CROP = (660, 1000)  # close-up size in binned px, as in the f/11 95_compare.png


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
        return {"mse": round(mse, 5), "ncc": round(ncc, 3), "detail": round(detail, 3), "dy": dy, "dx": dx,
                "scorer_dy": s["dy"], "scorer_dx": s["dx"]}

    def fitted(self, a, dy, dx):
        """a with the gain and offset that best match it to the reference over the scored region"""
        p, q = self.region(a, dy, dx)
        (g, o), *_ = np.linalg.lstsq(np.c_[p.ravel(), np.ones(p.size)], q.ravel(), rcond=None)
        return a * g + o


def kern(code, L, left):
    return fd.code_psf(code, L / B, 0.0, left)


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
    """mean, std, p99.9 of the raw over black in white-level units; clipped = fraction at or above
    LibRaw's white level; near_max = fraction within 1% of the photo's own maximum raw value"""
    with rawpy.imread(str(path)) as r:
        a = r.raw_image_visible.astype(float)
        bl, wl = np.mean(r.black_level_per_channel), r.white_level
    n = (a - bl) / (wl - bl)
    top = a.max()
    return {"mean": round(float(n.mean()), 5), "std": round(float(n.std()), 5),
            "p99.9": round(float(np.percentile(n, 99.9)), 4), "clipped": float(np.mean(a >= wl - 1)),
            "raw_max": int(top), "near_max": float(np.mean(a >= top - 0.01 * (top - bl)))}


def exif(dng):
    e = Image.open(dng).getexif().get_ifd(0x8769)
    f = lambda v: None if v is None else float(v)  # noqa: E731
    return {"f_number": f(e.get(33437)), "iso": e.get(34855), "exposure_s": f(e.get(33434))}


def check_manifest(m, prefix):
    out = {"error": m.get("error"), "done": m.get("done"), "tags": [f["tag"] for f in m["frames"]], "traces": {}}
    for f in m["frames"]:
        stem = prefix.parent / f"{prefix.name}_{f['index']:02d}_{f['tag']}"
        have = {ext: stem.with_suffix(ext).exists() for ext in (".cr2", ".dng", ".json")}
        t = {"files": have}
        if have[".json"]:
            tr = json.load(open(stem.with_suffix(".json")))
            code = tr["code"]
            want = tr["lead_ms"] + np.arange(len(code) + 1) * tr["chop_ms"]
            t.update({k: tr.get(k) for k in ("shutter_s", "code", "chop_ms", "lead_ms", "tail_ms", "method")})
            t["start_ms_max_err"] = float(np.max(np.abs(np.asarray(tr["start_ms"]) - want)))
            t["end_minus_start_max"] = float(np.max(np.asarray(tr["end_ms"]) - np.asarray(tr["start_ms"])))
        out["traces"][f["tag"]] = t
    return out


def frame(prefix, m, tag):
    f = next(f for f in m["frames"] if f["tag"] == tag)
    return prefix.parent / f"{prefix.name}_{f['index']:02d}_{tag}"


def code_of(stem):
    tr = json.load(open(stem.with_suffix(".json")))
    return [int(c) for c in tr["code"]], len(tr["code"]) * tr["chop_ms"] / 1000


def moving(S, stem, sweep, both=False):
    """sweep a coded or box photo, then RL 40 at the best length. The car drives left, so only left is
    tried unless both (in the dim f/22 light noise can make the reversed code score a little better)"""
    code, code_s = code_of(stem)
    C = fd.load(str(stem.with_suffix(".cr2")), B)
    dirs = (True, False) if both and 0 in code else (True,)
    best, curve = None, []
    for L in sweep:
        for left in dirs:
            s = S(wiener(C, kern(code, L, left)))
            curve.append([L, "left" if left else "right", s["mse"]])
            if best is None or s["mse"] < best[2]["mse"]:
                best = (L, left, s)
    L, left, s = best
    k = kern(code, L, left)
    return {"blur_px": L, "direction": "left" if left or 0 not in code else "right", "code_s": code_s,
            "car_speed_px_s": round(L / code_s, 1), "as_is": S(C), "deblurred_lam0.05": s,
            "deblurred_RL40": S(rl(C, k)), "tuned": tuned(S, C, k), "sweep": curve}


LAMS, RL_ITERS, SIGMAS = (0.02, 0.05, 0.1, 0.2, 0.5, 1.0), (5, 10, 20, 40, 80), (1, 2, 3, 4)


def tuned(S, C, k):
    """every lam and RL iteration count at the blur length the lam 0.05 sweep found, and the lowest MSE
    of each kind (the best-setting method, scored next to the fixed one)"""
    lam = {str(v): S(wiener(C, k, v)) for v in LAMS}
    its = {str(n): S(rl(C, k, n)) for n in RL_ITERS}
    bl, bi = min(lam, key=lambda v: lam[v]["mse"]), min(its, key=lambda n: its[n]["mse"])
    return {"lam": lam, "RL": its, "best_lam": float(bl), "best_RL_iters": int(bi)}


def tuned_impulse(S, I):
    """the impulse smoothed by each sigma (binned px; x4 for full-res px) and the lowest MSE"""
    sm = {str(v): S(gaussian_filter(I, v)) for v in SIGMAS}
    return {"smoothed": sm, "best_sigma_binned": int(min(sm, key=lambda v: sm[v]["mse"]))}


# pictures

def u8(a, lo=None, hi=None):
    """as flutter_deblur.to_png draws it: 0.5 and 99.5 percentiles (or lo, hi) to black and white, gamma 2.2"""
    lo = np.percentile(a, 0.5) if lo is None else lo
    hi = np.percentile(a, 99.5) if hi is None else hi
    return (np.clip((a - lo) / max(hi - lo, 1e-12), 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)


def find_95(ref):
    """(y, x) of the centre of the "95" in a reference and how well it matched (1 = exactly)"""
    t = np.load(TEMPLATE).astype(np.float32)
    m = cv2.matchTemplate(ref.astype(np.float32), t, cv2.TM_CCOEFF_NORMED)
    _, score, _, (x, y) = cv2.minMaxLoc(m)
    return y + t.shape[0] // 2, x + t.shape[1] // 2, float(score)


def close_ups(R, panels, cy, cx):
    """the same part of the scene from each panel (image, dy, dx): the reference's window around
    (cy, cx), moved by each image's alignment and kept inside every image so no edge is blank.
    An image matches the reference at a[y - dy, x - dx]."""
    h, w = R.shape
    dys, dxs = [0] + [p[1] for p in panels], [0] + [p[2] for p in panels]
    H = min(CROP[0], h - (max(dys) - min(dys)))
    W = min(CROP[1], w - (max(dxs) - min(dxs)))
    y0 = int(np.clip(cy - H // 2, max(dys), h - H + min(dys)))
    x0 = int(np.clip(cx - W // 2, max(dxs), w - W + min(dxs)))
    return [a[y0 - dy:y0 - dy + H, x0 - dx:x0 - dx + W] for a, dy, dx in panels]


def labelled(img, text):
    im = Image.fromarray(img)
    d = ImageDraw.Draw(im)
    font = ImageFont.load_default(size=18)
    x0, y0, x1, y1 = d.textbbox((4, 2), text, font=font)
    d.rectangle([0, 0, x1 + 4, y1 + 4], fill=0)
    d.text((4, 2), text, fill=255, font=font)
    return np.asarray(im)


def grid(rows, path):
    Image.fromarray(np.concatenate([np.concatenate(r, axis=1) for r in rows], axis=0)).save(path)


def label(what, s):
    return f"{what}  MSE {s['mse']:.4f}  detail {s['detail']:.2f}"


def pictures(prefix, m, res, out_dir):
    name = res["run"]
    R = fd.load(str(frame(prefix, m, "reference").with_suffix(".cr2")), B)
    S = Score(R)
    lo, hi = np.percentile(R, 0.5), np.percentile(R, 99.5)
    ref8 = u8(R, lo, hi)
    Image.fromarray(ref8).save(out_dir / f"{name}_reference.png")
    cy, cx, match = find_95(R)
    res["95_centre_binned_px"] = {"y": int(cy), "x": int(cx), "match": round(match, 3)}
    fit = lambda a, s: u8(S.fitted(a, s["dy"], s["dx"]), lo, hi)  # noqa: E731
    shown = {}  # (photo, version) -> (fitted 8-bit picture, score, title)
    for tag in ("coded", "box"):
        if tag not in res["photos"]:
            continue
        p, stem = res["photos"][tag], frame(prefix, m, tag)
        code, _ = code_of(stem)
        k = kern(code, p["blur_px"], p["direction"] == "left")
        C = fd.load(str(stem.with_suffix(".cr2")), B)
        L = p["blur_px"]
        for version, img, title in (("as_is", C, f"{tag} as is"),
                                    ("deblurred_lam0.05", wiener(C, k), f"{tag} deblurred lam 0.05, {L} px"),
                                    ("deblurred_RL40", rl(C, k), f"{tag} deblurred RL40, {L} px")):
            shown[tag, version] = (fit(img, p[version]), p[version], title)
        Image.fromarray(u8(C)).save(out_dir / f"{name}_{tag}.png")
        for version, short in (("deblurred_lam0.05", "lam0.05"), ("deblurred_RL40", "RL40")):
            Image.fromarray(shown[tag, version][0]).save(out_dir / f"{name}_{tag}_{short}_{L}px.png")
        if tag == "coded":
            grid([[u8(C)], [shown[tag, "deblurred_lam0.05"][0]], [ref8]], out_dir / "compare.png")
    if "impulse" in res["photos"]:
        p = res["photos"]["impulse"]
        I = fd.load(str(frame(prefix, m, "impulse").with_suffix(".cr2")), B)
        shown["impulse", "as_is"] = (fit(I, p["as_is"]), p["as_is"], "impulse as is")
        shown["impulse", "smoothed"] = (fit(gaussian_filter(I, 2), p["smoothed_2px_binned"]),
                                        p["smoothed_2px_binned"], "impulse smoothed 8 px")
        Image.fromarray(shown["impulse", "as_is"][0]).save(out_dir / f"{name}_impulse.png")

    run = {"name": name, "R": R, "ref8": ref8, "shown": shown, "cy": cy, "cx": cx, "res": res}
    if "coded" in res["photos"]:
        c = crops(run, [("coded", "as_is"), ("coded", "deblurred_lam0.05"), ("coded", "deblurred_RL40")])
        grid([c[:2], c[2:]], out_dir / "95_compare.png")
    return run


def crops(run, keys, ref_title="reference"):
    """the run's reference and the given (photo, version) pictures around the "95", labelled"""
    shown = run["shown"]
    panels = [(run["ref8"], 0, 0)] + [(shown[k][0], shown[k][1]["dy"], shown[k][1]["dx"]) for k in keys]
    c = close_ups(run["R"], panels, run["cy"], run["cx"])
    return [labelled(c[0], ref_title)] + [labelled(ci, label(shown[k][2], shown[k][1])) for ci, k in zip(c[1:], keys)]


def baselines_picture(coded_run, base_run, path):
    """the "95" up close: the coded photo on top, the box and impulse below, each row next to its own
    run's reference (the two runs can be different ones)"""
    two = coded_run is not base_run
    top = crops(coded_run, [("coded", "as_is"), ("coded", "deblurred_lam0.05"), ("coded", "deblurred_RL40")],
                "reference" + (f" ({coded_run['name'].removesuffix('_100ms_invert')})" if two else ""))
    box_best = min(("deblurred_lam0.05", "deblurred_RL40"), key=lambda v: base_run["res"]["photos"]["box"][v]["mse"])
    bottom = crops(base_run, [("box", "as_is"), ("box", box_best), ("impulse", "as_is"), ("impulse", "smoothed")],
                   "reference" + (f" ({base_run['name'].removesuffix('_100ms_invert')})" if two else ""))
    h, w = min(p.shape[0] for p in top + bottom), min(p.shape[1] for p in top + bottom)
    top, bottom = [p[:h, :w] for p in top], [p[:h, :w] for p in bottom]
    grid([top + [np.zeros_like(top[0])], bottom], path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--dir", default="captures/flutter")
    ap.add_argument("--out", default=str(CODE_DIR / "out" / "flutter"), help="each run goes in <out>/<run>/")
    ap.add_argument("--sweep", default="200:1200:25")
    ap.add_argument("--pictures-only", action="store_true", help="redraw the pictures from the saved <run>.json")
    ap.add_argument("--both-directions", action="store_true", help="sweep the coded photo moving right too")
    ap.add_argument("--folder", help="the folder name under --out, for one run (default: the run's name)")
    ap.add_argument("--baselines-from", help="a scored run (in its default folder) whose box and impulse go in "
                                             "this run's 95_baselines.png, when this run has none")
    a = ap.parse_args()
    if a.folder and len(a.runs) > 1:
        ap.error("--folder is for one run")
    lo, hi, st = (int(v) for v in a.sweep.split(":"))
    sweep = range(lo, hi + 1, st)
    for run in a.runs:
        name = run if run.endswith("_100ms_invert") else f"{run}_100ms_invert"
        out_dir = Path(a.out) / (a.folder or name.removesuffix("_100ms_invert"))
        out_dir.mkdir(parents=True, exist_ok=True)
        prefix = CODE_DIR / a.dir / name
        m = json.load(open(f"{prefix}_manifest.json"))
        if a.pictures_only:
            res = json.load(open(out_dir / f"{name}.json"))
        else:
            res = {"run": name, "manifest": check_manifest(m, prefix), "raw": {}, "exif": {}, "photos": {}}
            here = [f["tag"] for f in m["frames"] if frame(prefix, m, f["tag"]).with_suffix(".cr2").exists()]
            for tag in here:
                stem = frame(prefix, m, tag)
                res["raw"][tag] = raw_stats(stem.with_suffix(".cr2"))
                res["exif"][tag] = exif(stem.with_suffix(".dng"))
            print(json.dumps({k: res[k] for k in ("manifest", "raw", "exif")}, indent=1), flush=True)
            S = Score(fd.load(str(frame(prefix, m, "reference").with_suffix(".cr2")), B))
            for tag in ("coded", "box"):
                if tag in here:
                    res["photos"][tag] = moving(S, frame(prefix, m, tag), sweep, a.both_directions)
                    print(tag, {k: v for k, v in res["photos"][tag].items() if k != "sweep"}, flush=True)
                    json.dump(res, open(out_dir / f"{name}.json", "w"), indent=1)
            if "impulse" in here:
                I = fd.load(str(frame(prefix, m, "impulse").with_suffix(".cr2")), B)
                src = next((t for t in ("coded", "box") if t in res["photos"]), None)
                sp = res["photos"][src]["car_speed_px_s"] if src else None
                res["photos"]["impulse"] = {
                    "car_speed_px_s": sp, "speed_from": f"this run's {src} photo" if src else None,
                    "blur_px": None if sp is None else round(sp * res["exif"]["impulse"]["exposure_s"], 1),
                    "as_is": S(I), "smoothed_2px_binned": S(gaussian_filter(I, 2)), "tuned": tuned_impulse(S, I)}
                print("impulse", res["photos"]["impulse"], flush=True)
        run_pics = pictures(prefix, m, res, out_dir)
        json.dump(res, open(out_dir / f"{name}.json", "w"), indent=1)
        if all(t in res["photos"] for t in ("coded", "box", "impulse")):
            baselines_picture(run_pics, run_pics, out_dir / "95_baselines.png")
        elif a.baselines_from and "coded" in res["photos"]:
            bname = a.baselines_from if a.baselines_from.endswith("_100ms_invert") else f"{a.baselines_from}_100ms_invert"
            bdir = Path(a.out) / bname.removesuffix("_100ms_invert")
            bprefix = CODE_DIR / a.dir / bname
            bres = json.load(open(bdir / f"{bname}.json"))
            base_pics = pictures(bprefix, json.load(open(f"{bprefix}_manifest.json")), bres, bdir)
            baselines_picture(run_pics, base_pics, out_dir / "95_baselines.png")
        print("pictures in", out_dir, "; 95 found at", res["95_centre_binned_px"], flush=True)


if __name__ == "__main__":
    main()

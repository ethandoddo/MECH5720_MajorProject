"""Deblur the coded frame of a flutter run with its code and score it against the reference.

The blur is the code stretched over --blur px along the rows, open chops 1 and shut chops
--leak. Each row is deconvolved by a Wiener filter in the Fourier domain
(K = --lam). The result and the raw coded frame are each aligned to the averaged
reference frames by cross-correlation, fitted to them by a gain and an offset, and scored by
MSE over the middle half-width of the overlap, the reference scaled to its 99.5th percentile.
--sweep tries a range of blur lengths in both directions and keeps the lowest MSE.

A photo the camera took on its own shutter speed while the panel played the code sees only
the part of the cycle (lead black, code, tail black) inside its exposure. --exposure gives
that time in s; the blur is then that window of the cycle stretched over --blur px, the
window starting --phase ms after the play command. --phases sweeps the start as well.

Run from the code folder:
  .venv/bin/python -m aperture.analysis.flutter_deblur captures/flutter/Run1actual_100ms_invert --blur 100
  .venv/bin/python -m aperture.analysis.flutter_deblur captures/flutter/Run1actual_100ms_invert --sweep 50:5000:50
  .venv/bin/python -m aperture.analysis.flutter_deblur --coded ~/Desktop/IMG_9314.CR2 \\
      --reference captures/flutter/Run1actual_100ms_invert_01_reference.cr2 \\
      --trace captures/flutter/run4_100ms_invert_05_switch.json --exposure 0.5 \\
      --sweep 200:5200:200 --phases 500:4200:100 --bin 8
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, median_filter

from aperture.analysis import rawframe


def load(path, binning):
    """green channel, hot pixels median-filtered out, binned binning x binning"""
    g = median_filter(rawframe.read(path).green, 3)
    h, w = (g.shape[0] // binning) * binning, (g.shape[1] // binning) * binning
    return g[:h, :w].reshape(h // binning, binning, w // binning, binning).mean((1, 3))


def frame_path(prefix, frame):
    stem = prefix.parent / f"{prefix.name}_{frame['index']:02d}_{frame['tag']}"
    for ext in (".cr2", ".CR2", ".dng", ".DNG"):
        if stem.with_suffix(ext).exists():
            return stem.with_suffix(ext), stem.with_suffix(".json")
    raise FileNotFoundError(f"no raw file for {stem}")


def cycle(trace, step_ms=1.0):
    """the panel's transmission every step_ms from the play command: lead shut, the code, tail shut"""
    code = [int(c) for c in trace["code"]]
    chop, lead, tail = trace["chop_ms"], trace["lead_ms"], trace["tail_ms"]
    t = np.arange(0, lead + len(code) * chop + tail, step_ms)
    i = np.floor((t - lead) / chop).astype(int)
    inside = (i >= 0) & (i < len(code))
    return np.where(inside, np.asarray(code)[np.clip(i, 0, len(code) - 1)], 0).astype(float)


def psf(open_shut, length, leak, reverse):
    """a 0/1 transmission sampled evenly in time, stretched over length px at constant speed,
    integrated over each px and summed to 1; None when nothing in it is open"""
    v = np.asarray(open_shut, float)
    v = v + leak * (1 - v)
    m = max(int(np.ceil(length)), 1)
    x = (np.arange(len(v)) + 0.5) / len(v) * length
    k = np.bincount(np.minimum(x.astype(int), m - 1), weights=v, minlength=m)
    if k.sum() <= 0:
        return None
    k = k[::-1] if reverse else k
    return k / k.sum()


def code_psf(code, length, leak, reverse, sub=16):
    """the whole code stretched over length px"""
    return psf(np.repeat(np.asarray(code, float), sub), length, leak, reverse)


def deconvolve(img, k, lam):
    """row by row Wiener filter; rows padded by reflection and tapered so the
    edges do not wrap"""
    h, w = img.shape
    pad = len(k) + 16
    rows = np.pad(img, ((0, 0), (pad, pad)), mode="reflect")
    taper = np.ones(rows.shape[1])
    ramp = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, pad))
    taper[:pad], taper[-pad:] = ramp, ramp[::-1]
    mean = img.mean(1, keepdims=True)
    rows = (rows - mean) * taper + mean
    n = 1 << int(np.ceil(np.log2(rows.shape[1] + len(k))))
    K = np.fft.rfft(k, n)
    Y = np.fft.rfft(rows, n, axis=1)
    X = np.fft.irfft(Y * K.conj() / (np.abs(K) ** 2 + lam), n, axis=1)
    return X[:, pad:pad + w]


def _edges(x):
    x = gaussian_filter(x, 2)
    g = np.hypot(np.diff(x, axis=0)[:, :-1], np.diff(x, axis=1)[:-1])
    return (g - g.mean()) * np.outer(np.hanning(g.shape[0]), np.hanning(g.shape[1]))


class Scorer:
    """aligns a frame to the reference by cross-correlation of smoothed gradients, then scores
    it; the reference's spectrum is worked out once"""

    def __init__(self, ref, max_dy):
        self.ref, self.max_dy = ref, max_dy
        e = _edges(ref)
        self.sh = [2 * s for s in e.shape]
        self.R = np.fft.rfft2(e, self.sh)
        self.dys = np.r_[np.arange(0, max_dy + 1), np.arange(-max_dy, 0)] % self.sh[0]
        self.dx_all = np.fft.fftfreq(self.sh[1], 1 / self.sh[1]).astype(int)
        self.dy_all = np.fft.fftfreq(self.sh[0], 1 / self.sh[0]).astype(int)
        self.scale = np.percentile(ref, 99.5)

    def align(self, a):
        xc = np.fft.irfft2(self.R * np.fft.rfft2(_edges(a), self.sh).conj(), self.sh)
        sub = xc[self.dys]
        sub[:, np.abs(self.dx_all) > a.shape[1] // 2] = -np.inf     # keep at least half the width
        i, j = np.unravel_index(np.argmax(sub), sub.shape)
        return int(self.dy_all[self.dys[i]]), int(self.dx_all[j])

    def __call__(self, a):
        """MSE, PSNR, NCC, shift and fitted gain over the middle half-width of the overlap, so
        every candidate is scored on the same number of pixels"""
        ref = self.ref
        dy, dx = self.align(a)
        h, w = ref.shape
        ys, yd = slice(max(0, -dy), min(h, h - dy)), slice(max(0, dy), min(h, h + dy))
        xs, xd = slice(max(0, -dx), min(w, w - dx)), slice(max(0, dx), min(w, w + dx))
        p, q = a[ys, xs], ref[yd, xd]
        half = w // 2
        x0 = (p.shape[1] - half) // 2
        p, q = p[:, x0:x0 + half].ravel() / self.scale, q[:, x0:x0 + half].ravel() / self.scale
        A = np.c_[p, np.ones_like(p)]
        coef, *_ = np.linalg.lstsq(A, q, rcond=None)
        mse = float(np.mean((A @ coef - q) ** 2))
        return {"mse": mse, "psnr": float(10 * np.log10(1 / mse)), "ncc": float(np.corrcoef(p, q)[0, 1]),
                "dy": dy, "dx": dx, "gain": float(coef[0]), "offset": float(coef[1])}


def to_png(a, path, lo=None, hi=None):
    lo = np.percentile(a, 0.5) if lo is None else lo
    hi = np.percentile(a, 99.5) if hi is None else hi
    v = np.clip((a - lo) / max(hi - lo, 1e-12), 0, 1) ** (1 / 2.2)
    Image.fromarray((v * 255).astype(np.uint8)).save(path)


def span(text):
    start, stop, step = (float(v) for v in text.split(":"))
    return np.arange(start, stop + step / 2, step)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", nargs="?", help="the run's prefix, e.g. captures/flutter/Run1actual_100ms_invert")
    ap.add_argument("--coded", help="a coded photo to use instead of the run's coded frame")
    ap.add_argument("--reference", nargs="+", help="reference photo(s) to use instead of the run's, averaged")
    ap.add_argument("--trace", help="the trace .json giving code, chop, lead and tail (default the run's coded frame)")
    ap.add_argument("--exposure", type=float, help="the photo's own exposure in s; the blur is then that window of the cycle")
    ap.add_argument("--phase", type=float, default=1000, help="with --exposure: ms from the play command to the shutter opening")
    ap.add_argument("--phases", help="with --exposure: start:stop:step in ms, sweeps the phase too")
    ap.add_argument("--blur", type=float, default=100, help="blur length in full-res px, over the code or the exposure window")
    ap.add_argument("--sweep", help="start:stop:step in full-res px; tries both directions and keeps the lowest MSE")
    ap.add_argument("--reverse", action="store_true", help="target moved right to left (only without --sweep)")
    ap.add_argument("--leak", type=float, default=0.0, help="transmission of a shut chop relative to an open one")
    ap.add_argument("--lam", type=float, default=1e-3, help="Wiener filter K")
    ap.add_argument("--bin", type=int, default=4, help="bin the frames this many px a side first (default 4)")
    ap.add_argument("--max-dy", type=int, default=8, help="largest vertical shift tried in alignment, binned px")
    ap.add_argument("--out", help="output folder (default out/flutter/<run or photo name>)")
    a = ap.parse_args()

    cpath = Path(a.coded).expanduser() if a.coded else None
    rpaths = [Path(p).expanduser() for p in a.reference] if a.reference else None
    tpath = Path(a.trace) if a.trace else None
    if a.run:
        prefix = Path(a.run)
        manifest = json.loads(Path(f"{prefix}_manifest.json").read_text())
        coded = [f for f in manifest["frames"] if f["tag"] == "coded"]
        refs = [f for f in manifest["frames"] if f["tag"] == "reference"]
        if cpath is None:
            if not coded:
                sys.exit("the run has no coded frame; give one with --coded")
            cpath, ct = frame_path(prefix, coded[0])
            tpath = tpath or ct
        if rpaths is None:
            if not refs:
                sys.exit("the run has no reference frame; give one with --reference")
            rpaths = [frame_path(prefix, f)[0] for f in refs]
    if cpath is None or rpaths is None or tpath is None:
        sys.exit("give a run, or --coded, --reference and --trace")
    trace = json.loads(tpath.read_text())
    code = [int(c) for c in trace["code"]]
    out = Path(a.out or f"out/flutter/{Path(a.run).name if a.run and not a.coded else cpath.stem}")
    out.mkdir(parents=True, exist_ok=True)

    print(f"coded     {cpath}")
    print(f"code      {trace['code']}  {trace['chop_ms']} ms chops, lead {trace['lead_ms']} ms, tail {trace['tail_ms']} ms")
    C = load(cpath, a.bin)
    R = np.mean([load(p, a.bin) for p in rpaths], axis=0)
    print(f"reference {', '.join(p.name for p in rpaths)}; {R.shape[1]} x {R.shape[0]} after {a.bin}x{a.bin} binning")
    score = Scorer(R, a.max_dy)

    base = score(C)
    print(f"coded frame as it is   MSE {base['mse']:.5f}  PSNR {base['psnr']:.2f} dB  NCC {base['ncc']:.3f}  "
          f"shift ({base['dy']}, {base['dx']}) binned px")

    lengths = span(a.sweep) if a.sweep else [a.blur]
    dirs = (False, True) if a.sweep else (a.reverse,)
    if a.exposure:
        cyc = cycle(trace)
        n = int(round(a.exposure * 1000))
        phases = span(a.phases) if a.phases else [a.phase]
        windows = [(ph, cyc[int(ph):int(ph) + n]) for ph in phases]
        print(f"window    {a.exposure} s of the cycle, {len(phases)} phase(s)")
    else:
        windows = [(None, np.repeat(np.asarray(code, float), 16))]
    rows, best = [], None
    for ph, win in windows:
        if len(win) == 0:
            continue
        for L in lengths:
            for rev in dirs:
                k = psf(win, L / a.bin, a.leak, rev)
                if k is None:
                    continue
                s = score(deconvolve(C, k, a.lam))
                row = {"phase_ms": ph, "chops_open": None if ph is None else round(float(win.mean() * len(win) / trace["chop_ms"]), 2),
                       "blur_px": L, "direction": "left" if rev else "right", **s}
                rows.append(row)
                if len(windows) == 1:
                    print(f"blur {L:7.1f} px moving {row['direction']:5s}  MSE {s['mse']:.5f}  PSNR {s['psnr']:.2f} dB  "
                          f"NCC {s['ncc']:.3f}  shift ({s['dy']}, {s['dx']}) binned px")
                if best is None or s["mse"] < best[0]["mse"]:
                    best = (row, k)
        if len(windows) > 1:
            here = [r for r in rows if r["phase_ms"] == ph]
            if here:
                b = min(here, key=lambda r: r["mse"])
                print(f"phase {ph:6.0f} ms  open {b['chops_open']:4.2f} chops  best blur {b['blur_px']:6.0f} px "
                      f"{b['direction']:5s}  MSE {b['mse']:.5f}  NCC {b['ncc']:.3f}")

    with open(out / "scores.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    row, k = best
    D = deconvolve(C, k, a.lam)
    lo, hi = np.percentile(R, 0.5), np.percentile(R, 99.5)
    to_png(C, out / "coded.png")
    to_png(R, out / "reference.png", lo, hi)
    to_png(D * row["gain"] + row["offset"] * score.scale, out / "deblurred.png", lo, hi)
    np.save(out / "deblurred.npy", D.astype(np.float32))
    strip = np.concatenate([np.asarray(Image.open(out / n)) for n in ("coded.png", "deblurred.png", "reference.png")], axis=0)
    Image.fromarray(strip).save(out / "compare.png")
    where = "" if row["phase_ms"] is None else f" phase {row['phase_ms']:.0f} ms ({row['chops_open']} chops open)"
    print(f"\nbest:{where} blur {row['blur_px']:.1f} px moving {row['direction']}  MSE {row['mse']:.5f} "
          f"(coded as it is {base['mse']:.5f})  PSNR {row['psnr']:.2f} dB  NCC {row['ncc']:.3f}")
    print(f"wrote {out}/compare.png (coded / deblurred / reference), scores.csv, deblurred.npy")


if __name__ == "__main__":
    main()

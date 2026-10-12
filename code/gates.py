"""Score captured sessions against the three gates in the pitch.

A session is the folder capture_series.py or camview_capture.py downloaded, holding
<label>_<index>_<pattern>.<ext> frames and <label>_manifest.json. A session folder the
server wrote (captures/<stamp>_<label>/) works too. Every frame is a defocused point
source in the image centre, as in the Lab 3 PSF protocol.

  python gates.py gate1 captures/gate1/700mm_manifest.json --bare captures/bare/bare_00_open.CR2
  python gates.py gate2 captures/g2/700mm_manifest.json captures/g2/1000mm_manifest.json captures/g2/1300mm_manifest.json
  python gates.py gate3 captures/gate3/700mm_manifest.json
  python gates.py selftest

Gate 1  the coded PSF matches the displayed pattern at NCC >= 0.8, and the open disc
        through the panel is within 3 stops of the bare lens (--bare is a frame of the same
        point source with no panel, at the same ISO and shutter speed)
Gate 2  PSF width grows with defocus across the pair sessions, the two coded spectra
        share no nulls in the band, the open disc spectrum shows nulls
Gate 3  the two coded frames of one pair sequence each match their pattern at NCC >= 0.8,
        and the open frames before and after register within one pixel

Results print as a table and land in gates_<gate>.json beside the first manifest.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

import defocus
import patterns
import psfkit
import rawframe

NCC_PASS = 0.8            # pitch, gates 1 and 3
STOPS_PASS = 3.0          # pitch, gate 1
SHIFT_PASS_PX = 1.0       # pitch, gate 3
PSF_CROP = 256            # px, must hold the largest kernel at the farthest defocus
SPEC_SIZE = 512
BAND = (0.01, 0.12)       # cycles/px on the green plane where the pair is judged; the team's choice
DIP_REL = 0.1             # a spectrum sample below this fraction of its local envelope is a null
SHARED_PASS = 0.3         # gate 2 passes when the pair shares under this fraction of its nulls.
                          # On ideal masks the Zhou pair shares 10%, the Lab 3 levin/nayar
                          # pair 35%, a disc against itself 100%
MIN_EXTENT_FOR_NULLS = 25 # px; nearer focus than this the kernel has no nulls in the band to judge

RAW_FIRST = {".cr2": 0, ".dng": 0, ".png": 1, ".jpg": 2, ".jpeg": 2}


# ---- sessions -------------------------------------------------------------------------------

def load_session(manifest_path):
    """{"manifest": dict, "frames": [(pattern, path)]} resolving each frame's file on disk"""
    mp = Path(manifest_path)
    m = json.loads(mp.read_text())
    frames = []
    for fr in m["frames"]:
        found = []
        if fr.get("local"):
            local = Path(fr["local"])
            found = [p for p in local.parent.glob(local.name + ".*") if not p.name.endswith(("_preview.jpg", "_panel.png"))]
            if not found and local.exists():
                found = [local]
        if not found:
            for name in fr.get("files", [fr["file"]]):
                p = mp.parent / name
                if p.exists():
                    found.append(p)
        if not found:
            raise FileNotFoundError(f"{mp.name}: no file for frame {fr['index']} {fr['pattern']}")
        found.sort(key=lambda p: RAW_FIRST.get(p.suffix.lower(), 9))
        frames.append((fr["pattern"], found[0]))
    return {"manifest": m, "frames": frames, "path": mp}


def frames_named(session, pattern):
    return [p for n, p in session["frames"] if n == pattern]


def coded_names(session):
    """the two coded patterns in a pair session: everything that is not open, white or black"""
    return [n for n, _ in session["frames"] if n not in ("open", "white", "black")]


def psf_of(path, size=PSF_CROP):
    fr = rawframe.read(path)
    if fr.sat > 0:
        print(f"  warn {fr.path.name}: {100 * fr.sat:.3f}% of photosites saturated")
    p, centre = psfkit.extract(fr.green, size)
    return p, centre, fr


def design_of(name):
    return patterns.load_design(patterns.cfg.MASK_DIR / f"{name}.txt")


def dist_of(session):
    """distance in mm from the label, e.g. 700mm_pair -> 700; None when the label has none"""
    m = re.search(r"(\d+)\s*mm", session["manifest"]["label"])
    return int(m.group(1)) if m else None


def verdict(ok):
    return "PASS" if ok else "FAIL"


def save(session, gate, result):
    out = session["path"].parent / f"gates_{gate}.json"
    out.write_text(json.dumps(result, indent=2, default=float))
    print(f"  wrote {out}")


# ---- gate 1 ---------------------------------------------------------------------------------

def gate1(session, bare_path):
    print(f"Gate 1  {session['path'].name}")
    result = {"gate": 1, "session": session["manifest"]["session"], "patterns": {}, "transmission": None}
    for name in coded_names(session):
        p, centre, _ = psf_of(frames_named(session, name)[0])
        pose = psfkit.match_design(p, design_of(name))
        result["patterns"][name] = pose._asdict() | {"extent_px": psfkit.extent(p), "centre": centre}
        print(f"  {name:8s} NCC {pose.ncc:.3f}  {verdict(pose.ncc >= NCC_PASS)}   pitch {pose.pitch:.1f} px/cell  angle {pose.deg:.0f} deg  flip {pose.flip}")
    opens = frames_named(session, "open")
    if opens and bare_path:
        p_panel, _, f_panel = psf_of(opens[0])
        p_bare, _, f_bare = psf_of(bare_path)
        gain = rawframe.relative_gain(f_panel, f_bare)     # 1.0 when the two frames share ISO and shutter
        ratio = psfkit.energy(p_bare) / max(psfkit.energy(p_panel) / gain, 1e-12)
        stops = float(np.log2(ratio))
        result["transmission"] = {"stops_lost": stops, "energy_panel": psfkit.energy(p_panel),
                                  "energy_bare": psfkit.energy(p_bare), "exposure_gain": gain}
        print(f"  open disc through panel loses {stops:.2f} stops against the bare lens  {verdict(stops <= STOPS_PASS)}")
        if gain != 1.0:
            print(f"  note: ISO x exposure differed by x{gain:.3g} between the two frames and was corrected for")
    elif opens:
        print("  transmission skipped: give --bare <frame with no panel>")
    ok = all(v["ncc"] >= NCC_PASS for v in result["patterns"].values()) and \
        (result["transmission"] is None or result["transmission"]["stops_lost"] <= STOPS_PASS)
    result["pass"] = bool(ok and result["patterns"])
    print(f"  Gate 1 {verdict(result['pass'])}")
    save(session, "gate1", result)
    return result


# ---- gate 2 ---------------------------------------------------------------------------------

def gate2(sessions):
    print("Gate 2  " + ", ".join(s["path"].name for s in sessions))
    names = coded_names(sessions[0])
    if len(names) != 2:
        raise SystemExit(f"a pair session needs two coded patterns, got {names}")
    a, b = names
    result = {"gate": 2, "band": BAND, "dip_rel": DIP_REL, "distances": {}, "widths": {}, "fit": {}}
    widths = {n: [] for n in ("open", a, b)}
    dists = []
    for s in sessions:
        d = dist_of(s)
        if d is None:
            raise SystemExit(f"{s['path'].name}: put the distance in the label, e.g. 700mm")
        dists.append(d)
        ext, dipmap = {}, {}
        for n in ("open", a, b):
            p, _, _ = psf_of(frames_named(s, n)[0])
            ext[n] = psfkit.extent(p)
            widths[n].append(ext[n])
            dipmap[n] = psfkit.dips(psfkit.spectrum(p, SPEC_SIZE), ext[n], BAND, DIP_REL)
        row = {"widths": dict(ext), "judged": ext["open"] >= MIN_EXTENT_FOR_NULLS}
        line = f"  {d:5d} mm  widths open/{a}/{b} = {ext['open']}/{ext[a]}/{ext[b]} px"
        if row["judged"]:
            na, nb, shared, frac = psfkit.shared_dip_fraction(dipmap[a], dipmap[b])
            row.update(nulls_a=na, nulls_b=nb, shared=shared, shared_fraction=frac, nulls_open=int(dipmap["open"].sum()))
            line += f"   nulls {a} {na}  {b} {nb}  shared {shared} ({100 * frac:.0f}%)  open-disc nulls {row['nulls_open']}"
        else:
            line += f"   too near focus to judge nulls (open kernel under {MIN_EXTENT_FOR_NULLS} px)"
        result["distances"][d] = row
        print(line)
    result["widths"] = {n: dict(zip(dists, w)) for n, w in widths.items()}
    growth_ok = True
    for n, w in widths.items():
        try:
            f = defocus.fit(dists, w)
            result["fit"][n] = f._asdict()
            print(f"  {n:8s} width fit: focus {f.z_focus:.0f} mm, A {f.A:.0f}, floor {f.floor:.1f} px, rms {f.rms:.2f} px")
        except ValueError as e:
            growth_ok = False
            result["fit"][n] = {"error": str(e)}
            print(f"  {n:8s} width fit failed: {e}")
    judged = [r for r in result["distances"].values() if r["judged"]]
    shared_ok = bool(judged) and all(r["shared_fraction"] < SHARED_PASS for r in judged)
    open_ok = bool(judged) and all(r["nulls_open"] > 0 for r in judged)
    if not judged:
        print(f"  note: every session sits too near focus; no kernel reached {MIN_EXTENT_FOR_NULLS} px")
    elif not open_ok:
        print(f"  note: the open disc shows no dips below {DIP_REL} of its envelope; the noise floor is filling them")
    result["pass"] = bool(growth_ok and shared_ok and open_ok)
    print(f"  width grows with defocus {verdict(growth_ok)}, shared nulls {verdict(shared_ok)}, open-disc nulls {verdict(open_ok)}")
    print(f"  Gate 2 {verdict(result['pass'])}")
    save(sessions[0], "gate2", result)
    return result


# ---- gate 3 ---------------------------------------------------------------------------------

def gate3(session):
    print(f"Gate 3  {session['path'].name}")
    result = {"gate": 3, "session": session["manifest"]["session"], "patterns": {}, "registration": None, "timing": {}}
    for name in coded_names(session):
        p, _, _ = psf_of(frames_named(session, name)[0])
        pose = psfkit.match_design(p, design_of(name))
        result["patterns"][name] = pose._asdict()
        print(f"  {name:8s} NCC {pose.ncc:.3f}  {verdict(pose.ncc >= NCC_PASS)}")
    opens = frames_named(session, "open")
    if len(opens) >= 2:
        a = rawframe.read(opens[0]).green
        b = rawframe.read(opens[-1]).green
        dy, dx, resp = psfkit.shift_between(a, b)
        mag = float(np.hypot(dy, dx))
        result["registration"] = {"dy": dy, "dx": dx, "magnitude_px": mag, "response": resp}
        print(f"  open frames before and after shift by {mag:.2f} px (dy {dy:+.2f}, dx {dx:+.2f})  {verdict(mag < SHIFT_PASS_PX)}")
    else:
        print("  registration skipped: the sequence needs an open frame before and after the pair")
    fired = [fr["fired_s"] for fr in session["manifest"]["frames"]]
    shown = [fr["shown_s"] for fr in session["manifest"]["frames"]]
    if len(fired) > 1:
        gaps = np.diff(fired)
        result["timing"] = {"frame_to_frame_s": [float(g) for g in gaps], "settle_s": session["manifest"].get("settle_s"),
                            "show_to_fire_s": [float(f - s) for f, s in zip(fired, shown)]}
        print(f"  frame to frame {np.mean(gaps):.2f} s mean; the panel switch itself is inside the {session['manifest'].get('settle_s')} s settle")
    ncc_ok = all(v["ncc"] >= NCC_PASS for v in result["patterns"].values()) and bool(result["patterns"])
    reg_ok = result["registration"] is not None and result["registration"]["magnitude_px"] < SHIFT_PASS_PX
    result["pass"] = bool(ncc_ok and reg_ok)
    print(f"  Gate 3 {verdict(result['pass'])}")
    save(session, "gate3", result)
    return result


# ---- self test --------------------------------------------------------------------------------

def selftest(root):
    """synthetic sessions: each frame is a point source through the pattern, drawn as the
    pattern scaled by defocus with noise, shifted by a known amount, so every gate has a
    known answer"""
    from PIL import Image
    from scipy.ndimage import gaussian_filter, shift as nd_shift

    rng = np.random.default_rng(1)
    root = Path(root)
    H, W = 600, 800
    pair = patterns.cfg.PAIR
    focus = 1000.0

    def frame(name, dist, shift_px=(0.0, 0.0), trans=1.0):
        d = patterns.load_design(patterns.cfg.MASK_DIR / f"{name}.txt") if name not in ("open",) else None
        blur = 130.0 * abs(1 / focus - 1 / dist) * 1000 + 12     # px across the pupil image: 68, 12, 42
        if d is None:
            yy, xx = np.indices((13, 13)) - 6
            d = np.hypot(yy, xx) <= 6.5
        pitch = blur / 13
        img = psfkit.template(d, pitch, 180.0, True, 200) * trans
        canvas = np.zeros((H, W))
        canvas[H // 2 - 100:H // 2 + 100, W // 2 - 100:W // 2 + 100] = img
        canvas = gaussian_filter(canvas, 1.0)
        canvas = nd_shift(canvas, shift_px, order=1)
        canvas = 0.02 + 0.8 * canvas + rng.normal(0, 0.004, canvas.shape)
        return np.clip(canvas, 0, 1)

    def write_session(label, dist, shifts=None, trans=1.0):
        d = root / label
        d.mkdir(parents=True, exist_ok=True)
        names = ["open", pair[0], pair[1], "open"]
        shifts = shifts or [(0, 0)] * 4
        frames = []
        for i, (n, s) in enumerate(zip(names, shifts)):
            img = frame(n, dist, s, trans)
            path = d / f"{label}_{i:02d}_{n}.png"
            Image.fromarray((img * 255).astype(np.uint8)).save(path)
            frames.append({"index": i, "pattern": n, "file": path.name, "shown_s": i * 1.0, "fired_s": i * 1.0 + 0.3})
        m = {"label": label, "session": label, "settle_s": 0.3, "frames": frames}
        mp = d / f"{label}_manifest.json"
        mp.write_text(json.dumps(m, indent=2))
        return mp

    bare = root / "bare"
    bare.mkdir(parents=True, exist_ok=True)
    bare_path = bare / "bare_00_open.png"
    Image.fromarray((frame("open", 700, trans=1.0) * 255).astype(np.uint8)).save(bare_path)
    s700 = write_session("700mm", 700, trans=0.25)        # panel passes a quarter of the light: 2 stops
    s1000 = write_session("1000mm", 1000, trans=0.25)
    s1300 = write_session("1300mm", 1300, trans=0.25)
    s_g3 = write_session("g3_700mm", 700, shifts=[(0, 0), (0, 0), (0, 0), (0.4, -0.3)], trans=0.25)
    s_bad = write_session("bad_700mm", 700, shifts=[(0, 0), (0, 0), (0, 0), (2.5, 1.0)], trans=0.25)

    print("expected: NCC near 1, 2.0 stops lost, widths growing away from 1000 mm, few shared nulls, shift 0.5 px then 2.7 px\n")
    r1 = gate1(load_session(s700), bare_path)
    print()
    r2 = gate2([load_session(p) for p in (s700, s1000, s1300)])
    print()
    r3 = gate3(load_session(s_g3))
    print()
    r3b = gate3(load_session(s_bad))
    ok = r1["pass"] and abs(r1["transmission"]["stops_lost"] - 2.0) < 0.3 and r2["pass"] and r3["pass"] and not r3b["pass"]
    print(f"\nselftest {'PASS' if ok else 'FAIL'}")
    return ok


# ---- cli ----------------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="score sessions against the pitch gates")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g1 = sub.add_parser("gate1"); g1.add_argument("manifest"); g1.add_argument("--bare", help="frame with no panel")
    g2 = sub.add_parser("gate2"); g2.add_argument("manifests", nargs="+", help="pair sessions, one per distance")
    g3 = sub.add_parser("gate3"); g3.add_argument("manifest")
    st = sub.add_parser("selftest"); st.add_argument("--root", default=str(patterns.cfg.ROOT / "out" / "selftest"))
    args = ap.parse_args()
    if args.cmd == "gate1":
        gate1(load_session(args.manifest), args.bare)
    elif args.cmd == "gate2":
        gate2([load_session(m) for m in args.manifests])
    elif args.cmd == "gate3":
        gate3(load_session(args.manifest))
    elif args.cmd == "selftest":
        sys.exit(0 if selftest(args.root) else 1)


if __name__ == "__main__":
    main()

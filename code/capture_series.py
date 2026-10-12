"""Command line client for the aperture server, for scripted runs. camview_capture.py is
the window that does the same with a camera view. Run either on the laptop where
server.py is running, or point --host at the machine that runs it.

  python capture_series.py --status
  python capture_series.py --pattern levin
  python capture_series.py --set iso=100 --set shutterspeed=1/30
  python capture_series.py --sequence pair --label 700mm --outdir captures/gate3
  python capture_series.py --patterns open levin nayar open --label 700mm
  python capture_series.py --sequence scan --label 1000mm --outdir captures/refocus

A sequence runs inside the server and the files come back to --outdir named
<label>_<index>_<pattern>.<ext> with the manifest beside them.

Requires: requests
"""
import argparse
import json
import os
import shutil
import time

import requests


def parse_pairs(pairs):
    out = {}
    for p in pairs:
        k, _, v = p.partition("=")
        if not v:
            raise SystemExit(f"--set expects name=value, got {p!r}")
        out[k] = v
    return out


def download(base_url, session, name, dest):
    with requests.get(f"{base_url}/files/{session}/{name}", stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            shutil.copyfileobj(r.raw, f)
    print(f"saved {dest}")


def wait_for(base, session):
    """poll the sequence until the server marks it done, printing frames as they land"""
    seen = 0
    while True:
        m = requests.get(f"{base}/sequence/{session}", timeout=10).json()
        for fr in m["frames"][seen:]:
            print(f"{fr['index']:02d} {fr['pattern']:10s} shown {fr['shown_s']:7.3f}s fired {fr['fired_s']:7.3f}s")
        seen = len(m["frames"])
        if m.get("done"):
            return m
        time.sleep(0.5)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", default=8000, type=int)
    ap.add_argument("--status", action="store_true", help="print server and camera state")
    ap.add_argument("--camera", action="store_true", help="print gphoto2 --summary from the server")
    ap.add_argument("--list-config", action="store_true", help="print every gphoto2 config key")
    ap.add_argument("--set", dest="settings", action="append", default=[], metavar="NAME=VALUE",
                    help="camera setting, repeatable, e.g. --set iso=100 --set shutterspeed=1/30")
    ap.add_argument("--live", choices=["on", "off"], help="turn the camera's live view on or off")
    ap.add_argument("--pattern", help="show one pattern and stop")
    ap.add_argument("--capture", action="store_true", help="with --pattern: also take one frame")
    ap.add_argument("--sequence", help="named sequence from config.SEQUENCES: pair, scan, transmission")
    ap.add_argument("--patterns", nargs="+", help="explicit list of patterns to show and capture")
    ap.add_argument("--label", default="frame")
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--settle", type=float, default=None, help="seconds between showing and firing")
    ap.add_argument("--diameter", type=float, default=None, help="pupil diameter in mm, default from config")
    args = ap.parse_args()
    base = f"http://{args.host}:{args.port}"

    if args.status:
        print(json.dumps(requests.get(f"{base}/status", timeout=5).json(), indent=2))
    if args.camera:
        print(requests.get(f"{base}/camera", timeout=30).json().get("summary", "no summary"))
    if args.list_config:
        print(requests.get(f"{base}/camera/config", timeout=60).json().get("config"))
    if args.settings:
        r = requests.post(f"{base}/camera/config", json=parse_pairs(args.settings), timeout=60)
        r.raise_for_status()
        print("applied", r.json())
    if args.live:
        r = requests.post(f"{base}/liveview", json={"on": args.live == "on"}, timeout=30)
        print("live view", r.json())

    if args.pattern:
        r = requests.post(f"{base}/pattern", json={"name": args.pattern, "diameter_mm": args.diameter}, timeout=10)
        if r.status_code != 200:
            raise SystemExit(r.json().get("error"))
        print("showing", args.pattern)
        if args.capture:
            r = requests.post(f"{base}/capture", json={"label": args.label}, timeout=120)
            if r.status_code != 200:
                raise SystemExit(r.json().get("error"))
            info = r.json()
            os.makedirs(args.outdir, exist_ok=True)
            for name in info.get("files", [info["file"]]):
                ext = os.path.splitext(name)[1]
                download(base, info["session"], name, os.path.join(args.outdir, f"{args.label}_{args.pattern}{ext}"))

    if args.sequence or args.patterns:
        body = {"label": args.label}
        if args.patterns:
            body["patterns"] = args.patterns
        else:
            body["sequence"] = args.sequence
        if args.settle is not None:
            body["settle"] = args.settle
        if args.diameter is not None:
            body["diameter_mm"] = args.diameter
        r = requests.post(f"{base}/sequence", json=body, timeout=30)
        if r.status_code != 200:
            raise SystemExit(r.json().get("error"))
        session = r.json()["session"]
        manifest = wait_for(base, session)
        if manifest.get("error"):
            print("sequence stopped:", manifest["error"])
        os.makedirs(args.outdir, exist_ok=True)
        for fr in manifest["frames"]:
            for name in fr.get("files", [fr["file"]]):
                ext = os.path.splitext(name)[1]
                download(base, session, name, os.path.join(args.outdir, f"{args.label}_{fr['index']:02d}_{fr['pattern']}{ext}"))
            fr["local"] = os.path.join(args.outdir, f"{args.label}_{fr['index']:02d}_{fr['pattern']}")
        with open(os.path.join(args.outdir, f"{args.label}_manifest.json"), "w") as f:
            json.dump(manifest, f, indent=2)


if __name__ == "__main__":
    main()

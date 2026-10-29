"""Command line client for the aperture server, for scripted runs. camview_capture.py is
the window that does the same with a camera view. Run either on the laptop where
server.py is running, or point --host at the machine that runs it.

  python -m aperture.clients.capture_series --status
  python -m aperture.clients.capture_series --pattern levin
  python -m aperture.clients.capture_series --set iso=100 --set shutterspeed=1/30
  python -m aperture.clients.capture_series --sequence pair --label 700mm --outdir captures/gate3
  python -m aperture.clients.capture_series --patterns open levin nayar open --label 700mm
  python -m aperture.clients.capture_series --sequence scan --label 1000mm --outdir captures/refocus
  python -m aperture.clients.capture_series --patterns open ~/star.png ~/walk.gif open --label bokeh
  python -m aperture.clients.capture_series --play ~/walk.gif --speed 2
  python -m aperture.clients.capture_series --stop
  python -m aperture.clients.capture_series --code designed --chop 100 --label flutter      # one coded frame on M
  python -m aperture.clients.capture_series --code 1011001 --chop 200 --no-capture          # play it, trace only
  python -m aperture.clients.capture_series --go                                            # a paused job carries on
  python -m aperture.clients.capture_series --abort                                         # stop the running job

A sequence runs inside the server and the files come back to --outdir named
<label>_<index>_<pattern>.<ext> with the manifest beside them. A GIF in --patterns gives
one frame per GIF frame, and an image path is named by its file stem, walk_f03 for frame
3 of walk.gif. --code plays a flutter shutter code on the panel during one photo at the
shutter speed on M, which has to be at least lead + code. "designed" is the code
flutter.py designs, and the trace of switch times comes back as <label>_00_code.json.
The Experiments window in camview_capture.py builds the full flutter set with its baselines.

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
            fired = "   none" if fr.get("fired_s") is None else f"{fr['fired_s']:7.3f}s"
            print(f"{fr['index']:02d} {fr.get('tag', fr['pattern']):10s} shown {fr['shown_s']:7.3f}s fired {fired}")
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
    ap.add_argument("--play", metavar="GIF", help="loop a GIF on the panel until --stop or another pattern")
    ap.add_argument("--speed", type=float, default=1.0, help="with --play: multiplier on the GIF's frame delays")
    ap.add_argument("--stop", action="store_true", help="stop GIF playback")
    ap.add_argument("--sequence", help="named sequence from config.SEQUENCES: pair, scan, transmission")
    ap.add_argument("--patterns", nargs="+", help="explicit list of patterns to show and capture")
    ap.add_argument("--label", default="frame")
    ap.add_argument("--outdir", default=".")
    ap.add_argument("--settle", type=float, default=None, help="seconds between showing and firing")
    ap.add_argument("--diameter", type=float, default=None, help="pupil diameter in mm, default from config")
    ap.add_argument("--image-scale", type=float, default=1.0,
                    help="PNG and GIF size against the pupil: 1 = longest side fills it, 0.71 = fits inside the circle")
    ap.add_argument("--rotate", type=float, default=0.0, help="turn the pattern this many degrees anticlockwise")
    ap.add_argument("--code", help="flutter shutter code of 0s and 1s, or 'designed'; plays it in one frame on M")
    ap.add_argument("--chop", type=int, default=None, help="with --code: chop length in ms, default from config")
    ap.add_argument("--method", choices=["invert", "fill"], default="invert", help="with --code: how the panel switches")
    ap.add_argument("--no-capture", action="store_true", help="with --code: play it and record the trace, no camera")
    ap.add_argument("--go", action="store_true", help="let a paused job carry on")
    ap.add_argument("--abort", action="store_true", help="stop the running job after its current step")
    args = ap.parse_args()
    base = f"http://{args.host}:{args.port}"

    if args.go or args.abort:
        r = requests.post(f"{base}/sequence/{'go' if args.go else 'stop'}", json={}, timeout=10)
        print(r.json().get("note") or r.json().get("error") or "ok")

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
        r = requests.post(f"{base}/pattern", json={"name": args.pattern, "diameter_mm": args.diameter,
                                                          "image_scale": args.image_scale, "rotation_deg": args.rotate}, timeout=10)
        if r.status_code != 200:
            raise SystemExit(r.json().get("error"))
        print("showing", args.pattern)
        if args.capture:
            r = requests.post(f"{base}/capture", json={"label": args.label}, timeout=120)
            if r.status_code != 200:
                raise SystemExit(r.json().get("error"))
            info = r.json()
            os.makedirs(args.outdir, exist_ok=True)
            tag = info.get("tag", info["pattern"])
            for name in info.get("files", [info["file"]]):
                ext = os.path.splitext(name)[1]
                download(base, info["session"], name, os.path.join(args.outdir, f"{args.label}_{tag}{ext}"))

    if args.stop:
        r = requests.post(f"{base}/play", json={"stop": True}, timeout=15)
        print("stopped" if r.status_code == 200 else r.json().get("error"))
    if args.play:
        r = requests.post(f"{base}/play", json={"name": os.path.abspath(os.path.expanduser(args.play)),
                                                "speed": args.speed, "diameter_mm": args.diameter,
                                                "image_scale": args.image_scale, "rotation_deg": args.rotate}, timeout=30)
        if r.status_code != 200:
            raise SystemExit(r.json().get("error"))
        info = r.json()
        print(f"playing {info['playing']} at {info['speed']}x" +
              (f", {info['frames']} frames" if "frames" in info else ""))

    if args.sequence or args.patterns or args.code:
        body = {"label": args.label, "image_scale": args.image_scale, "rotation_deg": args.rotate}
        if args.code:
            code = args.code
            if code == "designed":
                from aperture import flutter
                code = flutter.to_text(flutter.design())
            step = {"code": code, "method": args.method, "capture": not args.no_capture}
            if args.chop is not None:
                step["chop_ms"] = args.chop
            body["patterns"] = [step]
        elif args.patterns:
            # the server opens image paths from its own working directory, so send them absolute
            body["patterns"] = [os.path.abspath(p) if p.lower().endswith((".png", ".gif")) else p
                                for p in args.patterns]
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
            tag = fr.get("tag", fr["pattern"])
            for name in fr.get("files", [fr["file"]]):
                ext = os.path.splitext(name)[1]
                download(base, session, name, os.path.join(args.outdir, f"{args.label}_{fr['index']:02d}_{tag}{ext}"))
            fr["local"] = os.path.join(args.outdir, f"{args.label}_{fr['index']:02d}_{tag}")
        with open(os.path.join(args.outdir, f"{args.label}_manifest.json"), "w") as f:
            json.dump(manifest, f, indent=2)


if __name__ == "__main__":
    main()

"""Aperture and DSLR server. Run this on the laptop that has the Arduino and the camera on USB.

The server streams each pattern to the Arduino that drives the LCD in the optical path and
fires the Canon through gphoto2. camview_capture.py and capture_series.py talk to it over
HTTP, the same shape as the Lab 1 Pi camera server, so a second machine can drive the rig
too. A sequence of patterns and captures runs in its own thread, so no client round trip
sits between a pattern change and the shutter, and the clients poll for progress.

  python server.py --display arduino --camera gphoto     # the real thing
  python server.py --display window --camera dummy       # a window instead of the panel, no camera

Endpoints:
  GET  /status                 backends, current pattern, panel geometry, last capture, running job
  GET  /patterns               pattern names the server can build
  POST /pattern                {"name": "levin", "diameter_mm": 27.8}  show a pattern
  GET  /pattern.png            the image the panel is showing right now
  GET  /last.jpg               preview of the last frame the camera took
  POST /liveview               {"on": true}  start or stop the camera's live view
  GET  /video_feed             MJPEG stream of the live view while it is on
  GET  /camera                 gphoto2 --summary
  GET  /camera/config          gphoto2 --list-all-config
  POST /camera/config          {"iso": "100", "shutterspeed": "1/30"}
  GET  /camera/choices         current value and choices for iso, shutterspeed, aperture
  POST /preview                one frame of the current pattern into captures/preview, not a session
  POST /capture                {"label": "x"}  one frame of the current pattern into a session
  POST /sequence               {"patterns": [...] or "sequence": "pair", "label": "700mm",
                                "settle": 0.3, "diameter_mm": 27.8}  starts the job
  GET  /sequence/<session>     manifest so far, with "done"
  GET  /files/<session>/<name> download a captured file

Requires: flask, pillow, numpy, rawpy, pyserial and the gphoto2 command line tool
"""
import argparse
import io
import json
import threading
import time
from datetime import datetime

from flask import Flask, Response, jsonify, request, send_file, send_from_directory

import config as cfg
import patterns
from camera import CameraError, open_camera
from display import open_display
from liveview import open_liveview
from preview import make_preview

app = Flask(__name__)
lock = threading.Lock()
state = {
    "display": None, "camera": None, "live": None, "live_wanted": False,
    "pattern": None, "diameter_mm": None, "shown_at": None,
    "last_preview": None, "last_file": None, "capture_count": 0,
    "job": {"running": False, "session": None, "index": 0, "total": 0, "error": None},
}
manifests = {}


def live_pause():
    """stop the live view stream so the camera is free for a still; returns whether it was on"""
    was = state["live"].running
    if was:
        state["live"].stop()
    return was


def live_resume(was):
    if was and state["live_wanted"]:
        try:
            state["live"].start()
        except Exception as e:
            print(f"live view did not restart: {e}")


def show(name, diameter_mm=None):
    img = patterns.make(name, diameter_mm)
    t = state["display"].show(img)
    state.update(pattern=name, diameter_mm=diameter_mm or cfg.PUPIL_MM, shown_at=t)
    return t


def session_dir(label):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    d = cfg.SESSIONS / f"{stamp}_{label}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def do_capture(stem, keep_live_paused=False):
    """fire the camera, write the preview JPEG beside the frame, return the files"""
    was = live_pause()
    try:
        files = state["camera"].capture(stem)
    finally:
        if not keep_live_paused:
            live_resume(was)
    primary = files[0]
    jpeg = next((f for f in files if f.suffix.lower() in (".jpg", ".jpeg")), primary)
    preview = stem.parent / f"{stem.name}_preview.jpg"
    try:
        make_preview(jpeg, preview)
        state["last_preview"] = preview
    except Exception as e:
        print(f"preview of {primary.name} failed: {e}")
    state["last_file"] = primary
    state["capture_count"] += 1
    return files


def run_sequence(names, d, settle, diameter_mm):
    """show, settle, capture for each name; the timing goes in the manifest"""
    job = state["job"]
    manifest = manifests[d.name]
    t0 = time.monotonic()
    with lock:
        was_live = live_pause()      # one pause for the whole sequence keeps the frame spacing tight
        try:
            for i, name in enumerate(names):
                job["index"] = i
                t_shown = show(name, diameter_mm)
                time.sleep(settle)
                t_fire = time.monotonic()
                stem = d / f"{i:02d}_{name}"
                files = do_capture(stem, keep_live_paused=True)
                t_done = time.monotonic()
                patterns.make(name, diameter_mm).save(d / f"{i:02d}_{name}_panel.png")
                manifest["frames"].append({
                    "index": i, "pattern": name, "file": files[0].name,
                    "files": [f.name for f in files],
                    "shown_s": round(t_shown - t0, 4), "fired_s": round(t_fire - t0, 4),
                    "downloaded_s": round(t_done - t0, 4),
                })
                (d / "manifest.json").write_text(json.dumps(manifest, indent=2))
        except Exception as e:
            job["error"] = str(e)
            manifest["error"] = str(e)
        finally:
            manifest["done"] = True
            job["running"] = False
            (d / "manifest.json").write_text(json.dumps(manifest, indent=2))
            live_resume(was_live)


def start_sequence(names, label, settle, diameter_mm):
    job = state["job"]
    if job["running"]:
        raise RuntimeError(f"sequence {job['session']} still running")
    d = session_dir(label)
    manifests[d.name] = {
        "label": label, "session": d.name, "started": datetime.now().isoformat(timespec="seconds"),
        "display": state["display"].name, "camera": state["camera"].name,
        "diameter_mm": diameter_mm or cfg.PUPIL_MM, "pitch_mm": cfg.PANEL_PITCH_MM,
        "invert": cfg.PANEL_INVERT, "settle_s": settle, "patterns": names,
        "frames": [], "done": False, "error": None,
    }
    job.update(running=True, session=d.name, index=0, total=len(names), error=None)
    threading.Thread(target=run_sequence, args=(names, d, settle, diameter_mm), daemon=True).start()
    return d.name


@app.route("/status")
def status():
    return jsonify({
        "display": state["display"].name, "camera": state["camera"].name,
        "pattern": state["pattern"], "diameter_mm": state["diameter_mm"],
        "panel": [cfg.PANEL_W, cfg.PANEL_H], "pitch_mm": cfg.PANEL_PITCH_MM,
        "pupil_mm": cfg.PUPIL_MM, "pupil_px": round(patterns.pupil_px(), 1), "invert": cfg.PANEL_INVERT,
        "sequences": cfg.SEQUENCES,
        "capture_count": state["capture_count"],
        "last_file": state["last_file"].name if state["last_file"] else None,
        "liveview": state["live"].running, "liveview_wanted": state["live_wanted"],
        "job": state["job"],
    })


@app.route("/liveview", methods=["POST"])
def liveview():
    data = request.get_json(force=True, silent=True) or {}
    on = bool(data.get("on", True))
    state["live_wanted"] = on
    if state["job"]["running"]:
        return jsonify({"liveview": state["live"].running, "note": "starts after the sequence"})
    with lock:
        try:
            if on:
                state["live"].start()
            else:
                state["live"].stop()
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"liveview": state["live"].running})


@app.route("/video_feed")
def video_feed():
    if not state["live"].running:
        return jsonify({"error": "live view is off; POST /liveview {\"on\": true}"}), 409

    def gen():
        for jpeg in state["live"].frames():
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"

    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/patterns")
def list_patterns():
    return jsonify(patterns.names())


@app.route("/pattern", methods=["POST"])
def set_pattern():
    data = request.get_json(force=True, silent=True) or {}
    name = data.get("name")
    if not name:
        return jsonify({"error": "name required"}), 400
    with lock:
        try:
            t = show(name, data.get("diameter_mm"))
        except (KeyError, FileNotFoundError, ValueError, OSError) as e:
            return jsonify({"error": e.args[0] if isinstance(e, KeyError) else str(e)}), 400
    return jsonify({"pattern": name, "shown_at": t})


@app.route("/pattern.png")
def pattern_png():
    img = state["display"].last
    if img is None:
        return jsonify({"error": "nothing shown yet"}), 404
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(buf.getvalue(), mimetype="image/png", headers={"Cache-Control": "no-store"})


@app.route("/last.jpg")
def last_jpg():
    p = state["last_preview"]
    if p is None or not p.exists():
        return jsonify({"error": "no capture yet"}), 404
    return send_file(p, mimetype="image/jpeg", max_age=0)


@app.route("/camera")
def camera_summary():
    with lock:
        return jsonify(state["camera"].describe())


@app.route("/camera/config", methods=["GET"])
def camera_config():
    cam = state["camera"]
    if not hasattr(cam, "list_config"):
        return jsonify({"config": "not a gphoto camera"})
    with lock:
        try:
            return jsonify({"config": cam.list_config()})
        except CameraError as e:
            return jsonify({"error": str(e)}), 500


@app.route("/camera/config", methods=["POST"])
def set_camera_config():
    data = request.get_json(force=True, silent=True) or {}
    with lock:
        try:
            applied = state["camera"].configure({k: str(v) for k, v in data.items()})
        except CameraError as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"applied": applied})


@app.route("/camera/choices")
def camera_choices():
    with lock:
        try:
            return jsonify(state["camera"].choices())
        except CameraError as e:
            return jsonify({"error": str(e)}), 500


@app.route("/preview", methods=["POST"])
def preview():
    with lock:
        if state["pattern"] is None:
            return jsonify({"error": "show a pattern first"}), 400
        d = cfg.SESSIONS / "preview"
        d.mkdir(parents=True, exist_ok=True)
        stem = d / f"{datetime.now().strftime('%H%M%S')}_{state['pattern']}"
        try:
            files = do_capture(stem)
        except CameraError as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"session": "preview", "file": files[0].name, "pattern": state["pattern"]})


@app.route("/capture", methods=["POST"])
def capture():
    data = request.get_json(force=True, silent=True) or {}
    label = data.get("label", "frame")
    with lock:
        if state["pattern"] is None:
            return jsonify({"error": "show a pattern first"}), 400
        d = session_dir(label)
        try:
            files = do_capture(d / f"00_{state['pattern']}")
        except CameraError as e:
            return jsonify({"error": str(e)}), 500
        patterns.make(state["pattern"], state["diameter_mm"]).save(d / f"00_{state['pattern']}_panel.png")
    return jsonify({"session": d.name, "file": files[0].name, "files": [f.name for f in files],
                    "pattern": state["pattern"]})


@app.route("/sequence", methods=["POST"])
def sequence():
    data = request.get_json(force=True, silent=True) or {}
    names = data.get("patterns") or cfg.SEQUENCES.get(data.get("sequence", ""))
    if not names:
        return jsonify({"error": f"give patterns or one of {list(cfg.SEQUENCES)}"}), 400
    for n in names:
        try:
            patterns.build(n)
        except (KeyError, FileNotFoundError, ValueError, OSError) as e:
            return jsonify({"error": e.args[0] if isinstance(e, KeyError) else str(e)}), 400
    label = data.get("label", "seq")
    settle = float(data.get("settle", cfg.SETTLE_S))
    try:
        session = start_sequence(names, label, settle, data.get("diameter_mm"))
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify({"session": session, "total": len(names)})


@app.route("/sequence/<session>")
def sequence_status(session):
    m = manifests.get(session)
    if m is None:
        p = cfg.SESSIONS / session / "manifest.json"
        if not p.exists():
            return jsonify({"error": "unknown session"}), 404
        m = json.loads(p.read_text())
    return jsonify(m)


@app.route("/files/<session>/<name>")
def files(session, name):
    return send_from_directory(cfg.SESSIONS / session, name, as_attachment=True)


def main():
    ap = argparse.ArgumentParser(description="LCD aperture and DSLR server")
    ap.add_argument("--display", choices=["arduino", "st7735", "window", "null"], default="arduino")
    ap.add_argument("--camera", choices=["gphoto", "dummy"], default="gphoto")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--pattern", default="open", help="pattern to show at start")
    args = ap.parse_args()

    state["display"] = open_display(args.display)
    state["camera"] = open_camera(args.camera, state["display"])
    state["live"] = open_liveview(args.camera, state["display"])
    show(args.pattern)
    print(f"display={args.display} camera={args.camera} pupil {cfg.PUPIL_MM:.1f} mm = {patterns.pupil_px():.1f} px")
    app.run(host="0.0.0.0", port=args.port, threaded=True)


if __name__ == "__main__":
    main()

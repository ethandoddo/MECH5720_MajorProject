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
  POST /pattern                {"name": "levin", "diameter_mm": 27.8}  show a pattern; "image_scale": 0.71
                               sizes a PNG or GIF against the pupil, 1 by default; "rotation_deg": 45
                               turns any pattern anticlockwise; /play and /sequence take both too
  POST /play                   {"name": "walk.gif", "speed": 2.0}  loop a GIF on the panel at its own
                               frame delays divided by speed; the same GIF again changes the speed;
                               {"stop": true} stops it. A pattern, capture or sequence stops it too
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
                                "settle": 0.3, "diameter_mm": 27.8}  starts the job; a GIF in
                                the list becomes one frame per GIF frame
  GET  /sequence/<session>     manifest so far, with "done"
  GET  /files/<session>/<name> download a captured file

Requires: flask, pillow, numpy, rawpy, pyserial and the gphoto2 command line tool
"""
import argparse
import io
import math
import json
import threading
import time
from contextlib import contextmanager
from datetime import datetime

from flask import Flask, Response, jsonify, request, send_file, send_from_directory

import config as cfg
import patterns
from camera import CameraError, add_dngs, open_camera
from display import open_display
from liveview import open_liveview
from preview import make_preview

app = Flask(__name__)
lock = threading.Lock()
state = {
    "display": None, "camera": None, "live": None, "live_wanted": False,
    "pattern": None, "diameter_mm": None, "image_scale": 1.0, "rotation_deg": 0.0, "shown_at": None,
    "last_preview": None, "last_file": None, "capture_count": 0,
    "job": {"running": False, "session": None, "index": 0, "total": 0, "error": None},
}
manifests = {}
play_lock = threading.Lock()        # orders starting and stopping playback; never take it while holding lock
play = {"thread": None, "stop": None, "name": None, "diameter_mm": None, "image_scale": 1.0, "rotation_deg": 0.0, "speed": 1.0, "error": None}


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


def live_ended(reason):
    """the stream ended on its own: a timeout in liveview.py, or gphoto2 lost the camera. Forget
    that it was wanted so the window's checkbox clears and no capture restarts it"""
    state["live_wanted"] = False
    print(f"live view off: {reason}")


@contextmanager
def camera_free():
    """the lock with live view paused, for any other gphoto2 call; the live view process holds
    the USB device, so a settings change while it runs fails with 'Could not claim the USB device'"""
    with lock:
        was = live_pause()
        try:
            yield
        finally:
            live_resume(was)


def show(name, diameter_mm=None, img=None, image_scale=1.0, rotation_deg=0.0):
    if img is None:
        img = patterns.make(name, diameter_mm, image_scale, rotation_deg)
    t = state["display"].show(img)
    state.update(pattern=name, diameter_mm=diameter_mm or cfg.PUPIL_MM, image_scale=image_scale,
                 rotation_deg=rotation_deg, shown_at=t)
    return t


def image_scale_of(data):
    """the "image_scale" of a request, 1 when absent; ValueError unless it is a number above 0"""
    if data.get("image_scale") is None:
        return 1.0
    try:
        v = float(data["image_scale"])
    except (TypeError, ValueError):
        v = 0.0
    if not v > 0:
        raise ValueError("image_scale must be a number above 0")
    return v


def rotation_of(data):
    """the "rotation_deg" of a request in degrees, 0 when absent; ValueError unless it is a finite number"""
    if data.get("rotation_deg") is None:
        return 0.0
    try:
        v = float(data["rotation_deg"])
    except (TypeError, ValueError):
        v = float("nan")
    if not math.isfinite(v):
        raise ValueError("rotation_deg must be a number")
    return v


def playing():
    return play["thread"] is not None and play["thread"].is_alive()


def play_loop(names, images, delays_ms, diameter_mm, image_scale, rotation_deg, stop):
    """loop the frames until stop is set; lock is held only while a frame goes to the panel,
    so a capture waits at most one frame and the panel holds still while the shutter is open"""
    i = 0
    try:
        while not stop.is_set():
            t0 = time.monotonic()
            with lock:
                if stop.is_set():
                    break
                show(names[i], diameter_mm, images[i], image_scale, rotation_deg)
            stop.wait(max(0.0, delays_ms[i] / 1000 / play["speed"] - (time.monotonic() - t0)))
            i = (i + 1) % len(names)
    except Exception as e:
        play["error"] = str(e)
        print(f"GIF playback stopped: {e}")


def stop_play():
    """stop GIF playback and wait for its thread; call with play_lock held and lock not held"""
    if play["thread"] is not None:
        play["stop"].set()
        play["thread"].join()
        play["thread"] = None


def halt_play():
    with play_lock:
        stop_play()


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


def run_sequence(names, d, settle, diameter_mm, image_scale, rotation_deg):
    """show, settle, capture for each name; the timing goes in the manifest"""
    job = state["job"]
    manifest = manifests[d.name]
    t0 = time.monotonic()
    with lock:
        was_live = live_pause()      # one pause for the whole sequence keeps the frame spacing tight
        try:
            for i, name in enumerate(names):
                job["index"] = i
                tag = patterns.tag(name)
                t_shown = show(name, diameter_mm, image_scale=image_scale, rotation_deg=rotation_deg)
                time.sleep(settle)
                t_fire = time.monotonic()
                stem = d / f"{i:02d}_{tag}"
                files = do_capture(stem, keep_live_paused=True)
                t_done = time.monotonic()
                state["display"].last.save(d / f"{i:02d}_{tag}_panel.png")
                manifest["frames"].append({
                    "index": i, "pattern": name, "tag": tag, "file": files[0].name,
                    "files": [f.name for f in files],
                    "shown_s": round(t_shown - t0, 4), "fired_s": round(t_fire - t0, 4),
                    "downloaded_s": round(t_done - t0, 4),
                })
                (d / "manifest.json").write_text(json.dumps(manifest, indent=2))
        except Exception as e:
            job["error"] = str(e)
            manifest["error"] = str(e)
        finally:
            add_session_dngs(manifest, d)
            manifest["done"] = True
            job["running"] = False
            (d / "manifest.json").write_text(json.dumps(manifest, indent=2))
            live_resume(was_live)


def add_session_dngs(manifest, d):
    """a DNG beside every CR2 of the session, after the last frame so converting never sits
    between a pattern and its shutter; a failure is noted and the CR2s stay as they are"""
    try:
        for fr in manifest["frames"]:
            fr["files"] = [f.name for f in add_dngs([d / n for n in fr["files"]])]
    except Exception as e:
        manifest["dng_error"] = str(e)
        print(f"no DNG for {d.name}: {e}")


def start_sequence(names, label, settle, diameter_mm, image_scale=1.0, rotation_deg=0.0):
    job = state["job"]
    if job["running"]:
        raise RuntimeError(f"sequence {job['session']} still running")
    d = session_dir(label)
    manifests[d.name] = {
        "label": label, "session": d.name, "started": datetime.now().isoformat(timespec="seconds"),
        "display": state["display"].name, "camera": state["camera"].name,
        "diameter_mm": diameter_mm or cfg.PUPIL_MM, "image_scale": image_scale, "rotation_deg": rotation_deg, "pitch_mm": cfg.PANEL_PITCH_MM,
        "invert": cfg.PANEL_INVERT, "settle_s": settle, "patterns": names,
        "frames": [], "done": False, "error": None,
    }
    job.update(running=True, session=d.name, index=0, total=len(names), error=None)
    threading.Thread(target=run_sequence, args=(names, d, settle, diameter_mm, image_scale, rotation_deg),
                     daemon=True).start()
    return d.name


@app.route("/status")
def status():
    return jsonify({
        "display": state["display"].name, "camera": state["camera"].name,
        "pattern": state["pattern"], "diameter_mm": state["diameter_mm"], "image_scale": state["image_scale"],
        "rotation_deg": state["rotation_deg"],
        "panel": [cfg.PANEL_W, cfg.PANEL_H], "pitch_mm": cfg.PANEL_PITCH_MM,
        "pupil_mm": cfg.PUPIL_MM, "pupil_px": round(patterns.pupil_px(), 1), "invert": cfg.PANEL_INVERT,
        "sequences": cfg.SEQUENCES,
        "playing": play["name"] if playing() else None, "play_speed": play["speed"], "play_error": play["error"],
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
    halt_play()
    with lock:
        try:
            t = show(name, data.get("diameter_mm"), image_scale=image_scale_of(data), rotation_deg=rotation_of(data))
        except (KeyError, FileNotFoundError, ValueError, OSError) as e:
            return jsonify({"error": e.args[0] if isinstance(e, KeyError) else str(e)}), 400
    return jsonify({"pattern": name, "shown_at": t})


@app.route("/play", methods=["POST"])
def play_gif():
    data = request.get_json(force=True, silent=True) or {}
    with play_lock:
        if data.get("stop"):
            stop_play()
            return jsonify({"playing": None})
        name = data.get("name")
        if not name or not patterns.split_frame(name)[0].lower().endswith(".gif"):
            return jsonify({"error": "name must be a path to a GIF"}), 400
        try:
            speed = float(data.get("speed", 1.0))
        except (TypeError, ValueError):
            speed = 0.0
        if not speed > 0:
            return jsonify({"error": "speed must be above 0"}), 400
        if state["job"]["running"]:
            return jsonify({"error": f"sequence {state['job']['session']} still running"}), 409
        base = patterns.split_frame(name)[0]
        diameter_mm = data.get("diameter_mm")
        try:
            image_scale, rotation_deg = image_scale_of(data), rotation_of(data)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        if playing() and (play["name"], play["diameter_mm"], play["image_scale"], play["rotation_deg"]) == \
                (base, diameter_mm, image_scale, rotation_deg):
            play["speed"] = speed
            return jsonify({"playing": base, "speed": speed})
        stop_play()
        try:
            images, delays = patterns.gif_play(base, diameter_mm, image_scale, rotation_deg)
        except (FileNotFoundError, ValueError, OSError) as e:
            return jsonify({"error": str(e)}), 400
        names = [f"{base}#{i}" for i in range(len(images))]
        stop = threading.Event()
        play.update(name=base, diameter_mm=diameter_mm, image_scale=image_scale, rotation_deg=rotation_deg, speed=speed,
                    error=None, stop=stop,
                    thread=threading.Thread(target=play_loop, daemon=True,
                                            args=(names, images, delays, diameter_mm, image_scale, rotation_deg, stop)))
        play["thread"].start()
    return jsonify({"playing": base, "speed": speed, "frames": len(images), "delays_ms": delays})


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
    with camera_free():
        return jsonify(state["camera"].describe())


@app.route("/camera/config", methods=["GET"])
def camera_config():
    cam = state["camera"]
    if not hasattr(cam, "list_config"):
        return jsonify({"config": "not a gphoto camera"})
    with camera_free():
        try:
            return jsonify({"config": cam.list_config()})
        except CameraError as e:
            return jsonify({"error": str(e)}), 500


@app.route("/camera/config", methods=["POST"])
def set_camera_config():
    data = request.get_json(force=True, silent=True) or {}
    with camera_free():
        try:
            applied = state["camera"].configure({k: str(v) for k, v in data.items()})
        except CameraError as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"applied": applied})


@app.route("/camera/choices")
def camera_choices():
    with camera_free():
        try:
            return jsonify(state["camera"].choices())
        except CameraError as e:
            return jsonify({"error": str(e)}), 500


@app.route("/preview", methods=["POST"])
def preview():
    halt_play()
    with lock:
        if state["pattern"] is None:
            return jsonify({"error": "show a pattern first"}), 400
        d = cfg.SESSIONS / "preview"
        d.mkdir(parents=True, exist_ok=True)
        stem = d / f"{datetime.now().strftime('%H%M%S')}_{patterns.tag(state['pattern'])}"
        try:
            files = do_capture(stem)
        except CameraError as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"session": "preview", "file": files[0].name, "pattern": state["pattern"]})


@app.route("/capture", methods=["POST"])
def capture():
    data = request.get_json(force=True, silent=True) or {}
    label = data.get("label", "frame")
    halt_play()
    with lock:
        if state["pattern"] is None:
            return jsonify({"error": "show a pattern first"}), 400
        tag = patterns.tag(state["pattern"])
        d = session_dir(label)
        try:
            files = do_capture(d / f"00_{tag}")
        except CameraError as e:
            return jsonify({"error": str(e)}), 500
        state["display"].last.save(d / f"00_{tag}_panel.png")
        dng_error = None
        try:
            files = add_dngs(files)
        except Exception as e:
            dng_error = str(e)
            print(f"no DNG for {d.name}: {e}")
    return jsonify({"session": d.name, "file": files[0].name, "files": [f.name for f in files],
                    "pattern": state["pattern"], "tag": tag, "dng_error": dng_error})


@app.route("/sequence", methods=["POST"])
def sequence():
    data = request.get_json(force=True, silent=True) or {}
    requested = data.get("patterns") or cfg.SEQUENCES.get(data.get("sequence", ""))
    if not requested:
        return jsonify({"error": f"give patterns or one of {list(cfg.SEQUENCES)}"}), 400
    names = []
    for n in requested:
        try:
            patterns.build(n)
            names += patterns.expand(n)
        except (KeyError, FileNotFoundError, ValueError, OSError) as e:
            return jsonify({"error": e.args[0] if isinstance(e, KeyError) else str(e)}), 400
    label = data.get("label", "seq")
    settle = float(data.get("settle", cfg.SETTLE_S))
    try:
        image_scale, rotation_deg = image_scale_of(data), rotation_of(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    with play_lock:
        stop_play()
        try:
            session = start_sequence(names, label, settle, data.get("diameter_mm"), image_scale, rotation_deg)
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
    state["live"] = open_liveview(args.camera, state["display"], on_end=live_ended)
    show(args.pattern)
    print(f"display={args.display} camera={args.camera} pupil {cfg.PUPIL_MM:.1f} mm = {patterns.pupil_px():.1f} px")
    try:
        app.run(host="0.0.0.0", port=args.port, threaded=True)
    finally:
        state["live"].stop()        # Ctrl-C ends the stream and brings the mirror down rather than leaving the camera in live view


if __name__ == "__main__":
    main()

"""Camera view and control window for the aperture rig. Run this on the laptop while
server.py is running there too. This is the main way to drive the rig.

Four windows: what the DSLR sees, what the panel is showing, the controls for patterns,
camera settings, single frames and sequences, and the experiments, one tab each for
depth, refocus, bokeh and the flutter shutter. With Live view on, the camera view
streams the EOS 60D's live view. Off, it shows the last frame the camera took. Live view
pauses around every capture because one process owns the USB link.

An experiment is a list of steps the server runs in order. A step with a prompt pauses
the job with the prompt on show, for a card swap or the lens cap, until Continue. A
flutter step plays a code on the panel during one photo on M.

PNG and GIF files come in through a file dialog. A GIF plays on the panel at a chosen
speed, and in an image sequence each GIF frame gets its own photo. The server opens the
files by path, so they have to be on the machine that runs it.

  python camview_capture.py --outdir captures                       # server on this laptop
  python camview_capture.py --host 192.168.1.100 --outdir captures  # server on another machine

Requires: opencv-python, requests, glfw, pyopengl, imgui-bundle, pillow, and zenity for the file dialog
  pip install -r requirements.txt
"""

import argparse
import json
import os
import re
import shutil
import threading
import time

import cv2
import numpy as np
import requests
from PIL import Image

import glfw
import OpenGL.GL as gl
from imgui_bundle import imgui
from imgui_bundle import portable_file_dialogs as pfd
from imgui_bundle.python_backends.glfw_backend import GlfwRenderer

import config as cfg
import flutter

status_message = "Ready"
status_color = (0.5, 0.7, 1.0, 1.0)
OK = (0.2, 0.8, 0.2, 1.0)
BUSY = (0.9, 0.6, 0.2, 1.0)
BAD = (0.9, 0.2, 0.2, 1.0)
SETTINGS = ("iso", "shutterspeed", "aperture")
FLUTTER_ORDER = ("reference", "impulse", "coded", "box", "leakage", "dark")     # target still, then moving, then the lens cap
FRAME_OVERHEAD_S = 2.5      # firing and downloading one 60D frame over USB 2, 2.2 to 2.6 s in the flutter_photo manifests
IMAGE_FILTERS = ["Images (.png .gif)", "*.png *.gif *.PNG *.GIF", "All files", "*"]
FIT_CIRCLE_PCT = 70.7       # a square image's corners just touch the round pupil
RESIZE_DELAY_S = 0.4        # redraw this long after Pupil mm, Image size or Rotation stops changing


def is_image_name(name):
    n = (name or "").lower()
    return n.endswith((".png", ".gif")) or ".gif#" in n


def set_status(msg, color=(0.5, 0.7, 1.0, 1.0)):
    global status_message, status_color
    status_message = msg
    status_color = color


# ---------------------------------------------------------------------------
# Server client
# ---------------------------------------------------------------------------

class Server:
    def __init__(self, base_url):
        self.base = base_url

    def get(self, path, timeout=5):
        r = requests.get(self.base + path, timeout=timeout)
        r.raise_for_status()
        return r

    def post(self, path, body, timeout=30):
        r = requests.post(self.base + path, json=body, timeout=timeout)
        if r.status_code != 200:
            try:
                raise RuntimeError(r.json().get("error", r.text))
            except ValueError:
                raise RuntimeError(r.text)
        return r.json()

    def status(self):
        return self.get("/status").json()

    def patterns(self):
        return self.get("/patterns").json()

    def show(self, name, diameter_mm=None, image_scale=1.0, rotation_deg=0.0):
        return self.post("/pattern", {"name": name, "diameter_mm": diameter_mm, "image_scale": image_scale,
                                      "rotation_deg": rotation_deg}, timeout=15)

    def play(self, name, speed, diameter_mm=None, image_scale=1.0, rotation_deg=0.0):
        return self.post("/play", {"name": name, "speed": speed, "diameter_mm": diameter_mm,
                                   "image_scale": image_scale, "rotation_deg": rotation_deg}, timeout=30)

    def stop_play(self):
        return self.post("/play", {"stop": True}, timeout=15)

    def choices(self):
        return self.get("/camera/choices", timeout=60).json()

    def configure(self, settings):
        return self.post("/camera/config", settings, timeout=60)

    def preview(self):
        return self.post("/preview", {}, timeout=120)

    def capture(self, label):
        return self.post("/capture", {"label": label}, timeout=120)

    def start_sequence(self, body):
        return self.post("/sequence", body, timeout=30)

    def go(self):
        return self.post("/sequence/go", {}, timeout=10)

    def stop_job(self):
        return self.post("/sequence/stop", {}, timeout=10)

    def sequence(self, session):
        return self.get(f"/sequence/{session}", timeout=10).json()

    def last_jpg(self):
        return self.get("/last.jpg", timeout=30).content

    def liveview(self, on):
        return self.post("/liveview", {"on": on}, timeout=30)

    def pattern_png(self):
        return self.get("/pattern.png", timeout=10).content

    def download(self, session, name, dest):
        with requests.get(f"{self.base}/files/{session}/{name}", stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                shutil.copyfileobj(r.raw, f)


class Poller(threading.Thread):
    """Polls /status twice a second and fetches the camera frame and panel image when they change."""

    def __init__(self, server):
        super().__init__(daemon=True)
        self.server = server
        self.lock = threading.Lock()
        self.status = None
        self.connected = False
        self.camera_frame = None
        self.camera_new = False
        self.panel_frame = None
        self.panel_new = False
        self._seen_count = -1
        self._seen_pattern = None
        self.running = True
        self.start()

    def run(self):
        while self.running:
            try:
                st = self.server.status()
                with self.lock:
                    self.status = st
                    self.connected = True
                if st["capture_count"] != self._seen_count and st["capture_count"] > 0:
                    data = np.frombuffer(self.server.last_jpg(), np.uint8)
                    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
                    if img is not None:
                        with self.lock:
                            self.camera_frame = np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
                            self.camera_new = True
                        self._seen_count = st["capture_count"]
                key = (st["pattern"], st["diameter_mm"], st.get("image_scale"), st.get("rotation_deg"))
                if key != self._seen_pattern and st["pattern"]:
                    data = np.frombuffer(self.server.pattern_png(), np.uint8)
                    img = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
                    if img is not None:
                        with self.lock:
                            self.panel_frame = np.ascontiguousarray(cv2.cvtColor(img, cv2.COLOR_GRAY2RGB))
                            self.panel_new = True
                        self._seen_pattern = key
            except Exception:
                with self.lock:
                    self.connected = False
            time.sleep(0.5)

    def take(self):
        with self.lock:
            out = (self.camera_frame, self.camera_new, self.panel_frame, self.panel_new, self.status, self.connected)
            self.camera_new = False
            self.panel_new = False
            return out

    def stop(self):
        self.running = False


class FrameReader(threading.Thread):
    """Reads the MJPEG live view from /video_feed, as the Lab 3 window read the Pi camera."""

    def __init__(self, stream_url):
        super().__init__(daemon=True)
        self.stream_url = stream_url
        self.frame = None
        self.new_frame = False
        self.lock = threading.Lock()
        self.running = True
        self.connected = False
        self.fps = 0.0
        self.start()

    def run(self):
        count, t0 = 0, time.time()
        while self.running:
            cap = cv2.VideoCapture(self.stream_url)
            if not cap.isOpened():
                self.connected = False
                time.sleep(1.0)
                continue
            self.connected = True
            while self.running:
                ok, frame = cap.read()
                if not ok:
                    self.connected = False
                    break
                with self.lock:
                    self.frame = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    self.new_frame = True
                count += 1
                now = time.time()
                if now - t0 >= 1.0:
                    self.fps = count / (now - t0)
                    count, t0 = 0, now
            cap.release()
            time.sleep(0.5)

    def get_frame(self):
        with self.lock:
            new = self.new_frame
            self.new_frame = False
            return self.frame, new

    def stop(self):
        self.running = False


# ---------------------------------------------------------------------------
# GL helpers and theme
# ---------------------------------------------------------------------------

def make_texture(nearest=False):
    tex = gl.glGenTextures(1)
    gl.glBindTexture(gl.GL_TEXTURE_2D, tex)
    f = gl.GL_NEAREST if nearest else gl.GL_LINEAR
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, f)
    gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, f)
    gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGB, 1, 1, 0, gl.GL_RGB, gl.GL_UNSIGNED_BYTE, b"\x00\x00\x00")
    return tex


def upload_texture(texture_id, rgb_frame):
    h, w, _ = rgb_frame.shape
    gl.glBindTexture(gl.GL_TEXTURE_2D, texture_id)
    gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
    gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGB, w, h, 0, gl.GL_RGB, gl.GL_UNSIGNED_BYTE, rgb_frame)
    return w, h


def draw_fitted(texture_id, tex_w, tex_h):
    avail = imgui.get_content_region_avail()
    scale = min(avail.x / tex_w, avail.y / tex_h)
    draw_w, draw_h = tex_w * scale, tex_h * scale
    pos = imgui.get_cursor_pos()
    imgui.set_cursor_pos((pos.x + (avail.x - draw_w) / 2, pos.y + (avail.y - draw_h) / 2))
    imgui.image(imgui.ImTextureRef(texture_id), imgui.ImVec2(draw_w, draw_h))


def centred_text(text):
    avail = imgui.get_content_region_avail()
    imgui.set_cursor_pos((max(0, avail.x / 2 - 4 * len(text)), avail.y / 2 - 10))
    imgui.text(text)


def apply_theme():
    style = imgui.get_style()
    style.window_rounding = 10.0
    style.frame_rounding = 6.0
    style.grab_rounding = 6.0
    style.scrollbar_rounding = 6.0
    style.window_border_size = 1.0
    theme_colors = {
        imgui.Col_.text: (0.90, 0.90, 0.95, 1.0),
        imgui.Col_.text_disabled: (0.50, 0.50, 0.55, 1.0),
        imgui.Col_.window_bg: (0.08, 0.08, 0.11, 0.95),
        imgui.Col_.child_bg: (0.08, 0.08, 0.11, 1.0),
        imgui.Col_.popup_bg: (0.12, 0.12, 0.16, 0.98),
        imgui.Col_.border: (0.25, 0.25, 0.35, 0.6),
        imgui.Col_.border_shadow: (0.00, 0.00, 0.00, 0.0),
        imgui.Col_.frame_bg: (0.14, 0.14, 0.20, 1.0),
        imgui.Col_.frame_bg_hovered: (0.20, 0.20, 0.28, 1.0),
        imgui.Col_.frame_bg_active: (0.28, 0.28, 0.38, 1.0),
        imgui.Col_.title_bg: (0.12, 0.12, 0.16, 1.0),
        imgui.Col_.title_bg_active: (0.18, 0.18, 0.24, 1.0),
        imgui.Col_.title_bg_collapsed: (0.08, 0.08, 0.11, 0.50),
        imgui.Col_.menu_bar_bg: (0.14, 0.14, 0.18, 1.0),
        imgui.Col_.scrollbar_bg: (0.10, 0.10, 0.14, 1.0),
        imgui.Col_.scrollbar_grab: (0.25, 0.25, 0.35, 1.0),
        imgui.Col_.scrollbar_grab_hovered: (0.35, 0.35, 0.45, 1.0),
        imgui.Col_.scrollbar_grab_active: (0.45, 0.45, 0.55, 1.0),
        imgui.Col_.check_mark: (0.50, 0.55, 0.90, 1.0),
        imgui.Col_.slider_grab: (0.40, 0.45, 0.80, 1.0),
        imgui.Col_.slider_grab_active: (0.50, 0.55, 0.90, 1.0),
        imgui.Col_.button: (0.20, 0.25, 0.45, 1.0),
        imgui.Col_.button_hovered: (0.28, 0.35, 0.60, 1.0),
        imgui.Col_.button_active: (0.35, 0.45, 0.75, 1.0),
        imgui.Col_.header: (0.20, 0.25, 0.45, 1.0),
        imgui.Col_.header_hovered: (0.28, 0.35, 0.60, 1.0),
        imgui.Col_.header_active: (0.35, 0.45, 0.75, 1.0),
        imgui.Col_.plot_histogram: (0.40, 0.45, 0.80, 1.0),
    }
    for col_enum, col_val in theme_colors.items():
        style.set_color_(col_enum, imgui.ImVec4(*col_val))


# ---------------------------------------------------------------------------
# Actions that talk to the server, each on its own thread
# ---------------------------------------------------------------------------

def in_thread(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()


def download_sequence(server, session, outdir, label):
    """pull every frame of a finished sequence into outdir and write the manifest beside them"""
    try:
        set_status(f"Downloading {session}...", BUSY)
        manifest = server.sequence(session)
        os.makedirs(outdir, exist_ok=True)
        for fr in manifest["frames"]:
            tag = fr.get("tag", fr["pattern"])
            for name in fr.get("files", [fr["file"]]):
                ext = os.path.splitext(name)[1]
                dest = os.path.join(outdir, f"{label}_{fr['index']:02d}_{tag}{ext}")
                server.download(session, name, dest)
            fr["local"] = os.path.join(outdir, f"{label}_{fr['index']:02d}_{tag}")
        with open(os.path.join(outdir, f"{label}_manifest.json"), "w") as f:
            json.dump(manifest, f, indent=2)
        if manifest.get("error"):
            set_status(f"Sequence stopped: {manifest['error']}", BAD)
        elif manifest.get("dng_error"):
            set_status(f"Saved {len(manifest['frames'])} frames to {outdir}, but no DNG: {manifest['dng_error']}", BUSY)
        else:
            set_status(f"Saved {len(manifest['frames'])} frames to {outdir}", OK)
    except Exception as e:
        set_status(f"Download error: {e}", BAD)


def download_single(server, info, outdir, label):
    try:
        os.makedirs(outdir, exist_ok=True)
        tag = info.get("tag", info["pattern"])
        for name in info.get("files", [info["file"]]):
            ext = os.path.splitext(name)[1]
            server.download(info["session"], name, os.path.join(outdir, f"{label}_{tag}{ext}"))
        if info.get("dng_error"):
            set_status(f"Saved {label}_{tag} to {outdir}, but no DNG: {info['dng_error']}", BUSY)
        else:
            set_status(f"Saved {label}_{tag} to {outdir}", OK)
    except Exception as e:
        set_status(f"Download error: {e}", BAD)


def frame_count(path):
    """photos a sequence entry will take: one per GIF frame, one for anything else, 0 if unreadable"""
    if not path.lower().endswith(".gif"):
        return 1
    try:
        with Image.open(path) as img:
            return getattr(img, "n_frames", 1)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--outdir", default="captures", help="where downloaded frames go")
    parser.add_argument("--exit-after", type=float, default=0, help="seconds, for a smoke test")
    parser.add_argument("--screenshot", help="PNG to write just before --exit-after fires")
    args = parser.parse_args()

    server = Server(f"http://{args.host}:{args.port}")

    ui = {
        "patterns": [], "pattern_idx": 0, "diameter": 0.0, "png_path": "",
        "choices": {}, "choice_idx": {}, "label": "frame", "outdir": args.outdir,
        "sequences": {}, "seq_idx": 0, "settle": 0.3, "custom": "open levin nayar open",
        "seq_session": None, "seq_collected": True, "seq_label": "", "seq_outdir": args.outdir,
        "speed": 1.0, "image_pct": 100.0, "rotation": 0.0, "resize_at": 0.0, "images": [], "image_counts": [], "image_sel": -1,
        "dialog": None, "dialog_target": None, "dialog_dir": os.path.expanduser("~"),
        # the Experiments window
        "repeats": 1, "distance": 1000, "bokeh_path": "", "depth_a": cfg.PAIR[0], "depth_b": cfg.PAIR[1],
        "fl_mode": 0, "fl_designed": flutter.design(), "fl_custom": "", "fl_chop": cfg.FLUTTER_CHOP_MS,
        "fl_lead": cfg.FLUTTER_LEAD_MS, "fl_tail": cfg.FLUTTER_TAIL_MS, "fl_method": 0,
        "fl_blur": 100, "fl_impulse": cfg.IMPULSE_SHUTTER,
        "fl_take": {"coded": True, "box": True, "leakage": True, "impulse": True, "reference": True, "dark": True},
        "fl_photo_mode": 0, "fl_photo": {k: "" for k in SETTINGS}, "fl_name": "",
        "popup_session": None, "popup_seen": None, "popup_text": "",
    }

    def open_dialog(target):
        """target "single" fills the image field, "images" appends to the sequence list, "bokeh" the shape,
        "depth_a" and "depth_b" the depth pair"""
        if ui["dialog"] is not None:
            return
        try:
            opts = pfd.opt.multiselect if target == "images" else pfd.opt.none
            ui["dialog"] = pfd.open_file("Choose PNG or GIF", ui["dialog_dir"], IMAGE_FILTERS, opts)
            ui["dialog_target"] = target
        except Exception as e:
            set_status(f"No file dialog: {e}. sudo apt install zenity", BAD)

    def add_images(paths):
        for p in paths:
            ui["images"].append(p)
            ui["image_counts"].append(frame_count(p))

    def load_lists():
        try:
            ui["patterns"] = server.patterns()
            st = server.status()
            ui["sequences"] = st.get("sequences", {})
            if st.get("pattern") in ui["patterns"]:
                ui["pattern_idx"] = ui["patterns"].index(st["pattern"])
            set_status("Connected to server", OK)
        except Exception as e:
            set_status(f"Could not reach the server: {e}", BAD)

    def load_choices():
        """read the camera's settings; True when that worked"""
        try:
            ch = server.choices()
            ui["choices"] = ch
            for k, v in ch.items():
                opts = v.get("choices") or []
                ui["choice_idx"][k] = opts.index(v["current"]) if v.get("current") in opts else 0
            return True
        except Exception as e:
            set_status(f"Camera settings unavailable: {e}", BAD)
            return False

    load_lists()
    in_thread(load_choices)

    if not glfw.init():
        print("Error: Could not initialize GLFW")
        return
    glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 2)
    glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 1)
    window = glfw.create_window(1600, 760, "Aperture Rig Control", None, None)
    if not window:
        glfw.terminate()
        print("Error: Could not create GLFW window")
        return
    glfw.make_context_current(window)
    glfw.swap_interval(1)

    imgui.create_context()
    impl = GlfwRenderer(window)
    apply_theme()

    cam_tex = make_texture()
    live_tex = make_texture()
    panel_tex = make_texture(nearest=True)
    cam_size = None
    live_size = None
    panel_size = None
    reader = None

    poller = Poller(server)
    t_start = time.time()

    def busy():
        st = poller.status
        return bool(st and st["job"]["running"])

    # ---- the Experiments window: each tab turns its settings into a list of steps for the server

    def go():
        try:
            server.go()
            set_status("Carrying on", OK)
        except Exception as e:
            set_status(f"Continue error: {e}", BAD)

    def stop_job():
        try:
            server.stop_job()
            set_status("Stopping after this step", BUSY)
        except Exception as e:
            set_status(f"Stop error: {e}", BAD)

    def start_steps(steps, label, experiment, popup=False):
        """run the steps as a sequence with the settle, pupil, image size and rotation from Controls;
        the frames download to <outdir>/<experiment>/. With popup, each prompt shows as a pop-up"""
        body = {"label": label, "patterns": steps, "settle": ui["settle"], "image_scale": ui["image_pct"] / 100,
                "rotation_deg": ui["rotation"]}
        if ui["diameter"]:
            body["diameter_mm"] = ui["diameter"]
        try:
            info = server.start_sequence(body)
            ui["seq_session"] = info["session"]
            ui["seq_label"] = label
            ui["seq_outdir"] = os.path.join(ui["outdir"], experiment)
            ui["seq_collected"] = False
            ui["popup_session"] = info["session"] if popup else None
            set_status(f"Running {label}: {info['total']} steps...", BUSY)
        except Exception as e:
            set_status(f"Sequence error: {e}", BAD)

    def repeat(steps):
        return [dict(s) if isinstance(s, dict) else s for _ in range(ui["repeats"]) for s in steps]

    def card(name, what=None):
        """one frame through a hand-fitted card with the panel white, after a pause to fit it"""
        return {"pattern": "white", "tag": f"card_{name}", "prompt": f"Fit the {what or name} card in front of the panel"}

    def depth_tab():
        for key in ("depth_a", "depth_b"):
            changed, val = imgui.input_text(f"Pattern {key[-1].upper()}", ui[key])
            if changed:
                ui[key] = val
        if imgui.button("Browse A..."):
            open_dialog("depth_a")
        imgui.same_line()
        if imgui.button("Browse B..."):
            open_dialog("depth_b")
        a, b = ui["depth_a"].strip(), ui["depth_b"].strip()
        sa, sb = (os.path.splitext(os.path.basename(p))[0] for p in (a, b))
        d = ui["distance"]
        # mm so gates.py finds the distance; a pair other than Zhou's adds its names, so it never overwrites the Zhou files
        base = f"depth{d}mm"
        pair = "" if (a, b) == cfg.PAIR else f"_{sa}_{sb}"
        cards = {"zhou_a": "Zhou A", "zhou_b": "Zhou B"}
        imgui.begin_disabled(not (a and b))
        if imgui.button("PSF set"):
            in_thread(start_steps, repeat(["open", a, b, "levin", "black"]), f"{base}_psf{pair}", "depth")
        imgui.same_line()
        if imgui.button("Pair"):
            in_thread(start_steps, repeat(["open", a, b, "open"]), f"{base}_pair{pair}", "depth")
        imgui.same_line()
        if imgui.button("Singles"):
            in_thread(start_steps, repeat([a, a, b, b, "levin", "levin"]), f"{base}_single{pair}", "depth")
        imgui.same_line()
        if imgui.button("Card pair"):
            in_thread(start_steps, repeat([card("open"), card(sa, cards.get(a)), card(sb, cards.get(b)), card("open")]),
                      f"{base}_cardpair{pair}", "depth")
        imgui.end_disabled()
        imgui.text_wrapped(f"Pattern A and B: a mask name from masks/, or a PNG or GIF from Browse, sized by Image size "
                           f"in Controls. A pair other than zhou_a and zhou_b adds its names to the file names. "
                           f"PSF set: open, {sa}, {sb}, levin and black, for a point source at the distance above. "
                           f"Pair: open, {sa}, {sb}, open, for a textured target. "
                           f"Singles: each coded pattern twice, so one pattern gets the pair's exposure. "
                           f"Card pair: the same four frames through hand-fitted cards with the panel white. "
                           f"The job pauses before each card.")

    def refocus_tab():
        d = ui["distance"]
        n = cfg.SCAN_N
        f = cfg.REFOCUS_F_NUMBER
        ftag = f"f{f:g}".replace(".", "p")
        if imgui.button(f"Scan {n}x{n}"):
            in_thread(start_steps, repeat(["open"] + [f"scan{i}" for i in range(n * n)] + ["black", "open"]),
                      f"refocus{d}_scan{n}", "refocus")
        imgui.same_line()
        if imgui.button("Scan 5x5"):
            in_thread(start_steps, repeat(["open"] + [f"scan5_{i}" for i in range(25)] + ["black", "open"]),
                      f"refocus{d}_scan5", "refocus")
        imgui.same_line()
        if imgui.button(f"f/{f:g} frame"):
            in_thread(start_steps, repeat([{"pattern": "open", "diameter_mm": cfg.FOCAL_MM / f, "tag": ftag}]),
                      f"refocus{d}_{ftag}", "refocus")
        imgui.same_line()
        if imgui.button("Lens focus"):
            in_thread(start_steps, repeat([{"pattern": "open", "tag": "lensfocus",
                                            "prompt": f"Focus the lens on the {d} mm target, then refocus it after the frame"}]),
                      f"refocus{d}_lensfocus", "refocus")
        imgui.text_wrapped(f"Scan: open, every tile, black and open. The 5x5 scan takes 28 frames. "
                           f"f/{f:g} frame: one open disc {cfg.FOCAL_MM / f:.1f} mm wide, the depth of field the "
                           f"{n}x{n} refocus reaches with no scan. Lens focus: the in-focus reference for SSIM, "
                           f"after a pause to focus the lens by hand.")

    def bokeh_tab():
        changed, val = imgui.input_text("Shape", ui["bokeh_path"])
        if changed:
            ui["bokeh_path"] = val
        if imgui.button("Browse...##bokeh"):
            open_dialog("bokeh")
        stem = os.path.splitext(os.path.basename(ui["bokeh_path"]))[0] or "shape"
        imgui.same_line()
        imgui.begin_disabled(not ui["bokeh_path"])
        if imgui.button("Capture"):
            in_thread(start_steps, repeat(["open", ui["bokeh_path"], "open"]), f"bokeh_{stem}", "bokeh")
        imgui.end_disabled()
        imgui.same_line()
        if imgui.button("Card shape"):
            in_thread(start_steps, repeat([card("open"), card("shape", stem), card("open")]), f"bokeh_{stem}_card", "bokeh")
        imgui.text_wrapped("Capture: open, the shape, open, at the Image size and Rotation set in Controls. "
                           "A GIF gives one frame per GIF frame. Card shape: the same through a laser-cut card, "
                           "with a pause before each card.")

    def flutter_code():
        """the code the Flutter tab has chosen, or None and the reason"""
        if ui["fl_mode"] == 0:
            return ui["fl_designed"], None
        try:
            return flutter.parse(ui["fl_custom"]), None
        except ValueError as e:
            return None, str(e)

    def flutter_label(base, settings=""):
        """the start of a Flutter tab capture's file names: the Name box or base, then _2, _3 when that
        is already in the download folder so nothing gets replaced, then the settings"""
        name = re.sub(r"[^A-Za-z0-9_-]+", "_", ui["fl_name"]).strip("_") or base
        try:
            have = os.listdir(os.path.join(ui["outdir"], "flutter"))
        except OSError:
            have = []
        i = 1
        while True:
            label = (name if i == 1 else f"{name}_{i}") + settings
            # download_sequence writes <label>_<index>_<tag>.<ext> and <label>_manifest.json; the last
            # label started counts too, since its files may not have landed yet
            used = re.compile(re.escape(label) + r"_(\d{2,}_|manifest\.json$)")
            if label != ui["seq_label"] and not any(used.match(f) for f in have):
                return label
            i += 1

    def flutter_shutter():
        """the shutter speed Run takes its frames at, as the camera names it: the one picked under
        These settings, else the camera's as last read"""
        picked = ui["fl_photo"]["shutterspeed"] if ui["fl_photo_mode"] == 1 else ""
        return picked or (ui["choices"].get("shutterspeed") or {}).get("current") or ""

    def shutter_problem(code, shutter):
        """why Run cannot take its frames at this shutter speed, or None. The panel stays black
        for Lead while the shutter opens, so the shutter has to stay open for Lead + code"""
        s = flutter.shutter_s(shutter)
        need = flutter.min_shutter_s(len(code), ui["fl_chop"], ui["fl_lead"])
        if s is None:
            if shutter:
                return f"Shutter speed {shutter!r} is not a time: turn the mode dial to M"
            return "Shutter speed unknown: Refresh settings in Controls"
        if s < need:
            opts = (ui["choices"].get("shutterspeed") or {}).get("choices") or []
            fits = [c for c in opts if (flutter.shutter_s(c) or 0) >= need]
            hint = min(fits, key=flutter.shutter_s) if fits else f"{need:g}"
            return f"Shutter {shutter} s is shorter than Lead + code {need:g} s: set {hint} s or longer"
        return None

    def run_flutter(code, label):
        """Run at the shutter speed under Photo, Camera as it is reading the camera first. It does
        not start when that is shorter than Lead + code"""
        if ui["fl_photo_mode"] == 0 or not ui["fl_photo"]["shutterspeed"]:
            set_status("Reading the camera's shutter speed...", BUSY)
            if not load_choices():
                return
        shutter = flutter_shutter()
        if any(ui["fl_take"][k] for k in FLUTTER_ORDER if k != "impulse"):
            problem = shutter_problem(code, shutter)
            if problem:
                set_status(problem, BAD)
                return
        start_steps(flutter_steps(code, shutter), label, "flutter", True)

    def flutter_steps(code, shutter):
        """the capture set, every frame on M, in the order that needs the fewest changes at the rig:
        the stationary reference, then the moving target through the impulse, coded, box and leakage
        frames, then the darks. shutter is the shutter speed of every frame but the impulse. A pop-up
        pauses the run before the reference, before the moving frames and before the darks, the
        three times something changes at the rig. The moving frames run straight through, so the
        target never has to stop. The frame after each pop-up or after the impulse frames sets the
        camera, so the impulse shutter speed never carries over"""
        n = len(code)
        chop, lead, tail = ui["fl_chop"], ui["fl_lead"], ui["fl_tail"]
        method = "invert" if ui["fl_method"] == 0 else "fill"
        take, r = ui["fl_take"], ui["repeats"]
        speed = flutter.target_speed(ui["fl_blur"], n, chop)
        code_s = n * chop / 1000
        moving = [k for k in FLUTTER_ORDER if take[k] and k in ("coded", "box", "leakage")]
        stages = [k for k, on in (("reference", take["reference"]), ("moving", take["impulse"] or moving),
                                  ("dark", take["dark"])) if on]
        # These settings sends its ISO and aperture with every capture, the impulse too
        cam = {k: v for k, v in ui["fl_photo"].items() if v and k != "shutterspeed"} if ui["fl_photo_mode"] == 1 else {}

        def frame(tag, bits, stage=None, camera=False):
            s = {"code": flutter.to_text(bits), "chop_ms": chop, "lead_ms": lead, "tail_ms": tail,
                 "method": method, "tag": tag}
            if stage:
                s["prompt"] = prompt(stage)
            if stage or camera:
                s["camera"] = dict(cam, shutterspeed=shutter)
            return s

        def count(k):
            return f"{r} {k} photo" + ("s" if r > 1 else "")

        def prompt(stage):
            """the pop-up before a stage of the run: what to change at the rig, what the photos are for"""
            if stage == "reference":
                title, ready = "Reference photo" + ("s" if r > 1 else ""), "when ready"
                todo = ["Have the target standing still."]
                what = (f"The camera takes {count('reference')} at {shutter} s with the panel open for "
                        f"{code_s:.1f} s. With the target still, this is the sharp photo the deblurred results "
                        f"are checked against.")
            elif stage == "moving":
                title, ready = "Moving photos", "once the target moves steadily"
                todo = [f"Set the target moving at {speed:.1f} px/s and keep it moving until the dark photos."]
                lines = {
                    "impulse": f"{count('impulse')} at {ui['fl_impulse']} s with the panel white: sharp but dark, "
                               f"the short exposure to compare with.",
                    "coded": f"{count('coded')} at {shutter} s: the panel stays black for {lead / 1000:.1f} s, "
                             f"flickers the code for {code_s:.1f} s, then stays black. The target blurs in the "
                             f"code's on and off pattern, which the deblur can undo.",
                    "box": f"{count('box')} at {shutter} s with the panel open for the code's {code_s:.1f} s, an "
                           f"ordinary long exposure that comes out as a plain smear.",
                    "leakage": f"{count('leakage')} at {shutter} s with the panel black the whole time, to "
                               f"measure the light the shut panel lets through.",
                }
                shown = [k for k in ("impulse", *moving) if take[k]]
                what = ("The camera takes these without stopping:\n" +
                        "\n".join(f"  - {lines[k]}" for k in shown))
                if r > 1 and len(moving) > 1:
                    what += f"\nThe {', '.join(moving[:-1])} and {moving[-1]} photos take turns."
                t = r * (take["impulse"] * ((flutter.shutter_s(ui["fl_impulse"]) or 0) + ui["settle"] +
                                            FRAME_OVERHEAD_S) +
                         len(moving) * ((flutter.shutter_s(shutter) or 0) + FRAME_OVERHEAD_S))
                what += (f"\n\nThat takes about {t:.0f} s, and the target travels about {round(speed * t, -2):,.0f} "
                         f"px. Start it near the edge of the frame it moves away from, so it stays in view.")
            else:
                title, ready = "Dark photo" + ("s" if r > 1 else ""), "when ready"
                todo = (["Stop the target."] if "moving" in stages else []) + ["Put the lens cap on."]
                what = (f"The camera takes {count('dark')} at {shutter} s with the panel black and no light "
                        f"getting in. This measures the camera's own noise.")
            if stage == stages[0]:
                todo.append("Check the mode dial is on M.")
            steps_todo = "\n".join(f"  {i}. {t}" for i, t in enumerate(todo, 1))
            return (f"Step {stages.index(stage) + 1} of {len(stages)}: {title}\n\nWhat to do:\n{steps_todo}\n\n"
                    f"What happens: {what}\n\nPress Continue {ready}.")

        steps = []
        if take["reference"]:
            for j in range(r):
                steps.append(frame("reference", flutter.box(n), "reference" if j == 0 else None))
        if take["impulse"]:
            for j in range(r):
                s = {"pattern": "white", "tag": "impulse", "camera": dict(cam, shutterspeed=ui["fl_impulse"])}
                if j == 0:
                    s["prompt"] = prompt("moving")
                steps.append(s)
        bits = {"coded": code, "box": flutter.box(n), "leakage": flutter.shut(n)}
        for j in range(r):
            for k in moving:
                # the first one puts the shutter back after the impulse frames, or pops up when there are none
                first = j == 0 and k == moving[0]
                steps.append(frame(k, bits[k], "moving" if first and not take["impulse"] else None, camera=first))
        if take["dark"]:
            for j in range(r):
                steps.append(frame("dark", flutter.shut(n), "dark" if j == 0 else None))
            steps.append({"prompt": "Last step: take the lens cap off\n\nAll the photos are taken. Take the lens cap "
                                    "off, then press Continue to finish and download them."})
        return steps

    def flutter_tab():
        if imgui.radio_button(f"Designed {cfg.FLUTTER_CHOPS} chops", ui["fl_mode"] == 0):
            ui["fl_mode"] = 0
        imgui.same_line()
        if imgui.radio_button("Custom", ui["fl_mode"] == 1):
            ui["fl_mode"] = 1
        if ui["fl_mode"] == 1:
            changed, val = imgui.input_text("0s and 1s", ui["fl_custom"])
            if changed:
                ui["fl_custom"] = val
        code, err = flutter_code()
        if code:
            imgui.text_wrapped(f"{flutter.to_text(code)}   {len(code)} chops, {sum(code)} open, score {flutter.score(code):.3f}")
        else:
            imgui.text_colored(BAD, err)
        for key, label, step, big in (("fl_chop", "Chop ms", 5, 50), ("fl_lead", "Lead ms", 100, 500), ("fl_tail", "Tail ms", 100, 500)):
            changed, val = imgui.input_int(label, ui[key], step, big)
            if changed:
                ui[key] = max(1 if key == "fl_chop" else 0, min(65535, val))
        if imgui.radio_button("Invert", ui["fl_method"] == 0):
            ui["fl_method"] = 0
        imgui.same_line()
        if imgui.radio_button("Frame write", ui["fl_method"] == 1):
            ui["fl_method"] = 1
        changed, val = imgui.input_int("Blur px", ui["fl_blur"], 10, 50)
        if changed:
            ui["fl_blur"] = max(1, val)
        opts = (ui["choices"].get("shutterspeed") or {}).get("choices") or []
        if opts:
            idx = opts.index(ui["fl_impulse"]) if ui["fl_impulse"] in opts else 0
            changed, idx = imgui.combo("Impulse shutter", idx, opts)
            if changed:
                ui["fl_impulse"] = opts[idx]
        else:
            changed, val = imgui.input_text("Impulse shutter", ui["fl_impulse"])
            if changed:
                ui["fl_impulse"] = val
        if code:
            n = len(code)
            total = flutter.total_ms(n, ui["fl_chop"], ui["fl_lead"], ui["fl_tail"]) / 1000
            imgui.text(f"Code {n * ui['fl_chop'] / 1000:.2f} s, "
                       f"target {flutter.target_speed(ui['fl_blur'], n, ui['fl_chop']):.1f} px/s")
            if total > cfg.FLUTTER_MAX_S:
                imgui.text_colored(BAD, f"Over the {cfg.FLUTTER_MAX_S} s limit of the board's clock")
            shutter = flutter_shutter()
            problem = shutter_problem(code, shutter)
            if problem:
                imgui.text_colored(BAD, problem)
            else:
                need = flutter.min_shutter_s(n, ui["fl_chop"], ui["fl_lead"])
                imgui.text(f"Shutter {shutter} s on M, at least Lead + code {need:g} s")
        imgui.text("Take:")
        for k in FLUTTER_ORDER:
            imgui.same_line()
            changed, val = imgui.checkbox(k, ui["fl_take"][k])
            if changed:
                ui["fl_take"][k] = val
        imgui.text("Photo:")
        imgui.same_line()
        if imgui.radio_button("Camera as it is", ui["fl_photo_mode"] == 0):
            ui["fl_photo_mode"] = 0
        imgui.same_line()
        if imgui.radio_button("These settings", ui["fl_photo_mode"] == 1):
            ui["fl_photo_mode"] = 1
        if ui["fl_photo_mode"] == 1:
            for k in SETTINGS:
                ch = ui["choices"].get(k) or {}
                opts = ch.get("choices") or []
                if opts:
                    if ui["fl_photo"][k] not in opts:
                        ui["fl_photo"][k] = ch["current"] if ch.get("current") in opts else opts[0]
                    changed, idx = imgui.combo(f"{k}##photo", opts.index(ui["fl_photo"][k]), opts)
                    if changed:
                        ui["fl_photo"][k] = opts[idx]
                else:
                    changed, val = imgui.input_text(f"{k}##photo", ui["fl_photo"][k])
                    if changed:
                        ui["fl_photo"][k] = val
        changed, val = imgui.input_text_with_hint("Name", "empty for the automatic name", ui["fl_name"])
        if changed:
            ui["fl_name"] = val
        method = "invert" if ui["fl_method"] == 0 else "fill"
        settings = f"_{ui['fl_chop']}ms_{method}"
        imgui.begin_disabled(code is None)
        if imgui.button("LCD only flutter shutter") and code:
            step = {"code": flutter.to_text(code), "chop_ms": ui["fl_chop"], "lead_ms": ui["fl_lead"], "tail_ms": ui["fl_tail"],
                    "method": method, "tag": "switch", "capture": False}
            in_thread(start_steps, repeat([step]), flutter_label("flutter_switch", settings), "flutter")
        imgui.end_disabled()
        imgui.same_line()
        if imgui.button("Capture"):
            step = {"pattern": "white", "tag": "photo"}
            if ui["fl_photo_mode"] == 1:
                step["camera"] = {k: v for k, v in ui["fl_photo"].items() if v}
            in_thread(start_steps, repeat([step]), flutter_label("flutter_photo"), "flutter")
        imgui.same_line()
        imgui.begin_disabled(code is None)
        if imgui.button("Run") and code:
            if any(ui["fl_take"].values()):
                in_thread(run_flutter, code, flutter_label("flutter", settings))
            else:
                set_status("Tick at least one capture", BAD)
        imgui.end_disabled()
        imgui.text_wrapped("LCD only flutter shutter plays the code on the panel Repeats times with no camera, so you can "
                           "watch it switch and check Invert takes it fully clear and dark. Capture takes a plain photo "
                           "Repeats times with the panel white and no flicker. Run takes the ticked captures Repeats "
                           "times each, every frame on M: the reference first with the target still, then impulse at "
                           "the Impulse shutter and coded, box and leakage with the target moving, then the darks with "
                           "the lens cap on. Photo sets both Capture and Run: Camera "
                           "as it is takes the camera's settings as they are when you press it, These settings sends "
                           "the ones picked above first. Run's impulse frames keep the Impulse shutter. The panel stays "
                           "black for Lead while the shutter opens, so Run needs a shutter speed of at least Lead + code "
                           "and does not start on a shorter one. A pop-up says what to do and waits for Continue before "
                           "the reference, before the moving photos and before the darks. The moving photos then run "
                           "straight through so the target never stops, and their pop-up says how far it travels. "
                           "Name starts the file names, "
                           "and Run and LCD only flutter shutter add the chop and method after it. A name already in "
                           "the folder gets _2, _3 and so on, so nothing is replaced.")

    while not glfw.window_should_close(window):
        glfw.poll_events()
        if args.exit_after and time.time() - t_start > args.exit_after:
            glfw.set_window_should_close(window, True)

        cam_frame, cam_new, panel_frame, panel_new, status, connected = poller.take()
        if cam_new and cam_frame is not None:
            cam_size = upload_texture(cam_tex, cam_frame)
        if panel_new and panel_frame is not None:
            panel_size = upload_texture(panel_tex, panel_frame)

        # follow the server's live view state with a stream reader
        live_on = bool(status and status.get("liveview"))
        if live_on and reader is None:
            reader = FrameReader(f"{server.base}/video_feed")
        elif not live_on and reader is not None:
            reader.stop()
            reader = None
            live_size = None
        if reader is not None:
            frame, new = reader.get_frame()
            if new and frame is not None:
                live_size = upload_texture(live_tex, frame)

        # a finished sequence of ours gets downloaded once
        if status and ui["seq_session"] and not ui["seq_collected"]:
            job = status["job"]
            if job["session"] == ui["seq_session"] and not job["running"]:
                ui["seq_collected"] = True
                in_thread(download_sequence, server, ui["seq_session"], ui["seq_outdir"], ui["seq_label"])

        # the file dialog runs as its own process; collect its answer once it closes
        if ui["dialog"] is not None and ui["dialog"].ready(0):
            picked = ui["dialog"].result()
            ui["dialog"] = None
            if picked:
                ui["dialog_dir"] = os.path.dirname(picked[0])
                if ui["dialog_target"] == "images":
                    add_images(picked)
                elif ui["dialog_target"] == "bokeh":
                    ui["bokeh_path"] = picked[0]
                elif ui["dialog_target"] in ("depth_a", "depth_b"):
                    ui[ui["dialog_target"]] = picked[0]
                else:
                    ui["png_path"] = picked[0]

        impl.process_inputs()
        imgui.new_frame()

        # --- Window 1: camera view, the smallest, since the experiments need the room ---
        imgui.set_next_window_size((420, 330), imgui.Cond_.first_use_ever)
        imgui.set_next_window_pos((20, 20), imgui.Cond_.first_use_ever)
        imgui.begin("Camera View")
        if reader is not None and live_size:
            imgui.text_colored(OK, f"LIVE  {reader.fps:.0f} fps")
            draw_fitted(live_tex, *live_size)
        elif reader is not None:
            centred_text("Starting live view...")
        elif cam_size:
            imgui.text_colored(BUSY, "Last capture")
            draw_fitted(cam_tex, *cam_size)
        elif not connected:
            centred_text("Connecting to the server...")
        else:
            centred_text("No frame yet. Turn on Live view or press Preview shot.")
        imgui.end()

        # --- Window 2: panel view ---
        imgui.set_next_window_size((420, 370), imgui.Cond_.first_use_ever)
        imgui.set_next_window_pos((20, 370), imgui.Cond_.first_use_ever)
        imgui.begin("Aperture Panel")
        if status:
            rot = status.get("rotation_deg") or 0
            imgui.text(f"{os.path.basename(status['pattern'] or '')}  {status['diameter_mm']:.1f} mm  "
                       + (f"{rot:.0f} deg  " if rot else "") + f"{status['panel'][0]}x{status['panel'][1]}")
            imgui.separator()
        if panel_size:
            draw_fitted(panel_tex, *panel_size)
        else:
            centred_text("No pattern yet")
        imgui.end()

        # --- Window 3: controls ---
        imgui.set_next_window_size((400, 720), imgui.Cond_.first_use_ever)
        imgui.set_next_window_pos((460, 20), imgui.Cond_.first_use_ever)
        imgui.begin("Controls")

        imgui.text("Server: ")
        imgui.same_line()
        if connected:
            imgui.text_colored(OK, f"connected  {status['display']} / {status['camera']}")
        else:
            imgui.text_colored(BAD, "disconnected")
            imgui.same_line()
            if imgui.button("Retry"):
                in_thread(load_lists)
                in_thread(load_choices)

        imgui.begin_disabled(busy() or not connected)

        imgui.separator_text("Pattern")
        if ui["patterns"]:
            changed, idx = imgui.combo("Pattern", ui["pattern_idx"], ui["patterns"])
            if changed:
                ui["pattern_idx"] = idx
        changed, val = imgui.input_float("Pupil mm (0 = config)", ui["diameter"], 0.5, 5.0, "%.1f")
        if changed:
            ui["diameter"] = max(0.0, val)
            ui["resize_at"] = time.time() + RESIZE_DELAY_S
        changed, val = imgui.slider_float("Rotation", ui["rotation"], -180.0, 180.0, "%.0f deg anticlockwise")
        if changed:
            ui["rotation"] = val
            ui["resize_at"] = time.time() + RESIZE_DELAY_S
        for label, step in (("-90", -90.0), ("0", None), ("+90", 90.0)):
            if label != "-90":
                imgui.same_line()
            if imgui.small_button(f"{label}##rot"):
                # keep the result inside -180..180 so the slider can show it
                ui["rotation"] = 0.0 if step is None else (ui["rotation"] + step + 180.0) % 360.0 - 180.0
                ui["resize_at"] = time.time()

        def show_pattern(name):
            d = ui["diameter"] or None
            try:
                server.show(name, d, ui["image_pct"] / 100, ui["rotation"])
                set_status(f"Showing {name}", OK)
            except Exception as e:
                set_status(f"Pattern error: {e}", BAD)

        if imgui.button("Show pattern") and ui["patterns"]:
            in_thread(show_pattern, ui["patterns"][ui["pattern_idx"]])
        imgui.same_line()
        if imgui.button("Refresh list"):
            in_thread(load_lists)
        changed, val = imgui.input_text("Image", ui["png_path"])
        if changed:
            ui["png_path"] = val
        if imgui.button("Browse..."):
            open_dialog("single")
        imgui.same_line()
        if imgui.button("Show image") and ui["png_path"]:
            in_thread(show_pattern, ui["png_path"])
        changed, val = imgui.slider_float("Image size", ui["image_pct"], 25.0, 140.0, "%.0f%% of pupil")
        if changed:
            ui["image_pct"] = val
            ui["resize_at"] = time.time() + RESIZE_DELAY_S
        if imgui.small_button("Fit circle"):
            ui["image_pct"] = FIT_CIRCLE_PCT
            ui["resize_at"] = time.time()
        if imgui.is_item_hovered():
            imgui.set_tooltip("71%: the whole image fits inside the round pupil. Above 100% the edges are cut")

        def play_gif(name, speed):
            try:
                server.play(name, speed, ui["diameter"] or None, ui["image_pct"] / 100, ui["rotation"])
                set_status(f"Playing {os.path.basename(name)} at {speed:.2f}x", OK)
            except Exception as e:
                set_status(f"Play error: {e}", BAD)

        def stop_gif():
            try:
                server.stop_play()
                set_status("Stopped", OK)
            except Exception as e:
                set_status(f"Stop error: {e}", BAD)

        is_gif = ui["png_path"].lower().endswith(".gif")
        playing_now = bool(status and status.get("playing"))
        changed, val = imgui.slider_float("GIF speed", ui["speed"], 0.25, 4.0, "%.2fx", imgui.SliderFlags_.logarithmic)
        if changed:
            ui["speed"] = val
        if imgui.is_item_deactivated_after_edit() and playing_now and is_gif:
            in_thread(play_gif, ui["png_path"], ui["speed"])     # same GIF again only changes the speed
        # a new pupil, image size or rotation redraws whatever is on the panel once the value settles
        if ui["resize_at"] and time.time() >= ui["resize_at"] and connected and not busy():
            ui["resize_at"] = 0.0
            if playing_now:
                in_thread(play_gif, status["playing"], ui["speed"])     # restarts the GIF at the new size
            elif status and status.get("pattern"):
                in_thread(show_pattern, status["pattern"])
        imgui.begin_disabled(not is_gif)
        if imgui.button("Play GIF"):
            in_thread(play_gif, ui["png_path"], ui["speed"])
        imgui.end_disabled()
        imgui.same_line()
        imgui.begin_disabled(not playing_now)
        if imgui.button("Stop"):
            in_thread(stop_gif)
        imgui.end_disabled()
        if playing_now:
            imgui.same_line()
            imgui.text_colored(OK, f"playing {os.path.basename(status['playing'])} {status['play_speed']:.2f}x")
        elif status and status.get("play_error"):
            imgui.text_colored(BAD, f"playback stopped: {status['play_error']}")

        imgui.separator_text("Camera")
        if ui["choices"]:
            for name in SETTINGS:
                if name not in ui["choices"]:
                    continue
                opts = ui["choices"][name].get("choices") or []
                if not opts:
                    imgui.text(f"{name}: {ui['choices'][name].get('current')}")
                    continue
                changed, idx = imgui.combo(name, ui["choice_idx"].get(name, 0), opts)
                if changed:
                    ui["choice_idx"][name] = idx

                    def apply(n=name, v=opts[idx]):
                        try:
                            server.configure({n: v})
                            set_status(f"{n} = {v}", OK)
                        except Exception as e:
                            set_status(f"{n} error: {e}", BAD)

                    in_thread(apply)
        else:
            imgui.text("No camera settings loaded")
        if imgui.button("Refresh settings"):
            in_thread(load_choices)

        imgui.separator_text("Frames")
        wanted = bool(status and status.get("liveview_wanted"))
        changed, val = imgui.checkbox("Live view", wanted)
        if changed:
            def toggle(on=val):
                try:
                    server.liveview(on)
                    set_status("Live view on" if on else "Live view off", OK)
                except Exception as e:
                    set_status(f"Live view error: {e}", BAD)
            in_thread(toggle)
        imgui.same_line()
        imgui.text_disabled("(pauses around each capture)")
        changed, val = imgui.input_text("Label", ui["label"])
        if changed:
            ui["label"] = val
        changed, val = imgui.input_text("Out dir", ui["outdir"])
        if changed:
            ui["outdir"] = val

        def preview_shot():
            try:
                set_status("Taking preview...", BUSY)
                info = server.preview()
                set_status(f"Preview {info['file']}", OK)
            except Exception as e:
                set_status(f"Preview error: {e}", BAD)

        def capture_one():
            try:
                set_status("Capturing...", BUSY)
                info = server.capture(ui["label"])
                download_single(server, info, ui["outdir"], ui["label"])
            except Exception as e:
                set_status(f"Capture error: {e}", BAD)

        if imgui.button("Preview shot"):
            in_thread(preview_shot)
        imgui.same_line()
        if imgui.button("Capture and save"):
            in_thread(capture_one)

        imgui.separator_text("Sequence")
        seq_names = list(ui["sequences"]) + ["custom", "images"]
        changed, idx = imgui.combo("Sequence", ui["seq_idx"], seq_names)
        if changed:
            ui["seq_idx"] = idx
        if seq_names[ui["seq_idx"]] == "custom":
            changed, val = imgui.input_text("Patterns", ui["custom"])
            if changed:
                ui["custom"] = val
        elif seq_names[ui["seq_idx"]] == "images":
            imgs, counts = ui["images"], ui["image_counts"]
            if imgui.begin_list_box("##images", imgui.ImVec2(-1, 7 * imgui.get_text_line_height_with_spacing())):
                for i, p in enumerate(imgs):
                    n = counts[i]
                    extra = f"  ({n} frames)" if p.lower().endswith(".gif") else ""
                    if n == 0:
                        extra = "  (cannot read)"
                    clicked, _ = imgui.selectable(f"{i + 1:2d}  {os.path.basename(p)}{extra}##{i}", ui["image_sel"] == i)
                    if clicked:
                        ui["image_sel"] = i
                    if imgui.is_item_hovered():
                        imgui.set_tooltip(p)
                imgui.end_list_box()
            if imgui.button("Add files..."):
                open_dialog("images")
            imgui.same_line()
            if imgui.button("Add pattern") and ui["patterns"]:
                add_images([ui["patterns"][ui["pattern_idx"]]])
            sel = ui["image_sel"]
            has_sel = 0 <= sel < len(imgs)
            imgui.begin_disabled(not has_sel)
            if imgui.button("Up") and sel > 0:
                for lst in (imgs, counts):
                    lst[sel - 1], lst[sel] = lst[sel], lst[sel - 1]
                ui["image_sel"] = sel - 1
            imgui.same_line()
            if imgui.button("Down") and has_sel and sel < len(imgs) - 1:
                for lst in (imgs, counts):
                    lst[sel + 1], lst[sel] = lst[sel], lst[sel + 1]
                ui["image_sel"] = sel + 1
            imgui.same_line()
            if imgui.button("Remove") and has_sel:
                del imgs[sel]
                del counts[sel]
                ui["image_sel"] = min(sel, len(imgs) - 1)
            imgui.end_disabled()
            imgui.same_line()
            if imgui.button("Clear"):
                imgs.clear()
                counts.clear()
                ui["image_sel"] = -1
            imgui.text_disabled(f"{sum(counts)} photos" if imgs else "Add PNGs, GIFs or a pattern; runs top to bottom")
        else:
            imgui.text_wrapped(" > ".join(ui["sequences"][seq_names[ui["seq_idx"]]]))
        changed, val = imgui.input_float("Settle s", ui["settle"], 0.05, 0.5, "%.2f")
        if changed:
            ui["settle"] = max(0.0, val)

        def run_sequence():
            body = {"label": ui["label"], "settle": ui["settle"], "image_scale": ui["image_pct"] / 100,
                    "rotation_deg": ui["rotation"]}
            if ui["diameter"]:
                body["diameter_mm"] = ui["diameter"]
            chosen = seq_names[ui["seq_idx"]]
            if chosen == "custom":
                body["patterns"] = ui["custom"].split()
            elif chosen == "images":
                if not ui["images"]:
                    set_status("The image list is empty", BAD)
                    return
                body["patterns"] = list(ui["images"])
            else:
                body["sequence"] = chosen
            try:
                info = server.start_sequence(body)
                ui["seq_session"] = info["session"]
                ui["seq_label"] = ui["label"]
                ui["seq_outdir"] = ui["outdir"]
                ui["seq_collected"] = False
                set_status(f"Running {info['total']} frames...", BUSY)
            except Exception as e:
                set_status(f"Sequence error: {e}", BAD)

        if imgui.button("Run sequence"):
            in_thread(run_sequence)

        imgui.end_disabled()

        if status and status["job"]["running"]:
            job = status["job"]
            frac = (job["index"]) / max(1, job["total"])
            imgui.progress_bar(frac, imgui.ImVec2(-1, 0), f"step {job['index'] + 1} of {job['total']}")

        imgui.spacing()
        imgui.separator()
        imgui.text("Activity: ")
        imgui.same_line()
        imgui.text_colored(status_color, status_message)
        if status and status.get("last_file"):
            imgui.text(f"Last frame: {status['last_file']}")
        imgui.text(f"UI {imgui.get_io().framerate:.0f} FPS")
        imgui.end()

        # --- Window 4: experiments ---
        imgui.set_next_window_size((700, 720), imgui.Cond_.first_use_ever)
        imgui.set_next_window_pos((880, 20), imgui.Cond_.first_use_ever)
        imgui.begin("Experiments")
        job = status["job"] if status else None
        if job and job["running"]:
            if job.get("waiting"):
                imgui.text_colored(BUSY, "Waiting for you:")
                imgui.text_wrapped(job["waiting"])
                if imgui.button("Continue"):
                    in_thread(go)
                imgui.same_line()
            else:
                imgui.progress_bar(job["index"] / max(1, job["total"]), imgui.ImVec2(-80, 0),
                                   f"step {job['index'] + 1} of {job['total']}")
                imgui.same_line()
            if imgui.button("Stop"):
                in_thread(stop_job)
            imgui.separator()
        # the Flutter run's prompts pop up, one for the first frame of each capture
        if job and job["running"] and job.get("waiting") and job["session"] == ui["popup_session"]:
            if ui["popup_seen"] != (job["session"], job["index"]):
                ui["popup_seen"] = (job["session"], job["index"])
                ui["popup_text"] = job["waiting"]
                imgui.open_popup("Next step")
        imgui.set_next_window_pos(imgui.get_main_viewport().get_center(), imgui.Cond_.appearing, imgui.ImVec2(0.5, 0.5))
        if imgui.begin_popup_modal("Next step", None, imgui.WindowFlags_.always_auto_resize)[0]:
            title, _, body = ui["popup_text"].partition("\n")
            imgui.text_colored(BUSY, title)
            imgui.separator()
            imgui.push_text_wrap_pos(imgui.get_font_size() * 36)
            imgui.text_unformatted(body.strip())
            imgui.pop_text_wrap_pos()
            imgui.spacing()
            clicked_go = imgui.button("Continue", imgui.ImVec2(160, 0))
            imgui.same_line()
            clicked_stop = imgui.button("Stop run", imgui.ImVec2(160, 0))
            if clicked_go:
                in_thread(go)
            if clicked_stop:
                in_thread(stop_job)
            if clicked_go or clicked_stop or not (job and job.get("waiting")):
                imgui.close_current_popup()      # also when the job carried on or stopped from somewhere else
            imgui.end_popup()
        imgui.begin_disabled(busy() or not connected)
        changed, val = imgui.input_int("Repeats", ui["repeats"])
        if changed:
            ui["repeats"] = max(1, min(20, val))
        changed, val = imgui.input_int("Target distance mm", ui["distance"], 50, 100)
        if changed:
            ui["distance"] = max(1, val)
        imgui.text_disabled(f"Frames download to {ui['outdir']}/<experiment>/")
        if imgui.begin_tab_bar("##experiments"):
            for name, draw in (("Depth", depth_tab), ("Refocus", refocus_tab), ("Bokeh", bokeh_tab), ("Flutter", flutter_tab)):
                if imgui.begin_tab_item(name)[0]:
                    draw()
                    imgui.end_tab_item()
            imgui.end_tab_bar()
        imgui.end_disabled()
        imgui.end()

        imgui.render()
        fb_w, fb_h = glfw.get_framebuffer_size(window)
        gl.glViewport(0, 0, fb_w, fb_h)
        gl.glClearColor(0.06, 0.06, 0.08, 1.0)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT)
        impl.render(imgui.get_draw_data())
        if args.screenshot and args.exit_after and time.time() - t_start > args.exit_after - 0.5:
            buf = gl.glReadPixels(0, 0, fb_w, fb_h, gl.GL_RGB, gl.GL_UNSIGNED_BYTE)
            shot = np.frombuffer(buf, np.uint8).reshape(fb_h, fb_w, 3)[::-1]
            cv2.imwrite(args.screenshot, cv2.cvtColor(shot, cv2.COLOR_RGB2BGR))
            args.screenshot = None
        glfw.swap_buffers(window)

    poller.stop()
    if reader is not None:
        reader.stop()
    if poller.status and poller.status.get("liveview_wanted"):
        try:
            server.liveview(False)      # with the window gone the camera would stream to nobody until the idle timeout
        except Exception as e:
            print(f"could not turn live view off: {e}")
    impl.shutdown()
    imgui.destroy_context()
    gl.glDeleteTextures([cam_tex, live_tex, panel_tex])
    glfw.terminate()


if __name__ == "__main__":
    main()

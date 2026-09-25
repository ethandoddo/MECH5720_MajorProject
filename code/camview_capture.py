"""Camera view and control window for the aperture rig. Run this on your laptop while
server.py is running on the Pi. This is the main way to drive the rig.

Three windows: what the DSLR sees, what the panel is showing, and the controls for
patterns, camera settings, single frames and sequences. With Live view on, the camera
view streams the EOS 60D's live view. Off, it shows the last frame the camera took.
Live view pauses around every capture because one process owns the USB link.

  python camview_capture.py --host 192.168.1.100 --outdir captures

Requires: opencv-python, requests, glfw, pyopengl, imgui-bundle
  pip install -r requirements-laptop.txt
"""

import argparse
import json
import os
import shutil
import threading
import time

import cv2
import numpy as np
import requests

import glfw
import OpenGL.GL as gl
from imgui_bundle import imgui
from imgui_bundle.python_backends.glfw_backend import GlfwRenderer

status_message = "Ready"
status_color = (0.5, 0.7, 1.0, 1.0)
OK = (0.2, 0.8, 0.2, 1.0)
BUSY = (0.9, 0.6, 0.2, 1.0)
BAD = (0.9, 0.2, 0.2, 1.0)
SETTINGS = ("iso", "shutterspeed", "aperture")


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

    def show(self, name, diameter_mm=None):
        return self.post("/pattern", {"name": name, "diameter_mm": diameter_mm}, timeout=15)

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
                key = (st["pattern"], st["diameter_mm"])
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
            for name in fr.get("files", [fr["file"]]):
                ext = os.path.splitext(name)[1]
                dest = os.path.join(outdir, f"{label}_{fr['index']:02d}_{fr['pattern']}{ext}")
                server.download(session, name, dest)
            fr["local"] = os.path.join(outdir, f"{label}_{fr['index']:02d}_{fr['pattern']}")
        with open(os.path.join(outdir, f"{label}_manifest.json"), "w") as f:
            json.dump(manifest, f, indent=2)
        if manifest.get("error"):
            set_status(f"Sequence stopped: {manifest['error']}", BAD)
        else:
            set_status(f"Saved {len(manifest['frames'])} frames to {outdir}", OK)
    except Exception as e:
        set_status(f"Download error: {e}", BAD)


def download_single(server, info, outdir, label):
    try:
        os.makedirs(outdir, exist_ok=True)
        for name in info.get("files", [info["file"]]):
            ext = os.path.splitext(name)[1]
            server.download(info["session"], name, os.path.join(outdir, f"{label}_{info['pattern']}{ext}"))
        set_status(f"Saved {label}_{info['pattern']} to {outdir}", OK)
    except Exception as e:
        set_status(f"Download error: {e}", BAD)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.1.100")
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
        "seq_session": None, "seq_collected": True, "seq_label": "",
    }

    def load_lists():
        try:
            ui["patterns"] = server.patterns()
            st = server.status()
            ui["sequences"] = st.get("sequences", {})
            if st.get("pattern") in ui["patterns"]:
                ui["pattern_idx"] = ui["patterns"].index(st["pattern"])
            set_status("Connected to Pi", OK)
        except Exception as e:
            set_status(f"Could not reach the Pi: {e}", BAD)

    def load_choices():
        try:
            ch = server.choices()
            ui["choices"] = ch
            for k, v in ch.items():
                opts = v.get("choices") or []
                ui["choice_idx"][k] = opts.index(v["current"]) if v.get("current") in opts else 0
        except Exception as e:
            set_status(f"Camera settings unavailable: {e}", BAD)

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
                in_thread(download_sequence, server, ui["seq_session"], ui["outdir"], ui["seq_label"])

        impl.process_inputs()
        imgui.new_frame()

        # --- Window 1: camera view ---
        imgui.set_next_window_size((820, 640), imgui.Cond_.first_use_ever)
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
            centred_text("Connecting to the Pi...")
        else:
            centred_text("No frame yet. Turn on Live view or press Preview shot.")
        imgui.end()

        # --- Window 2: panel view ---
        imgui.set_next_window_size((320, 500), imgui.Cond_.first_use_ever)
        imgui.set_next_window_pos((860, 20), imgui.Cond_.first_use_ever)
        imgui.begin("Aperture Panel")
        if status:
            imgui.text(f"{status['pattern']}  {status['diameter_mm']:.1f} mm  {status['panel'][0]}x{status['panel'][1]}")
            imgui.separator()
        if panel_size:
            draw_fitted(panel_tex, *panel_size)
        else:
            centred_text("No pattern yet")
        imgui.end()

        # --- Window 3: controls ---
        imgui.set_next_window_size((380, 720), imgui.Cond_.first_use_ever)
        imgui.set_next_window_pos((1200, 20), imgui.Cond_.first_use_ever)
        imgui.begin("Controls")

        imgui.text("Pi: ")
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

        def show_pattern(name):
            d = ui["diameter"] or None
            try:
                server.show(name, d)
                set_status(f"Showing {name}", OK)
            except Exception as e:
                set_status(f"Pattern error: {e}", BAD)

        if imgui.button("Show pattern") and ui["patterns"]:
            in_thread(show_pattern, ui["patterns"][ui["pattern_idx"]])
        imgui.same_line()
        if imgui.button("Refresh list"):
            in_thread(load_lists)
        changed, val = imgui.input_text("PNG on Pi", ui["png_path"])
        if changed:
            ui["png_path"] = val
        if imgui.button("Show PNG") and ui["png_path"]:
            in_thread(show_pattern, ui["png_path"])

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
        seq_names = list(ui["sequences"]) + ["custom"]
        changed, idx = imgui.combo("Sequence", ui["seq_idx"], seq_names)
        if changed:
            ui["seq_idx"] = idx
        if seq_names[ui["seq_idx"]] == "custom":
            changed, val = imgui.input_text("Patterns", ui["custom"])
            if changed:
                ui["custom"] = val
        else:
            imgui.text_wrapped(" > ".join(ui["sequences"][seq_names[ui["seq_idx"]]]))
        changed, val = imgui.input_float("Settle s", ui["settle"], 0.05, 0.5, "%.2f")
        if changed:
            ui["settle"] = max(0.0, val)

        def run_sequence():
            body = {"label": ui["label"], "settle": ui["settle"]}
            if ui["diameter"]:
                body["diameter_mm"] = ui["diameter"]
            chosen = seq_names[ui["seq_idx"]]
            if chosen == "custom":
                body["patterns"] = ui["custom"].split()
            else:
                body["sequence"] = chosen
            try:
                info = server.start_sequence(body)
                ui["seq_session"] = info["session"]
                ui["seq_label"] = ui["label"]
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
            imgui.progress_bar(frac, imgui.ImVec2(-1, 0), f"frame {job['index'] + 1} of {job['total']}")

        imgui.spacing()
        imgui.separator()
        imgui.text("Activity: ")
        imgui.same_line()
        imgui.text_colored(status_color, status_message)
        if status and status.get("last_file"):
            imgui.text(f"Last frame: {status['last_file']}")
        imgui.text(f"UI {imgui.get_io().framerate:.0f} FPS")
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
    impl.shutdown()
    imgui.destroy_context()
    gl.glDeleteTextures([cam_tex, live_tex, panel_tex])
    glfw.terminate()


if __name__ == "__main__":
    main()

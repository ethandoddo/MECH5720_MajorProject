"""Live view from the camera as a stream of JPEG frames.

  gphoto  the EOS 60D's live view through `gphoto2 --stdout --capture-movie`, which writes
          back-to-back JPEG frames at roughly 15 to 25 per second. One process owns the USB
          device, so the server pauses the stream around every still capture and restarts
          it afterwards. Stopping sets viewfinder=0 so the mirror is down before a capture
  dummy   the panel image with a little noise at five frames a second, so the window's live
          view path runs with no camera
"""
import io
import subprocess
import threading
import time

import numpy as np
from PIL import Image

import config as cfg

SOI = b"\xff\xd8"
EOI = b"\xff\xd9"


class LiveView:
    name = "base"

    def __init__(self):
        self.running = False
        self._lock = threading.Lock()
        self._frame = None
        self._seq = 0

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def latest(self, after=-1, timeout=1.0):
        """(seq, jpeg bytes) once a frame newer than `after` exists, or (after, None) on timeout"""
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            with self._lock:
                if self._frame is not None and self._seq > after:
                    return self._seq, self._frame
            time.sleep(0.01)
        return after, None

    def _publish(self, jpeg):
        with self._lock:
            self._frame = jpeg
            self._seq += 1

    def frames(self):
        """generator of JPEG frames for an HTTP client, ending when the stream stops"""
        seq = -1
        while self.running:
            seq, jpeg = self.latest(seq, timeout=2.0)
            if jpeg is not None:
                yield jpeg


class DummyLiveView(LiveView):
    name = "dummy"

    def __init__(self, display):
        super().__init__()
        self.display = display
        self._thread = None

    def start(self):
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        rng = np.random.default_rng()
        while self.running:
            img = self.display.last
            if img is not None:
                a = np.asarray(img.convert("L"), dtype=np.float64)
                a = np.clip(a * 0.7 + 20 + rng.normal(0, 6, a.shape), 0, 255).astype(np.uint8)
                buf = io.BytesIO()
                Image.fromarray(a).resize((a.shape[1] * 4, a.shape[0] * 4), Image.NEAREST).save(buf, "JPEG", quality=80)
                self._publish(buf.getvalue())
            time.sleep(0.2)


class GPhotoLiveView(LiveView):
    name = "gphoto"

    def __init__(self, binary=None):
        super().__init__()
        self.bin = binary or cfg.GPHOTO_BIN
        self._proc = None
        self._thread = None

    def start(self):
        if self.running:
            return
        self._proc = subprocess.Popen([self.bin, "--stdout", "--capture-movie"],
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        buf = b""
        while self.running and self._proc and self._proc.poll() is None:
            chunk = self._proc.stdout.read(65536)
            if not chunk:
                break
            buf += chunk
            while True:
                s = buf.find(SOI)
                if s < 0:
                    buf = b""
                    break
                e = buf.find(EOI, s + 2)
                if e < 0:
                    buf = buf[s:]
                    break
                self._publish(buf[s:e + 2])
                buf = buf[e + 2:]
        self.running = False

    def stop(self):
        self.running = False
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
        # bring the mirror down so the next still capture starts from a known state
        subprocess.run([self.bin, "--set-config", "viewfinder=0"], capture_output=True, timeout=20)


def open_liveview(name, display=None):
    if name == "gphoto":
        return GPhotoLiveView()
    if name == "dummy":
        return DummyLiveView(display)
    raise KeyError(name)

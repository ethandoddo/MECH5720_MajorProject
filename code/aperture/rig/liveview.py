"""Live view from the camera as a stream of JPEG frames.

  gphoto  the EOS 60D's live view through `gphoto2 --stdout --capture-movie`, which writes
          back-to-back JPEG frames at roughly 15 to 25 per second. One process owns the USB
          device, so the server pauses the stream around every still capture and restarts
          it afterwards. Stopping sets viewfinder=0 so the mirror is down before a capture.
          Live view is the camera's biggest drain on the battery, so the stream also ends
          itself when nobody has taken a frame for LIVEVIEW_IDLE_S, after LIVEVIEW_MAX_S in
          one go, or when gphoto2 dies, and says why through on_end
  dummy   the panel image with a little noise at five frames a second, so the window's live
          view path runs with no camera
"""
import io
import select
import subprocess
import threading
import time

import numpy as np
from PIL import Image

from aperture import config as cfg

SOI = b"\xff\xd8"
EOI = b"\xff\xd9"


class LiveView:
    name = "base"

    def __init__(self, on_end=None):
        self.running = False
        self.on_end = on_end            # called with a reason when the stream ends on its own rather than through stop()
        self._lock = threading.Lock()
        self._frame = None
        self._seq = 0
        self._last_pull = 0.0           # when a client last took a frame, for the idle timeout

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
                self._last_pull = time.monotonic()
                yield jpeg


class DummyLiveView(LiveView):
    name = "dummy"

    def __init__(self, display, on_end=None):
        super().__init__(on_end)
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

    def __init__(self, binary=None, on_end=None):
        super().__init__(on_end)
        self.bin = binary or cfg.GPHOTO_BIN
        self._proc = None
        self._proc_lock = threading.Lock()  # owns _proc: stop() and the reader thread both close, whoever gets here first does it

    def start(self):
        with self._proc_lock:
            if self._proc is not None:
                return
            proc = subprocess.Popen([self.bin, "--stdout", "--capture-movie"],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
            self._proc = proc
            self._last_pull = time.monotonic()
            self.running = True
            threading.Thread(target=self._run, args=(proc,), daemon=True).start()

    def _run(self, proc):
        """reads frames out of proc until it ends, stop() takes it away or a timeout says so"""
        buf = b""
        t_start = time.monotonic()
        reason = "the stream ended"
        while self._proc is proc:
            # a one second wait rather than a blocking read, so the timeouts still fire when the camera goes quiet
            ready, _, _ = select.select([proc.stdout], [], [], 1.0)
            if ready:
                chunk = proc.stdout.read(65536)
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
            now = time.monotonic()
            if cfg.LIVEVIEW_IDLE_S and now - self._last_pull > cfg.LIVEVIEW_IDLE_S:
                reason = f"nobody took a frame for {cfg.LIVEVIEW_IDLE_S:g} s"
                break
            if cfg.LIVEVIEW_MAX_S and now - t_start > cfg.LIVEVIEW_MAX_S:
                reason = f"it ran for {cfg.LIVEVIEW_MAX_S:g} s"
                break
        self._close(proc, reason)
        proc.stdout.close()

    def _close(self, proc, reason=None):
        """end proc, reap it and bring the mirror down. Only the caller that finds proc still
        current does the work; reason is given when the stream ended on its own"""
        with self._proc_lock:
            if proc is not self._proc:
                return
            self._proc = None
            self.running = False
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
            # bring the mirror down so the next still capture starts from a known state
            subprocess.run([self.bin, "--set-config", "viewfinder=0"], capture_output=True, timeout=20)
        if reason and self.on_end:
            self.on_end(reason)

    def stop(self):
        self.running = False
        proc = self._proc
        if proc is not None:
            self._close(proc)


def open_liveview(name, display=None, on_end=None):
    if name == "gphoto":
        return GPhotoLiveView(on_end=on_end)
    if name == "dummy":
        return DummyLiveView(display, on_end)
    raise KeyError(name)

"""Camera backends. capture(stem) writes one frame and returns the files it wrote, raw first.

  gphoto  a Canon EOS 60D on USB through the gphoto2 command line tool. The camera
          sits in manual exposure and manual focus, with the file quality set on the
          body. RAW+JPEG on the body gives a CR2 for processing and a JPEG the camera
          view can show at once
  dummy   writes whatever the display is showing as a PNG, so a whole sequence can run
          on a laptop with nothing plugged in

bulb_start(stem, seconds) opens the shutter in bulb mode for about that long and returns a
job whose wait() gives the files, so the server can read the panel's flutter trace while
the exposure runs. The 60D puts bulb on the mode dial, so ensure_bulb() checks for it.
"""
import math
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

import config as cfg

RAW_EXT = {".cr2", ".dng", ".nef", ".arw", ".raw"}
SETTING_NAMES = ("iso", "shutterspeed", "aperture")


class CameraError(RuntimeError):
    pass


class Camera:
    name = "base"

    def capture(self, stem):
        """stem is a path without extension; returns the files written, the raw one first"""
        raise NotImplementedError

    def bulb_start(self, stem, seconds):
        """open the shutter for about `seconds` and download; returns a job with wait()"""
        raise NotImplementedError

    def ensure_bulb(self):
        """raise CameraError unless the body is ready for a bulb exposure"""
        pass

    def configure(self, settings):
        return {}

    def choices(self):
        """{"iso": {"current": "100", "choices": [...]}, ...} for the settings the GUI offers"""
        return {}

    def describe(self):
        return {"camera": self.name}


class ThreadJob:
    """a capture that runs in its own thread; wait() returns the files or raises"""

    def __init__(self, fn):
        self.files = None
        self.error = None
        self._thread = threading.Thread(target=self._run, args=(fn,), daemon=True)
        self._thread.start()

    def _run(self, fn):
        try:
            self.files = fn()
        except Exception as e:
            self.error = e

    def wait(self, timeout=None):
        self._thread.join(timeout)
        if self._thread.is_alive():
            raise CameraError("the bulb exposure did not finish")
        if self.error:
            raise self.error if isinstance(self.error, CameraError) else CameraError(str(self.error))
        return self.files


class DummyCamera(Camera):
    name = "dummy"

    def __init__(self, display):
        self.display = display
        self.settings = {"iso": "100", "shutterspeed": "1/30", "aperture": "1.8"}

    def capture(self, stem):
        path = Path(str(stem) + ".png")
        path.parent.mkdir(parents=True, exist_ok=True)
        img = self.display.last
        if img is None:
            raise CameraError("nothing has been shown yet")
        img.save(path)
        return [path]

    def bulb_start(self, stem, seconds):
        def run():
            time.sleep(seconds)
            return self.capture(stem)
        return ThreadJob(run)

    def configure(self, settings):
        self.settings.update(settings)
        return settings

    def choices(self):
        opts = {
            "iso": ["100", "200", "400", "800", "1600"],
            "shutterspeed": ["1/250", "1/125", "1/60", "1/30", "1/15", "1/8", "1/4", "1/2", "1", "2", "4"],
            "aperture": ["1.8", "2.8", "4", "5.6", "8"],
        }
        return {k: {"current": self.settings[k], "choices": v} for k, v in opts.items()}


class GPhotoCamera(Camera):
    name = "gphoto"

    def __init__(self, binary=None):
        self.bin = binary or cfg.GPHOTO_BIN
        if shutil.which(self.bin) is None:
            raise CameraError(f"{self.bin} not found; sudo apt install gphoto2")
        # the desktop's volume monitor grabs the camera as a USB drive and gphoto2 then
        # cannot claim it, so make sure it is out of the way before the first capture
        subprocess.run(["pkill", "-f", "gvfs-gphoto2-volume-monitor"], capture_output=True)
        subprocess.run(["pkill", "-f", "gvfsd-gphoto2"], capture_output=True)

    def _run(self, *args, timeout=cfg.CAPTURE_TIMEOUT_S):
        proc = subprocess.run([self.bin, *args], capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            raise CameraError(proc.stderr.strip() or proc.stdout.strip() or f"gphoto2 exit {proc.returncode}")
        return proc.stdout

    def describe(self):
        try:
            return {"camera": self.name, "summary": self._run("--summary", timeout=20)}
        except CameraError as e:
            return {"camera": self.name, "error": str(e)}

    def list_config(self):
        return self._run("--list-all-config", timeout=30)

    def configure(self, settings):
        """settings like {"iso": "100", "shutterspeed": "1/30"}; names as --list-config reports them"""
        args = []
        for k, v in settings.items():
            args += ["--set-config", f"{k}={v}"]
        if args:
            self._run(*args, timeout=30)
        return settings

    def choices(self):
        out = {}
        for name in SETTING_NAMES:
            try:
                text = self._run("--get-config", name, timeout=20)
            except CameraError:
                continue
            current = re.search(r"^Current:\s*(.*)$", text, re.M)
            opts = re.findall(r"^Choice:\s*\d+\s+(.*)$", text, re.M)
            out[name] = {"current": current.group(1).strip() if current else None, "choices": opts}
        return out

    def capture(self, stem):
        stem = Path(stem)
        stem.parent.mkdir(parents=True, exist_ok=True)
        # %C is the camera's own extension, so RAW+JPEG on the body gives two files
        template = str(stem) + ".%C"
        self._run("--capture-image-and-download", "--filename", template, "--force-overwrite")
        return self._written(stem)

    @staticmethod
    def _written(stem):
        written = [p for p in stem.parent.glob(stem.name + ".*") if not p.name.endswith("_preview.jpg")]
        if not written:
            raise CameraError("gphoto2 reported success but no file appeared")
        return sorted(written, key=lambda p: (p.suffix.lower() not in RAW_EXT, p.name))

    def ensure_bulb(self):
        """the 60D has bulb on the mode dial, so this asks the body and tries to set it, and
        says to turn the dial when both fail"""
        text = self._run("--get-config", "shutterspeed", timeout=20)
        m = re.search(r"^Current:\s*(.*)$", text, re.M)
        current = m.group(1).strip() if m else ""
        if current.lower() == "bulb":
            return
        try:
            self._run("--set-config", "shutterspeed=bulb", timeout=20)
            return
        except CameraError:
            pass
        raise CameraError(f"the shutter speed is {current!r}, not bulb: turn the mode dial to B")

    def bulb_start(self, stem, seconds):
        """open the bulb with BULB_OPEN, hold it about `seconds`, close it with BULB_CLOSE and
        download the frame, all in one gphoto2 call so the USB session stays open throughout"""
        stem = Path(stem)
        stem.parent.mkdir(parents=True, exist_ok=True)
        template = str(stem) + ".%C"
        args = [self.bin, "--set-config", cfg.BULB_OPEN, "--wait-event", f"{int(math.ceil(seconds))}s",
                "--set-config", cfg.BULB_CLOSE, "--wait-event-and-download", f"{int(cfg.BULB_DOWNLOAD_S)}s",
                "--filename", template, "--force-overwrite"]
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        def run():
            try:
                out, err = proc.communicate(timeout=seconds + cfg.BULB_DOWNLOAD_S + cfg.CAPTURE_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                proc.kill()
                raise CameraError("gphoto2 did not return from the bulb exposure")
            if proc.returncode != 0:
                raise CameraError(err.strip() or out.strip() or f"gphoto2 exit {proc.returncode}")
            return self._written(stem)
        return ThreadJob(run)


def to_dng(raw):
    """a DNG beside a CR2 through dnglab, without the CR2 embedded in it. The raw pixels and the
    BlackLevel tag match the CR2, so MATLAB reads the same numbers. LibRaw reads these DNGs
    with a black level 40 to 100 counts too high, so rawpy and gates.py stay on the CR2"""
    raw = Path(raw)
    out = raw.with_suffix(".dng")
    if shutil.which(cfg.DNGLAB_BIN) is None:
        raise CameraError(f"{cfg.DNGLAB_BIN} not found; see Laptop setup in the README")
    proc = subprocess.run([cfg.DNGLAB_BIN, "convert", "--embed-raw", "false", "--override", str(raw), str(out)],
                          capture_output=True, text=True, timeout=120)
    if proc.returncode != 0 or not out.exists():
        raise CameraError(f"dnglab could not convert {raw.name}: {proc.stderr.strip()[-300:]}")
    return out


def add_dngs(files):
    """files from capture() with a DNG added after each CR2 when SAVE_DNG is on"""
    out = list(files)
    if cfg.SAVE_DNG:
        for f in files:
            if f.suffix.lower() == ".cr2":
                out.append(to_dng(f))
    return out


def open_camera(name, display=None):
    if name == "gphoto":
        return GPhotoCamera()
    if name == "dummy":
        return DummyCamera(display)
    raise KeyError(name)

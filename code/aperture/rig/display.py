"""Display backends. Each one takes a PANEL_W x PANEL_H PIL image and puts it on a screen.

  arduino  the Adafruit 358 panel in the optical path, on an Arduino or an ESP32 running
           arduino/aperture_panel. The laptop streams each image over USB serial
  window   a Tk window on the laptop, the panel image scaled up with nearest-neighbour
           sampling so every panel pixel shows as a crisp block
  st7735   the same panel wired to a Raspberry Pi over SPI, the original layout
  null     keeps the last image in memory, for tests with no screen at all

show() returns the time.monotonic() at which the backend finished pushing the frame.
The cell then still takes its own response time to settle.
`python -m aperture.rig.display` prints what every pattern costs on the serial link.

play_code() plays a flutter shutter code, every chop the whole panel open or shut, and
read_play() blocks until it has finished and returns the trace: when each switch started
and finished. The arduino backend has the sketch do it from the board's own clock. The
other backends play it from a thread with full frames and return the same trace, so a
flutter run goes end to end with no hardware.
"""
import os
import queue
import struct
import threading
import time

import numpy as np
from PIL import Image

from aperture import config as cfg

MAX_CHOPS = 64          # the sketch's limit, as flutter.py has it


def flat(white):
    """every pixel open (white) or shut, as the pattern code would draw it, so PANEL_INVERT applies"""
    open_px = 255 if white else 0
    return Image.new("L", (cfg.PANEL_W, cfg.PANEL_H), 255 - open_px if cfg.PANEL_INVERT else open_px)


class Display:
    name = "base"

    def __init__(self):
        self.last = None
        self._play = None

    def show(self, img):
        raise NotImplementedError

    def close(self):
        pass

    def play_code(self, code, chop_ms, lead_ms, tail_ms, method="invert"):
        """start playing the code from a thread with full frames; returns when the clock
        started. Backends with a board of their own override this"""
        code = [1 if b else 0 for b in code]
        if not 1 <= len(code) <= MAX_CHOPS:
            raise ValueError(f"a code has 1 to {MAX_CHOPS} chops")
        self.show(flat(False))
        t0 = time.monotonic()
        self._play = {"code": code, "chop": chop_ms, "lead": lead_ms, "tail": tail_ms,
                      "t0": t0, "start": [], "end": [], "error": None}
        self._play["thread"] = threading.Thread(target=self._run_play, daemon=True)
        self._play["thread"].start()
        return t0

    def _run_play(self):
        p = self._play
        try:
            shown = False
            for i in range(len(p["code"]) + 1):
                due = p["t0"] + (p["lead"] + i * p["chop"]) / 1000
                want = i < len(p["code"]) and bool(p["code"][i])
                time.sleep(max(0.0, due - time.monotonic()))
                p["start"].append(round((time.monotonic() - p["t0"]) * 1000))
                if want != shown:
                    self.show(flat(want))
                    shown = want
                p["end"].append(round((time.monotonic() - p["t0"]) * 1000))
            end = p["t0"] + (p["lead"] + len(p["code"]) * p["chop"] + p["tail"]) / 1000
            time.sleep(max(0.0, end - time.monotonic()))
        except Exception as e:
            p["error"] = str(e)

    def read_play(self):
        """wait for the code to finish; the trace of when each switch started and finished"""
        p = self._play
        if p is None:
            raise RuntimeError("no code is playing")
        p["thread"].join()
        self._play = None
        if p["error"]:
            raise RuntimeError(f"playback failed: {p['error']}")
        return {"start_ms": p["start"], "end_ms": p["end"]}


class NullDisplay(Display):
    name = "null"

    def show(self, img):
        self.last = img
        return time.monotonic()


class ST7735Display(Display):
    """The panel on a Raspberry Pi over SPI. Needs adafruit-circuitpython-rgb-display."""
    name = "st7735"

    def __init__(self):
        super().__init__()
        import board
        import digitalio
        from adafruit_rgb_display import st7735

        cs = digitalio.DigitalInOut(getattr(board, cfg.SPI_CS))
        dc = digitalio.DigitalInOut(getattr(board, f"D{cfg.PIN_DC}"))
        rst = digitalio.DigitalInOut(getattr(board, f"D{cfg.PIN_RST}"))
        self.disp = st7735.ST7735R(
            board.SPI(), cs=cs, dc=dc, rst=rst, baudrate=cfg.SPI_BAUD,
            width=cfg.PANEL_W, height=cfg.PANEL_H, rotation=cfg.PANEL_ROTATION,
        )

    def show(self, img):
        self.disp.image(img.convert("RGB"))
        self.last = img
        return time.monotonic()


class WindowDisplay(Display):
    """Tk wants one thread to own the window, so the window runs in its own thread and
    show() hands it images through a queue and waits until the frame has been drawn."""
    name = "window"

    def __init__(self, scale=None, title="aperture panel"):
        super().__init__()
        self.scale = scale or cfg.WINDOW_SCALE
        self.title = title
        self._queue = queue.Queue()
        self._ready = threading.Event()
        self._error = None
        # over SSH there is no DISPLAY, but the machine's own desktop is display :0
        if not os.environ.get("DISPLAY") and os.path.exists("/tmp/.X11-unix/X0"):
            os.environ["DISPLAY"] = ":0"
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(5)
        if self._error:
            raise RuntimeError(f"no window could be opened: {self._error}. Run on the desktop, "
                               f"or over SSH with DISPLAY=:0, or use the arduino backend for the panel")

    def _run(self):
        import tkinter as tk
        from PIL import ImageTk

        try:
            root = tk.Tk()
        except Exception as e:
            self._error = e
            self._ready.set()
            return
        root.title(self.title)
        root.configure(bg="black")
        w, h = cfg.PANEL_W * self.scale, cfg.PANEL_H * self.scale
        label = tk.Label(root, bg="black", bd=0, highlightthickness=0)
        label.pack()
        self._root = root
        self._closed = False

        def poll():
            try:
                while True:
                    img, done = self._queue.get_nowait()
                    big = img.resize((w, h), Image.NEAREST)
                    photo = ImageTk.PhotoImage(big)
                    label.configure(image=photo)
                    label.image = photo
                    root.update_idletasks()
                    done["t"] = time.monotonic()
                    done["event"].set()
            except queue.Empty:
                pass
            if not self._closed:
                root.after(10, poll)

        root.after(0, poll)
        self._ready.set()
        root.mainloop()

    def show(self, img):
        done = {"event": threading.Event(), "t": None}
        self._queue.put((img, done))
        done["event"].wait(5)
        self.last = img
        return done["t"] or time.monotonic()

    def close(self):
        self._closed = True
        try:
            self._root.after(0, self._root.destroy)
        except Exception:
            pass


ARDUINO_VIDS = {0x2341, 0x2A03, 0x303A, 0x1A86, 0x0403, 0x10C4}   # Arduino, Arduino.org, Espressif, CH340, FTDI, CP210x


def encode_runs(img):
    """The wire format of arduino/aperture_panel. For each row, bytes that alternate black
    run, white run, black run and so on, starting with black and summing to the width. A
    row that starts white begins with a zero. Every run fits a byte, since a row is 128 px."""
    a = np.asarray(img.convert("L")) > 127
    out = bytearray()
    for row in a:
        edges = np.flatnonzero(row[1:] != row[:-1]) + 1
        runs = np.diff(np.concatenate(([0], edges, [row.size])))
        if row[0]:
            out.append(0)
        out.extend(runs.tolist())
    return bytes(out)


class ArduinoDisplay(Display):
    """The panel on an Arduino or ESP32 running arduino/aperture_panel, over USB serial. show()
    streams the image as run lengths and returns the time the sketch's acknowledgement
    arrived, about a millisecond after its SPI write finished. Opening the port resets
    most boards, so the constructor waits for the sketch's banner first."""
    name = "arduino"

    def __init__(self, port=None, baud=None):
        super().__init__()
        import serial
        from serial.tools import list_ports

        self.protocol = None
        self.port = port or cfg.ARDUINO_PORT or self._find_port(list_ports)
        self.ser = serial.Serial(self.port, baud or cfg.ARDUINO_BAUD, timeout=cfg.ARDUINO_TIMEOUT_S)
        size = self._banner(3.0)
        if size is None:                 # the board did not reset on open, so ask it
            self.ser.write(b"?")
            size = self._banner(2.0)
        if size is None:
            raise RuntimeError(f"nothing answered on {self.port}; upload arduino/aperture_panel to the board")
        if self.protocol != cfg.ARDUINO_PROTOCOL:
            raise RuntimeError(f"the board on {self.port} runs protocol {self.protocol} and this code needs "
                               f"{cfg.ARDUINO_PROTOCOL}; upload arduino/aperture_panel to the board again")
        self.ser.write(bytes([ord("O"), (cfg.PANEL_ROTATION // 90) % 4]))
        size = self._banner(2.0)
        if size != (cfg.PANEL_W, cfg.PANEL_H):
            raise RuntimeError(f"PANEL_ROTATION {cfg.PANEL_ROTATION} makes the panel {size}, but patterns are "
                               f"{cfg.PANEL_W} x {cfg.PANEL_H}; use 0 or 180")

    @staticmethod
    def _find_port(list_ports):
        ports = list(list_ports.comports())
        for p in ports:
            if p.vid in ARDUINO_VIDS or p.device.startswith(("/dev/ttyACM", "/dev/ttyUSB")):
                return p.device
        found = ", ".join(p.device for p in ports) or "none"
        raise RuntimeError(f"no Arduino found; set ARDUINO_PORT in config.py. Serial ports: {found}")

    def _banner(self, seconds):
        """(width, height) from the next 'aperture <protocol> W H' line, or None after `seconds`;
        the protocol number lands in self.protocol"""
        deadline = time.monotonic() + seconds
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                return None
            self.ser.timeout = left
            parts = self.ser.readline().decode("ascii", errors="replace").split()
            if len(parts) == 4 and parts[0] == "aperture":
                try:
                    self.protocol, w, h = int(parts[1]), int(parts[2]), int(parts[3])
                    return w, h
                except ValueError:
                    continue

    def _ack(self):
        self.ser.timeout = cfg.ARDUINO_TIMEOUT_S
        reply = self.ser.read(1)
        while reply == b"c":             # credits still on their way at the end of a frame
            reply = self.ser.read(1)
        if reply == b"K":
            return time.monotonic()
        if reply == b"E":
            raise RuntimeError("the sketch rejected the frame; check ARDUINO_BAUD against BAUD in the sketch")
        raise RuntimeError(f"no acknowledgement from {self.port} within {cfg.ARDUINO_TIMEOUT_S} s")

    def show(self, img):
        """Send the frame with at most ARDUINO_WINDOW bytes in flight. The sketch sends 'c' for
        every ARDUINO_CREDIT bytes it takes out of its receive buffer, so the buffer never holds
        more than the window, however long the panel takes over each run."""
        data = encode_runs(img)
        self.ser.reset_input_buffer()
        self.ser.write(b"R")
        self.ser.timeout = cfg.ARDUINO_TIMEOUT_S
        sent = credited = 0
        while sent < len(data):
            room = cfg.ARDUINO_WINDOW - (sent - credited)
            if room > 0:
                chunk = data[sent:sent + room]
                self.ser.write(chunk)
                sent += len(chunk)
                continue
            reply = self.ser.read(1)
            if reply == b"c":
                credited += cfg.ARDUINO_CREDIT
            elif reply == b"E":
                raise RuntimeError("the sketch rejected the frame part way through")
            else:
                raise RuntimeError(f"no credit from {self.port} within {cfg.ARDUINO_TIMEOUT_S} s")
        t = self._ack()
        self.last = img
        return t

    def fill(self, white):
        """every panel pixel white or black in one short command, for switching time
        measurements. This bypasses PANEL_INVERT: white means the pixels drive white."""
        self.ser.reset_input_buffer()
        self.ser.write(bytes([ord("F"), 1 if white else 0]))
        t = self._ack()
        self.last = Image.new("L", (cfg.PANEL_W, cfg.PANEL_H), 255 if white else 0)
        return t

    def invert(self, on):
        """flip every pixel with one controller command, or restore them. Three SPI bytes,
        so a black panel turns white in the time the liquid crystal takes and no more"""
        self.ser.reset_input_buffer()
        self.ser.write(bytes([ord("I"), 1 if on else 0]))
        t = self._ack()
        if self.last is not None and on:
            self.last = Image.fromarray(255 - np.asarray(self.last.convert("L")))
        return t

    def play_code(self, code, chop_ms, lead_ms, tail_ms, method="invert"):
        """hand the code to the sketch, which plays it from its own clock. Returns the time
        its clock started, when the 'P' acknowledgement arrived. read_play() collects the
        switch times once it has finished"""
        code = [1 if b else 0 for b in code]
        n = len(code)
        if not 1 <= n <= MAX_CHOPS:
            raise ValueError(f"a code has 1 to {MAX_CHOPS} chops")
        if method not in ("invert", "fill"):
            raise ValueError("method is invert or fill")
        bits = bytearray((n + 7) // 8)
        for i, b in enumerate(code):
            if b:
                bits[i >> 3] |= 0x80 >> (i & 7)
        header = struct.pack("<BBBHHH", 0 if method == "invert" else 1, 0 if cfg.PANEL_INVERT else 1, n,
                             int(chop_ms), int(lead_ms), int(tail_ms))
        self.ser.reset_input_buffer()
        self.ser.write(b"P" + header + bytes(bits))
        self.ser.timeout = cfg.ARDUINO_TIMEOUT_S
        reply = self.ser.read(1)
        if reply == b"E":
            raise RuntimeError("the sketch rejected the code")
        if reply != b"P":
            raise RuntimeError(f"no play acknowledgement from {self.port} within {cfg.ARDUINO_TIMEOUT_S} s")
        self.last = flat(False)
        self._play = {"n": n, "total_s": (int(lead_ms) + n * int(chop_ms) + int(tail_ms)) / 1000}
        return time.monotonic()

    def read_play(self):
        """block until the sketch reports, then the trace: when each switch started and
        finished in ms since the clock started"""
        p = self._play
        if p is None:
            raise RuntimeError("no code is playing")
        self._play = None
        self.ser.timeout = p["total_s"] + 5
        head = self.ser.read(2)
        if len(head) < 2:
            raise RuntimeError("the sketch did not report at the end of the code")
        if head[0] != ord("D") or head[1] != p["n"]:
            raise RuntimeError("the sketch's play report is malformed")
        self.ser.timeout = cfg.ARDUINO_TIMEOUT_S
        words = 2 * (p["n"] + 1)
        raw = self.ser.read(2 * words)
        if len(raw) < 2 * words:
            raise RuntimeError("the sketch's play report is short")
        times = struct.unpack(f"<{words}H", raw)
        return {"start_ms": list(times[:p["n"] + 1]), "end_ms": list(times[p["n"] + 1:])}

    def close(self):
        self.ser.close()


BACKENDS = {"arduino": ArduinoDisplay, "st7735": ST7735Display, "window": WindowDisplay, "null": NullDisplay}


def open_display(name, **kw):
    return BACKENDS[name](**kw)


if __name__ == "__main__":
    # what each pattern costs on the serial link, at ten bits per byte
    from aperture import patterns

    for n in patterns.names():
        size = len(encode_runs(patterns.make(n)))
        print(f"{n:10s} {size:5d} bytes  {size * 10 / cfg.ARDUINO_BAUD * 1000:5.1f} ms at {cfg.ARDUINO_BAUD} baud")

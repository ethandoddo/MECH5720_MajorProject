"""Display backends. Each one takes a PANEL_W x PANEL_H PIL image and puts it on a screen.

  st7735  the Adafruit 358 panel over SPI, the one that sits in the optical path
  window  a Tk window on the 7 inch touchscreen or a laptop, the panel image scaled up
          with nearest-neighbour sampling so every panel pixel shows as a crisp block
  null    keeps the last image in memory, for tests with no screen at all

show() returns the time.monotonic() at which the backend finished pushing the frame.
The cell then still needs its own response time, which a photodiode has to measure.
"""
import os
import queue
import threading
import time

from PIL import Image

import config as cfg


class Display:
    name = "base"

    def __init__(self):
        self.last = None

    def show(self, img):
        raise NotImplementedError

    def close(self):
        pass


class NullDisplay(Display):
    name = "null"

    def show(self, img):
        self.last = img
        return time.monotonic()


class ST7735Display(Display):
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
        # over SSH there is no DISPLAY, but the Pi desktop on the HDMI screen is display :0
        if not os.environ.get("DISPLAY") and os.path.exists("/tmp/.X11-unix/X0"):
            os.environ["DISPLAY"] = ":0"
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(5)
        if self._error:
            raise RuntimeError(f"no window could be opened: {self._error}. Run on the Pi desktop, "
                               f"or over SSH with DISPLAY=:0, or use --backend st7735 for the panel")

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


BACKENDS = {"st7735": ST7735Display, "window": WindowDisplay, "null": NullDisplay}


def open_display(name, **kw):
    return BACKENDS[name](**kw)

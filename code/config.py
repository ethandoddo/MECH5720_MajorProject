"""Settings shared by the server, the clients, the pattern code and the arduino backend."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MASK_DIR = ROOT / "masks"
SESSIONS = ROOT.parent / "captures"     # the server writes one folder per sequence here

# ---- panel: Adafruit 358, ST7735R, 1.8 inch, portrait -------------------------------
PANEL_W, PANEL_H = 128, 160
PANEL_PITCH_MM = 28.03 / 128            # active area 28.03 x 35.04 mm, so 0.219 mm per pixel
PANEL_ROTATION = 0                      # 0 or 180; the patterns are portrait, so the arduino backend refuses 90 and 270
PANEL_INVERT = False                    # True when the stripped cell passes light where the image is black
WINDOW_SCALE = 3                        # window backend: 128 x 160 becomes 384 x 480 on the laptop screen

# ---- panel link ---------------------------------------------------------------------
# arduino backend: the laptop streams patterns to arduino/aperture_panel on an Arduino or ESP32 over USB serial
ARDUINO_PORT = None                     # None finds the first Arduino or ESP32; else "/dev/ttyACM0", "/dev/ttyUSB0" or "COM5"
ARDUINO_BAUD = 500_000                  # must match BAUD in the sketch
ARDUINO_PROTOCOL = 2                    # must match PROTOCOL in the sketch, which the banner reports
ARDUINO_CREDIT = 16                     # must match CREDIT_BYTES in the sketch: one 'c' per this many bytes taken
ARDUINO_WINDOW = 48                     # most frame bytes in flight; under the Uno's 64 byte receive buffer
ARDUINO_TIMEOUT_S = 2.0                 # wait for the sketch's acknowledgement; a frame takes under 0.5 s

# st7735 backend, the Raspberry Pi option: SPI wiring in BCM numbering, the Adafruit Pi guide's default
SPI_BAUD = 24_000_000
PIN_DC = 24
PIN_RST = 25
SPI_CS = "CE0"                          # board.CE0 or board.CE1

# ---- lens ---------------------------------------------------------------------------
FOCAL_MM = 50.0
F_NUMBER = 1.8                          # widest stop of the lens, since the iris stays open
PUPIL_MM = FOCAL_MM / F_NUMBER          # entrance pupil the pattern has to cover, 27.8 mm here

# ---- patterns -----------------------------------------------------------------------
PAIR = ("zhou_a", "zhou_b")             # Zhou, Lin and Nayar 2009, fig. 4, 13 x 13; levin / nayar are the Lab 3 masks
SCAN_N = 3                              # sub-aperture scan is SCAN_N x SCAN_N tiles, nine for post-capture refocus
SEQUENCES = {
    "pair": ["open", PAIR[0], PAIR[1], "open"],
    "scan": ["open"] + [f"scan{i}" for i in range(SCAN_N * SCAN_N)] + ["open"],
    "transmission": ["white", "black", "open"],
}

# ---- camera -------------------------------------------------------------------------
GPHOTO_BIN = "gphoto2"
SAVE_DNG = True                         # a DNG beside every CR2, for the Lab 3 MATLAB scripts; gates.py reads the CR2
DNGLAB_BIN = "dnglab"                   # github.com/dnglab/dnglab, converts the 60D's CR2 losslessly
SETTLE_S = 0.3                          # wait after a pattern change before the shutter fires
CAPTURE_TIMEOUT_S = 60                  # RAW download over USB 2 from the 60D takes a few seconds
# live view keeps the mirror up and the sensor streaming, the biggest drain on the LP-E6, so it stops itself
LIVEVIEW_IDLE_S = 30                    # when no client has taken a frame for this long: a closed window or a dropped stream
LIVEVIEW_MAX_S = 600                    # and after this long in one go, watched or not; tick the box again to carry on. 0 for no limit
